"""课程 / 全部范围会话的跨记录检索工具（B2，chat→search 单向）。

与 search_transcript 互斥挂载：RECORD 会话只挂 search_transcript，
COURSE/ALL 只挂本工具，FREE 不挂。检索 = 跨记录分片 FTS（命中带归属记录
标题与时间 / 页码）→ FTS 零命中才 LIKE 兜底（整 query 子串，覆盖粘贴 /
速记等无分片记录）。运行期范围由 stream_chat_reply 每轮生成前经
ContextVar 绑定，AgentConfig 挂载变体保持常量。
"""

import json
from contextvars import ContextVar, Token
from dataclasses import dataclass

from langchain_core.tools import tool
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.agent.schemas import ChatScope
from app.modules.search.schemas import LibrarySegmentSearchHit
from app.modules.search.segment_service import (
    ENTITY_TRANSCRIPT_SEGMENT,
    SegmentSearchService,
)

SEARCH_LIBRARY_LIMIT = 8
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


def _hit_payload(hit: LibrarySegmentSearchHit) -> dict[str, object]:
    payload: dict[str, object] = {
        "record_id": hit.record_id,
        "record_title": hit.record_title,
        "content": hit.content,
    }
    if hit.entity_type == ENTITY_TRANSCRIPT_SEGMENT:
        time_range = _format_time_range(hit.record_start_ms, hit.record_end_ms)
        if time_range is not None:
            payload["time"] = time_range
    elif hit.page_no is not None:
        payload["page"] = hit.page_no
    return payload


def _escape_like(needle: str) -> str:
    return needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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


def _payload(hits: list[dict[str, object]], message: str = "") -> str:
    body: dict[str, object] = {"hits": hits}
    if message:
        body["message"] = message
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


@tool
async def search_library(query: str) -> str:
    """在本次对话范围的学习资料（多条记录的转写与文档）中检索原文片段。

    当问题涉及范围内任意记录的细节、或需要跨记录对比时使用：用 2~6 个
    关键词描述要找的内容，命中结果带所属记录标题与逐字原文，可直接作为
    引用（引用时逐字照抄命中内容、不超过 80 字，并注明来源记录标题）。
    没有命中就换同义词或相关词重试；不要编造资料中不存在的内容。
    """
    context = _library_context.get()
    if context is None:
        return _payload([], "当前对话未挂载资料范围，无法检索。")
    needle = query.strip()
    if not needle:
        return _payload([], "检索词不能为空。")
    async with context.session_factory() as session:
        hits = await SegmentSearchService.search_scope_segments(
            session, context.course_id, query, SEARCH_LIBRARY_LIMIT
        )
        if hits:
            return _payload([_hit_payload(hit) for hit in hits])
        rows = (
            await session.execute(
                _SCOPE_TRANSCRIPT_LIKE_SQL,
                {
                    "course_id": context.course_id,
                    "needle": _escape_like(needle),
                    "limit": SEARCH_LIBRARY_LIMIT,
                },
            )
        ).all()
    fallback = _like_fallback_hits(
        [(str(row.record_id), str(row.record_title), str(row.content)) for row in rows],
        needle,
        SEARCH_LIBRARY_LIMIT,
    )
    if fallback:
        return _payload(fallback)
    return _payload([], "未找到相关原文；可换同义词或相关关键词重试。")
