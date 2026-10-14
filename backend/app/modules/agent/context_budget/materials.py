"""材料让位于历史承接；只有超过完整请求预算时才取相关原文片段。"""

import json
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage

from app.modules.agent.context_budget.policy import estimate_input
from app.modules.agent.context_budget.rules import search_material
from app.modules.agent.context_budget.schemas import ContextPolicy
from app.modules.agent.runtime import AgentRuntimeContext
from app.modules.library.retrieval import LibraryRetrievalService, RetrievalScope


async def select_material(
    runtime: AgentRuntimeContext,
    policy: ContextPolicy,
    system: SystemMessage | None,
    messages: list[AnyMessage],
    tools: Sequence[Any],
) -> SystemMessage | None:
    if system is None or not isinstance(system.content, str):
        return system
    full = estimate_input(policy, [system, *messages], tools)
    if full.input_tokens < full.usable_budget * 0.8:
        return system
    scope = RetrievalScope(
        runtime.scope, runtime.record_id, runtime.library_item_id, runtime.course_id
    )
    async with runtime.session_factory() as session:
        if runtime.record_id:
            kind, source_id = "record", runtime.record_id
            _, content, version = await LibraryRetrievalService.read_source(
                session, scope, kind, source_id
            )
            marker = f"转写全文：\n{content}"
        elif runtime.library_item_id:
            from app.modules.agent.message_service import load_library_materials

            kind, source_id = "library", runtime.library_item_id
            _, _, version = await LibraryRetrievalService.read_source(
                session, scope, kind, source_id
            )
            records, items = await load_library_materials(
                runtime.session_factory, runtime.scope, source_id
            )
            parts = [f"【来源：{r.title}】\n{r.transcript}" for r in records]
            parts.extend(f"【来源：{item.title}】\n{item.content}" for item in items)
            marker = "资料正文（优先依据正文回答；正文各段以【来源：标题】开头）：\n" + "\n\n".join(
                parts
            )
        else:
            return system
        if marker not in system.content:
            return system
        without_material = system.model_copy(
            update={"content": system.content.replace(marker, "", 1)}
        )
        baseline = estimate_input(policy, [without_material, *messages], tools)
        # 小材料仍保留全文；大材料先让位，避免为保留整份材料压掉历史承接。
        if (
            not full.error_code
            and full.input_tokens - baseline.input_tokens <= full.usable_budget * 0.2
        ):
            return system
        query = next((m.text for m in reversed(messages) if isinstance(m, HumanMessage)), "")
        result = await search_material(session, runtime.session_id, scope, query)
    replacement = json.dumps(
        {
            "source_id": f"{kind}:{source_id}",
            "version": version,
            "message": (
                "全文超出本轮材料预算，仅提供相关原文；"
                "缺失细节用 search_library/read_context 取回。"
            ),
            "evidence_hits": [
                {"quote": h.quote, "segment_id": h.segment_id, **h.locator}
                for h in result.evidence_hits[:3]
            ],
        },
        ensure_ascii=False,
    )
    return system.model_copy(update={"content": system.content.replace(marker, replacement, 1)})
