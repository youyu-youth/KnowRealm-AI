"""挂载对话的转写检索工具（chat→search 单向）：分片 FTS 命中 → 逐字原文 + 定位。

检索词经 jieba 分词构造 FTS5 MATCH 找到分片，再回表取逐字 content（引用逐字
校验的根基）；无分片记录（粘贴/速记，F1 有意不建分片）回退 transcript 全文
子串匹配——transcript 恒为事实源。运行期上下文（挂载 record / transcript /
只读会话工厂）由 stream_chat_reply 每轮生成前经 ContextVar 绑定、不在工具实例
上携带，AgentConfig 挂载变体因此保持常量。
"""

import json
from contextvars import ContextVar, Token
from dataclasses import dataclass

from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.search.schemas import SegmentSearchHit
from app.modules.search.segment_service import (
    ENTITY_TRANSCRIPT_SEGMENT,
    SegmentSearchService,
)

SEARCH_TRANSCRIPT_LIMIT = 8
# 兜底命中为整行原文；单行过长（无标点的整段）时以命中词为中心截窗口，控制回喂长度。
FALLBACK_HIT_MAX_CHARS = 400


@dataclass(frozen=True)
class SearchTranscriptContext:
    """挂载材料检索的运行期上下文（每轮生成前绑定，工具执行期读取）。"""

    record_id: str
    transcript: str
    session_factory: async_sessionmaker[AsyncSession]


_search_context: ContextVar[SearchTranscriptContext | None] = ContextVar(
    "chat_search_transcript_context", default=None
)


def bind_search_context(context: SearchTranscriptContext) -> Token[SearchTranscriptContext | None]:
    return _search_context.set(context)


def reset_search_context(token: Token[SearchTranscriptContext | None]) -> None:
    _search_context.reset(token)


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


def _segment_hit_payload(hit: SegmentSearchHit) -> dict[str, object]:
    payload: dict[str, object] = {"content": hit.content, "sequence_no": hit.sequence_no}
    if hit.entity_type == ENTITY_TRANSCRIPT_SEGMENT:
        time_range = _format_time_range(hit.record_start_ms, hit.record_end_ms)
        if time_range is not None:
            payload["time"] = time_range
    elif hit.page_no is not None:
        payload["page"] = hit.page_no
    return payload


def _substring_window(text: str, needle: str) -> str:
    if len(text) <= FALLBACK_HIT_MAX_CHARS:
        return text
    index = text.find(needle)
    start = max(0, index - (FALLBACK_HIT_MAX_CHARS - len(needle)) // 2)
    return text[start : start + FALLBACK_HIT_MAX_CHARS]


def _substring_hits(transcript: str, query: str, limit: int) -> list[dict[str, object]]:
    """transcript 全文子串匹配 → 命中所在行的逐字原文（无分片记录的兜底路径）。"""
    needle = query.strip()
    if not needle:
        return []
    hits: list[dict[str, object]] = []
    seen_line_starts: set[int] = set()
    start = 0
    while len(hits) < limit:
        index = transcript.find(needle, start)
        if index < 0:
            break
        line_start = transcript.rfind("\n", 0, index) + 1
        line_end = transcript.find("\n", index)
        line_end = len(transcript) if line_end < 0 else line_end
        if line_start not in seen_line_starts:
            seen_line_starts.add(line_start)
            hits.append({"content": _substring_window(transcript[line_start:line_end], needle)})
        start = line_end + 1
    return hits


def _payload(hits: list[dict[str, object]], message: str = "") -> str:
    body: dict[str, object] = {"hits": hits}
    if message:
        body["message"] = message
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


@tool
async def search_transcript(query: str) -> str:
    """在本次对话挂载的学习材料（课堂转写、文档）中检索原文片段。

    当问题的细节不在当前上下文（材料很长或只提供了摘要）时使用：用 2~6 个
    关键词描述要找的内容，命中结果是材料中的逐字原文，可直接作为引用（引用
    时逐字照抄命中内容、不超过 80 字）。没有命中就换同义词或相关词重试；
    不要编造材料中不存在的内容。
    """
    context = _search_context.get()
    if context is None:
        return _payload([], "当前对话未挂载学习材料，无法检索。")
    async with context.session_factory() as session:
        hits = await SegmentSearchService.search_segments(
            session, context.record_id, query, SEARCH_TRANSCRIPT_LIMIT
        )
        if hits:
            return _payload([_segment_hit_payload(hit) for hit in hits])
        if await SegmentSearchService.record_has_segments(session, context.record_id):
            # 有分片索引记录：FTS 无命中即如实返回，不做子串兜底（spec：兜底仅限无分片记录）。
            return _payload([], "未找到相关原文；可换同义词或相关关键词重试。")
    fallback = _substring_hits(context.transcript, query, SEARCH_TRANSCRIPT_LIMIT)
    if fallback:
        return _payload(fallback)
    return _payload([], "未找到相关原文；可换同义词或相关关键词重试。")
