"""范围会话的统一检索工具（工单 04：消费 LibraryRetrievalService，chat→library 单向）。

五档挂载会话（RECORD / LIBRARY_ITEM / COURSE / ALL）统一只挂本工具：作用域
与目标 id 由统一 Agent 运行时上下文承载（工单 01 起随每轮流式生成绑定，
见 agent/runtime.py），AgentConfig 挂载变体保持常量；FREE 不挂任何检索工具。
预算 module 负责每轮准入与消费；本工具保留结构化载荷裁剪：单次与累计回喂
超限截断并附 truncated 说明，不静默丢弃。

search_transcript 已退出模型可见工具面（迁移期记录级子串兜底由本工具经
服务继承）；web_search 为独立联网工具，与本地检索互不冒充。
"""

import json
from typing import cast

from langchain_core.tools import tool

from app.modules.agent.budget.policy import budget_snapshot
from app.modules.agent.budget.service import budgeted, format_output, mark_output
from app.modules.agent.context_budget.rules import search_material
from app.modules.agent.runtime import (
    ToolCallBudget,
    current_agent_runtime,
)
from app.modules.library.retrieval import (
    # 评测基线（test_library_retrieval_eval）从这里复用冻结值；本模块不再直接消费。
    CONCEPT_MATCH_LIMIT,  # noqa: F401  # pyright: ignore[reportUnusedImport]
    SEARCH_LIBRARY_LIMIT,
    AssetMatch,
    ConceptHint,
    EvidenceHit,
    LibraryRetrievalService,
    RetrievalScope,
)

# 本工具的载荷裁剪参数（contract §3 冻结值）；累计消费由预算 module 恢复。
TOOL_RESULT_MAX_CHARS = 4_000
TOOL_ROUND_OUTPUT_MAX_CHARS = 12_000


def _hit_payload(hit: EvidenceHit) -> dict[str, object]:
    """evidence 命中的模型可见载荷：逐字原文 + 来源标题 + 定位（分数不透出）。"""
    payload: dict[str, object] = {
        "source_title": hit.source_title,
        "quote": hit.quote,
        "context_window": hit.context_window,
        "segment_id": hit.segment_id,
        "source_type": hit.source_type,
        "channel": hit.channel,
    }
    payload.update(hit.locator)
    if hit.record_id is not None:
        payload["record_id"] = hit.record_id
    if hit.library_item_id is not None:
        payload["library_item_id"] = hit.library_item_id
    if hit.shared_source:
        payload["shared_source"] = True
    return payload


def _asset_payload(match: AssetMatch) -> dict[str, object]:
    return {"type": match.type, "id": match.id, "title": match.title}


def _concept_payload(hint: ConceptHint) -> dict[str, object]:
    return {
        "concept_id": hint.concept_id,
        "canonical_name": hint.canonical_name,
        "description": hint.description,
        "course_id": hint.course_id,
    }


def _truncate_payload(body: dict[str, object], budget: ToolCallBudget) -> tuple[str, bool]:
    """按预算截断序列化载荷：单次 ≤4000 字符、每轮累计 ≤12000 字符。

    截断顺序：evidence_hits 尾部 → asset_matches 尾部（concept_hints 保留，
    量级固定且帮助理解术语）；命中截断即置 truncated=true 并附收窄提示。
    累计已满时不再回喂新命中，仅返回提示（模型须基于已有结果回答）。
    """
    limit = min(TOOL_RESULT_MAX_CHARS, TOOL_ROUND_OUTPUT_MAX_CHARS - budget.chars_fed)
    body["tool_budget"] = budget_snapshot(budget)
    if limit <= 0:
        body = {
            "evidence_hits": [],
            "asset_matches": [],
            "concept_hints": [],
            "truncated": True,
            "tool_budget": budget_snapshot(budget),
            "message": (
                "本轮检索结果累计已达上下文预算，请基于已获得的检索结果回答，并建议收窄查询范围。"
            ),
        }
        return json.dumps(body, ensure_ascii=False, separators=(",", ":")), True

    def serialized() -> str:
        return json.dumps(body, ensure_ascii=False, separators=(",", ":"))

    evidence = _as_list(body.get("evidence_hits"))
    assets = _as_list(body.get("asset_matches"))
    truncated = False
    while len(serialized()) > limit:
        truncated = True
        if evidence:
            evidence.pop()
        elif assets:
            assets.pop()
        else:
            break
    if truncated:
        body["truncated"] = True
        body["message"] = "检索结果超出本轮预算已截断，可用更具体的关键词收窄查询。"
    payload = serialized()
    mark_output(payload)
    return payload, truncated


def _as_list(value: object) -> list[object]:
    return cast("list[object]", value) if isinstance(value, list) else []


def _payload(
    evidence_hits: list[dict[str, object]] | None = None,
    asset_matches: list[dict[str, object]] | None = None,
    concept_hints: list[dict[str, object]] | None = None,
    message: str = "",
    *,
    ok: bool = True,
    truncated: bool = False,
) -> str:
    body: dict[str, object] = {
        "evidence_hits": evidence_hits or [],
        "asset_matches": asset_matches or [],
        "concept_hints": concept_hints or [],
    }
    if message:
        body["message"] = message
    if truncated:
        body["truncated"] = True
    if not ok:
        body["ok"] = False
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


def _budget_rejection() -> str:
    return _payload(
        message=(
            "本轮检索次数已达上限，本次检索未执行，相关内容未能核实，不能据此认定资料不存在。"
            "停止补查与同轮重试，基于已获得的证据回答，并分别说明实际检索范围与未核实缺口。"
        ),
        ok=False,
    )


@tool
@budgeted(_budget_rejection)
async def search_library(query: str) -> str:
    """在本次对话范围的学习资料（转写、文档分片、资料正文）中检索原文片段。

    当问题涉及范围内资料的细节、需要跨记录对比或核实原文时使用：用 2~6 个
    关键词描述要找的内容。返回三类结果——evidence_hits 是唯一可引用的逐字
    原文（含来源标题、时间/页码定位），引用时逐字照抄其中原文、不超过 80 字，
    并注明 source_title；asset_matches 是标题导航命中，不可当原文引用；
    concept_hints 是范围内已确认的课程概念说明，可帮助理解术语，但不得当作
    原文引用。没有命中就换同义词重试（不超过 2 次）；范围内确实没有证据时
    如实说明「当前资料中未找到」，不要编造资料中不存在的内容。
    """
    context = current_agent_runtime()
    if context is None:
        return _payload(message="当前对话未挂载资料范围，无法检索。")
    needle = query.strip()
    if not needle:
        return _payload(message="检索词不能为空。")
    # 检索异常不炸整轮流（同 web_search 先例）：错误载荷 ok=false，模型可据此说明。
    try:
        async with context.session_factory() as session:
            result = await search_material(
                session,
                context.session_id,
                RetrievalScope(
                    scope=context.scope,
                    record_id=context.record_id,
                    library_item_id=context.library_item_id,
                    course_id=context.course_id,
                ),
                needle,
                SEARCH_LIBRARY_LIMIT,
            )
            evidence: list[dict[str, object]] = []
            for hit in result.evidence_hits:
                kind = "record" if hit.record_id else "library"
                target = hit.record_id or hit.library_item_id
                if target is None:
                    continue
                _, _, version = await LibraryRetrievalService.read_source(
                    session,
                    RetrievalScope(
                        scope=context.scope,
                        record_id=context.record_id,
                        library_item_id=context.library_item_id,
                        course_id=context.course_id,
                    ),
                    kind,
                    target,
                )
                evidence.append({**_hit_payload(hit), "source_version": version})
    except Exception:
        return _payload(message="检索暂时失败，请稍后重试。", ok=False)
    body: dict[str, object] = {
        "evidence_hits": evidence,
        "asset_matches": [_asset_payload(match) for match in result.asset_matches],
        "concept_hints": [_concept_payload(hint) for hint in result.concept_hints],
    }
    if not result.evidence_hits:
        body["message"] = (
            "本次检索已执行，当前查询未找到相关原文；这不表示资料中不存在相关内容。"
            "补查前请先检查共享剩余额度。"
        )
    return await format_output(lambda budget: _truncate_payload(body, budget)[0])
