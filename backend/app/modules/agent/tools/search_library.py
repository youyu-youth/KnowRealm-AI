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
from itertools import zip_longest
from typing import Annotated, cast

from langchain_core.tools import tool
from loguru import logger
from pydantic import Field

from app.modules.agent.budget.policy import budget_snapshot, output_remaining
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
    RetrievalResult,
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
    limit = min(TOOL_RESULT_MAX_CHARS, output_remaining(budget))
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
        body["truncated"] = True
        body["message"] = "检索结果超出本轮预算已截断，可用更具体的关键词收窄查询。"
        if evidence:
            evidence.pop()
        elif assets:
            assets.pop()
        else:
            break
    payload = serialized()
    if len(payload) > limit:
        # 连控制信封都放不下时只回固定提示，不再计入任何材料正文。
        return _payload(
            message="本执行或根任务字符额度不足，请基于已有证据回答。", truncated=True
        ), True
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
async def search_library(
    query: str
    | Annotated[
        list[Annotated[str, Field(min_length=1, max_length=200)]],
        Field(min_length=1, max_length=4),
    ],
) -> str:
    """在当前挂载资料中检索可引用的原文、定义和案例。

    每项只用一个主题的短关键词（如“原子性”），不要把不同主题拼成 AND 查询。
    多主题请传 query 列表，最多四项；各项独立检索、公平合并，合计最多八条证据。
    evidence_hits 是可引用的逐字原文，引用逐字照抄不超过80字并注明 source_title。
    asset_matches 仅供标题导航，concept_hints 仅供术语理解，均不可作为原文引用。
    无命中只表示本次查询未找到，不代表资料不存在；补查前检查自身与根剩余额度。
    """
    context = current_agent_runtime()
    if context is None:
        return _payload(message="当前对话未挂载资料范围，无法检索。")
    needles = list(
        dict.fromkeys(item.strip() for item in ([query] if isinstance(query, str) else query))
    )
    if not needles or any(not item for item in needles):
        return _payload(message="检索词不能为空。", ok=False)
    scope = RetrievalScope(
        scope=context.scope,
        record_id=context.record_id,
        library_item_id=context.library_item_id,
        course_id=context.course_id,
    )
    try:
        async with context.session_factory() as session:
            results = [
                await search_material(
                    session,
                    context.session_id,
                    scope,
                    needle,
                    SEARCH_LIBRARY_LIMIT,
                    short_query=True,
                )
                for needle in needles
            ]
            merged = RetrievalResult()
            seen: set[str] = set()
            for group in zip_longest(*(result.evidence_hits for result in results)):
                for hit in group:
                    if hit is not None and hit.segment_id not in seen:
                        seen.add(hit.segment_id)
                        merged.evidence_hits.append(hit)
            del merged.evidence_hits[SEARCH_LIBRARY_LIMIT:]
            assets_seen: set[str] = set()
            for result in results:
                for asset in result.asset_matches:
                    if asset.id not in assets_seen:
                        assets_seen.add(asset.id)
                        merged.asset_matches.append(asset)
                merged.concept_hints.extend(result.concept_hints)
            evidence: list[dict[str, object]] = []
            for hit in merged.evidence_hits:
                kind = "record" if hit.record_id else "library"
                target = hit.record_id or hit.library_item_id
                if target is None:
                    continue
                _, _, version = await LibraryRetrievalService.read_source(
                    session, scope, kind, target
                )
                item = {**_hit_payload(hit), "source_version": version}
                if len(needles) > 1:
                    # 批量优先保留各主题原文，重复上下文不挤掉后面的主题。
                    item["context_window"] = ""
                evidence.append(item)
    except Exception as exc:
        logger.warning(
            "library_search_failed",
            turn_id=context.turn_id,
            execution_id=context.execution_id,
            error_type=type(exc).__name__,
        )
        return _payload(message="检索暂时失败，请稍后重试。", ok=False)
    body: dict[str, object] = {
        "evidence_hits": evidence,
        "asset_matches": [_asset_payload(match) for match in merged.asset_matches[:8]],
        "concept_hints": [_concept_payload(hint) for hint in merged.concept_hints[:4]],
    }
    if not merged.evidence_hits:
        body["message"] = (
            "本次检索已执行，当前查询未找到相关原文；这不表示资料中不存在相关内容。"
            "补查前请先检查自身与根剩余额度。"
        )
    return await format_output(lambda budget: _truncate_payload(body, budget)[0])
