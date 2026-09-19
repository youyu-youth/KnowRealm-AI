"""范围会话的统一检索工具（工单 04：消费 LibraryRetrievalService，chat→library 单向）。

五档挂载会话（RECORD / LIBRARY_ITEM / COURSE / ALL）统一只挂本工具：作用域
与目标 id 由会话运行时经 ContextVar 绑定，AgentConfig 挂载变体保持常量；
FREE 不挂任何检索工具。工具预算（contract §3）在此生效：每轮调用次数上限、
单次载荷截断、累计回喂截断——超限截断并附 truncated 说明，不静默丢弃。

search_transcript 已退出模型可见工具面（迁移期记录级子串兜底由本工具经
服务继承）；web_search 为独立联网工具，与本地检索互不冒充。
"""

import json
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import cast

from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.agent.schemas import ChatScope
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

# 工具预算（contract §3 冻结值）。
MAX_TOOL_CALLS_PER_TURN = 6
TOOL_RESULT_MAX_CHARS = 4_000
TOOL_ROUND_OUTPUT_MAX_CHARS = 12_000


@dataclass
class ToolCallBudget:
    """每轮（每条用户消息）的检索预算累计器：随上下文每轮重建。"""

    calls_used: int = 0
    chars_fed: int = 0


@dataclass
class LibrarySearchContext:
    """范围检索的运行期上下文（每轮生成前绑定，工具执行期读取）。"""

    scope: ChatScope  # RECORD | LIBRARY_ITEM | COURSE | ALL
    course_id: str | None  # 概念扩展与课程边界（RECORD=记录所属课程，ALL=None）
    session_factory: async_sessionmaker[AsyncSession]
    record_id: str | None = None  # RECORD 会话非空
    library_item_id: str | None = None  # LIBRARY_ITEM 会话非空
    budget: ToolCallBudget = field(default_factory=ToolCallBudget)


_library_context: ContextVar[LibrarySearchContext | None] = ContextVar(
    "chat_search_library_context", default=None
)


def bind_library_context(context: LibrarySearchContext) -> Token[LibrarySearchContext | None]:
    return _library_context.set(context)


def reset_library_context(token: Token[LibrarySearchContext | None]) -> None:
    _library_context.reset(token)


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
    if limit <= 0:
        body = {
            "evidence_hits": [],
            "asset_matches": [],
            "concept_hints": [],
            "truncated": True,
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
    budget.chars_fed += len(payload)
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


@tool
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
    context = _library_context.get()
    if context is None:
        return _payload(message="当前对话未挂载资料范围，无法检索。")
    needle = query.strip()
    if not needle:
        return _payload(message="检索词不能为空。")
    if context.budget.calls_used >= MAX_TOOL_CALLS_PER_TURN:
        return _payload(
            message="本轮检索次数已达上限，请基于已获得的检索结果直接回答，并说明检索范围。"
        )
    context.budget.calls_used += 1
    # 检索异常不炸整轮流（同 web_search 先例）：错误载荷 ok=false，模型可据此说明。
    try:
        async with context.session_factory() as session:
            result = await LibraryRetrievalService.search(
                session,
                RetrievalScope(
                    scope=context.scope,
                    record_id=context.record_id,
                    library_item_id=context.library_item_id,
                    course_id=context.course_id,
                ),
                needle,
                SEARCH_LIBRARY_LIMIT,
            )
    except Exception:
        return _payload(message="检索暂时失败，请稍后重试。", ok=False)
    body: dict[str, object] = {
        "evidence_hits": [_hit_payload(hit) for hit in result.evidence_hits],
        "asset_matches": [_asset_payload(match) for match in result.asset_matches],
        "concept_hints": [_concept_payload(hint) for hint in result.concept_hints],
    }
    if not result.evidence_hits:
        body["message"] = (
            "当前范围内未找到相关原文；可换同义词或相关关键词重试（不超过 2 次），"
            "仍无命中请如实回答「当前资料中未找到」。"
        )
    payload, _truncated = _truncate_payload(body, context.budget)
    return payload
