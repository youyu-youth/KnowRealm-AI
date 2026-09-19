"""课程 / 全部范围会话的跨记录检索工具（B2 + CB-07 概念增强，chat→search 单向）。

与 search_transcript 互斥挂载：RECORD 会话只挂 search_transcript，
COURSE/ALL 只挂本工具，FREE 不挂。检索 = 概念 FTS 命中（CONFIRMED-only，
top 4）→ 原查询 + 各概念名并跑分片 FTS（概念只在其归属课程内扩展，每词
top 8）→ 合并去重（record_id+content）→ FTS 零命中才 LIKE 兜底（整 query
子串，覆盖粘贴 / 速记等无分片记录）。运行期范围由 stream_chat_reply 每轮
生成前经 ContextVar 绑定，AgentConfig 挂载变体保持常量。
"""

import json
from contextvars import ContextVar, Token
from dataclasses import dataclass

from langchain_core.tools import tool
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.agent.schemas import ChatScope
from app.modules.course_brain.schemas import BrainSearchConceptOut
from app.modules.course_brain.service import CourseBrainService
from app.modules.search.schemas import LibrarySegmentSearchHit
from app.modules.search.segment_service import (
    ENTITY_TRANSCRIPT_SEGMENT,
    SegmentSearchService,
)
from app.modules.search.tokenizer import escape_like

SEARCH_LIBRARY_LIMIT = 8
# 概念扩展（CB-07）：命中概念数与每个扩展词的分片命中上限（spec B2 检索增强）。
CONCEPT_MATCH_LIMIT = 4
_EXPANSION_PER_TERM_LIMIT = 8
# occurrences 按 record 去重后的代表摘录限长（引用仍以 hits 逐字原文为准）。
_OCCURRENCE_QUOTE_LIMIT = 80
# LIKE 兜底命中为整行原文；单行过长时以命中词为中心截窗口，控制回喂长度。
FALLBACK_HIT_MAX_CHARS = 400

# LIKE 兜底：范围内逐记录子串扫描（transcript 恒为事实源；无分片记录也覆盖）。
_SCOPE_TRANSCRIPT_LIKE_SQL = text(
    "SELECT r.id AS record_id, r.title AS record_title, t.content "
    "FROM transcripts t "
    "JOIN records r ON r.id = t.record_id AND r.deleted_at IS NULL "
    "WHERE t.deleted_at IS NULL "
    "AND (:course_id IS NULL OR r.course_id = :course_id) "
    "AND t.content LIKE '%' || :needle || '%' ESCAPE '\\' "
    "ORDER BY r.updated_at DESC, r.id DESC "
    "LIMIT :limit"
)


@dataclass(frozen=True)
class LibrarySearchContext:
    """跨记录检索的运行期上下文（每轮生成前绑定，工具执行期读取）。"""

    scope: ChatScope  # COURSE | ALL
    course_id: str | None  # COURSE 会话非空
    session_factory: async_sessionmaker[AsyncSession]


_library_context: ContextVar[LibrarySearchContext | None] = ContextVar(
    "chat_search_library_context", default=None
)


def bind_library_context(context: LibrarySearchContext) -> Token[LibrarySearchContext | None]:
    return _library_context.set(context)


def reset_library_context(token: Token[LibrarySearchContext | None]) -> None:
    _library_context.reset(token)


def _format_timestamp(ms: int) -> str:
    total_seconds = max(0, ms) // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _format_time_range(start_ms: int | None, end_ms: int | None) -> str | None:
    start = _format_timestamp(start_ms) if start_ms is not None else None
    end = _format_timestamp(end_ms) if end_ms is not None else None
    if start is None:
        return end
    if end is None or end == start:
        return start
    return f"{start}-{end}"


def _locator_fields(hit: LibrarySegmentSearchHit) -> dict[str, object]:
    """锚点定位字段：转写分片带时间区间，文档分片带页码（无则为空）。"""
    if hit.entity_type == ENTITY_TRANSCRIPT_SEGMENT:
        time_range = _format_time_range(hit.record_start_ms, hit.record_end_ms)
        return {"time": time_range} if time_range is not None else {}
    return {"page": hit.page_no} if hit.page_no is not None else {}


def _hit_payload(hit: LibrarySegmentSearchHit) -> dict[str, object]:
    payload: dict[str, object] = {
        "record_id": hit.record_id,
        "record_title": hit.record_title,
        "content": hit.content,
    }
    payload.update(_locator_fields(hit))
    return payload


def _concept_payload(concept: BrainSearchConceptOut) -> dict[str, object]:
    return {
        "concept_id": concept.concept_id,
        "canonical_name": concept.canonical_name,
        "description": concept.description,
        "record_count": concept.record_count,
        "occurrence_count": concept.occurrence_count,
    }


def _occurrence_payload(hit: LibrarySegmentSearchHit) -> dict[str, object]:
    """按 record 去重后的代表命中：一条记录一条，供「讲过几次」计数。"""
    payload: dict[str, object] = {
        "record_id": hit.record_id,
        "record_title": hit.record_title,
        "quote": hit.content[:_OCCURRENCE_QUOTE_LIMIT],
    }
    payload.update(_locator_fields(hit))
    return payload


def _substring_window(line: str, needle: str) -> str:
    if len(line) <= FALLBACK_HIT_MAX_CHARS:
        return line
    index = line.find(needle)
    start = max(0, index - (FALLBACK_HIT_MAX_CHARS - len(needle)) // 2)
    return line[start : start + FALLBACK_HIT_MAX_CHARS]


def _like_fallback_hits(
    rows: list[tuple[str, str, str]], query: str, limit: int
) -> list[dict[str, object]]:
    """LIKE 命中记录 → 每条记录取首个含命中词的行（窗口 ≤400 字）。"""
    needle = query.strip()
    hits: list[dict[str, object]] = []
    for record_id, record_title, content in rows:
        if len(hits) >= limit:
            break
        index = content.find(needle)
        if index < 0:
            continue
        line_start = content.rfind("\n", 0, index) + 1
        line_end = content.find("\n", index)
        line_end = len(content) if line_end < 0 else line_end
        hits.append(
            {
                "record_id": record_id,
                "record_title": record_title,
                "content": _substring_window(content[line_start:line_end], needle),
            }
        )
    return hits


def _payload(
    hits: list[dict[str, object]],
    concepts: list[dict[str, object]] | None = None,
    occurrences: list[dict[str, object]] | None = None,
    message: str = "",
    *,
    ok: bool = True,
) -> str:
    body: dict[str, object] = {
        "hits": hits,
        "concepts": concepts if concepts is not None else [],
        "occurrences": occurrences if occurrences is not None else [],
    }
    if message:
        body["message"] = message
    if not ok:
        body["ok"] = False
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


@tool
async def search_library(query: str) -> str:
    """在本次对话范围的学习资料（多条记录的转写与文档）中检索原文片段。

    当问题涉及范围内任意记录的细节、或需要跨记录对比时使用：用 2~6 个
    关键词描述要找的内容，命中结果带所属记录标题与逐字原文，可直接作为
    引用（引用时逐字照抄命中内容、不超过 80 字，并注明来源记录标题）。
    返回中的 concepts 是范围内已确认的课程概念（含描述与出现计数），可帮
    你理解术语；occurrences 是按记录去重后的出现明细（一条记录一条）。
    没有命中就换同义词或相关词重试；不要编造资料中不存在的内容。
    """
    context = _library_context.get()
    if context is None:
        return _payload([], [], [], "当前对话未挂载资料范围，无法检索。")
    needle = query.strip()
    if not needle:
        return _payload([], [], [], "检索词不能为空。")
    # FTS 异常不炸整轮流（同 web_search 先例）：错误载荷 ok=false，模型可据此说明。
    try:
        async with context.session_factory() as session:
            concepts = await CourseBrainService.match_concepts(
                session, context.course_id, needle, CONCEPT_MATCH_LIMIT
            )
            # 原查询（会话范围）+ 各命中概念名（只在其归属课程内）并跑；ALL 不跨课程混入。
            terms: list[tuple[str, str | None, int]] = [
                (needle, context.course_id, SEARCH_LIBRARY_LIMIT)
            ]
            terms.extend(
                (concept.canonical_name, concept.course_id, _EXPANSION_PER_TERM_LIMIT)
                for concept in concepts
            )
            seen: set[tuple[str, str]] = set()
            merged: list[LibrarySegmentSearchHit] = []
            for term, scope_course_id, per_term_limit in terms:
                for hit in await SegmentSearchService.search_scope_segments(
                    session, scope_course_id, term, per_term_limit
                ):
                    key = (hit.record_id, hit.content)
                    if key not in seen:
                        seen.add(key)
                        merged.append(hit)
            if merged:
                occurrences: list[dict[str, object]] = []
                seen_records: set[str] = set()
                for hit in merged:
                    if hit.record_id in seen_records:
                        continue
                    seen_records.add(hit.record_id)
                    occurrences.append(_occurrence_payload(hit))
                return _payload(
                    [_hit_payload(hit) for hit in merged[:SEARCH_LIBRARY_LIMIT]],
                    [_concept_payload(concept) for concept in concepts],
                    occurrences,
                )
            rows = (
                await session.execute(
                    _SCOPE_TRANSCRIPT_LIKE_SQL,
                    {
                        "course_id": context.course_id,
                        "needle": escape_like(needle),
                        "limit": SEARCH_LIBRARY_LIMIT,
                    },
                )
            ).all()
    except Exception:
        return _payload([], [], [], "检索暂时失败，请稍后重试。", ok=False)
    fallback = _like_fallback_hits(
        [(str(row.record_id), str(row.record_title), str(row.content)) for row in rows],
        needle,
        SEARCH_LIBRARY_LIMIT,
    )
    if fallback:
        # LIKE 兜底仍带上已命中的概念（模型理解术语用）；occurrences 仅 FTS 面提供。
        return _payload(fallback, [_concept_payload(concept) for concept in concepts], [])
    return _payload([], [], [], "未找到相关原文；可换同义词或相关关键词重试。")
