"""对话发消息：受理（校验 / 补答 / user 落库）与 SSE 流式事件生成。"""

import asyncio
import json
from collections.abc import AsyncGenerator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from langchain_core.messages import AnyMessage
from langgraph.checkpoint.base import BaseCheckpointSaver  # pyright: ignore[reportMissingTypeStubs]
from loguru import logger
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sse_starlette import ServerSentEvent

from app.db.base import utcnow
from app.modules.agent.citations import (
    LibraryRecordMaterial,
    parse_citation_reply,
    parse_library_citation_reply,
)
from app.modules.agent.context import (
    CHAT_TRANSCRIPT_MAX_CHARS,
    ChatContextTooLargeError,
    ContextRow,
    LibraryContext,
    LibraryRecordRow,
    MountedMaterial,
    RecordContext,
    build_context_messages,
)
from app.modules.agent.graph import (
    ChatStreamOutcome,
    ChatTokenEvent,
    ChatToolCallEvent,
    stream_chat_reply,
)
from app.modules.agent.models import ChatMessage, ChatSession
from app.modules.agent.schemas import ChatRole, ChatScope
from app.modules.agent.session_service import ChatSessionService
from app.modules.agent.tools.search_library import LibrarySearchContext
from app.modules.course.models import Course
from app.modules.knowledge_point.models import KnowledgePoint
from app.modules.knowledge_point.schemas import KnowledgePointGenerationStatus
from app.modules.record.models import Record
from app.modules.record.service import RecordService
from app.modules.search.integrations.tavily import TavilySearchClient
from app.modules.search.web_search import SearchProvider
from app.modules.settings.config import (
    LlmProviderConfig,
    load_llm_provider,
    load_web_search_config,
)
from app.modules.summary.models import AiSummary
from app.modules.summary.schemas import AiSummaryStatus
from app.modules.transcript.models import Transcript
from app.shared.errors import CodedHTTPException

# 会话标题默认取首条用户消息的截断长度。
CHAT_TITLE_MAX_CHARS = 30

STREAM_STATUS_GENERATING = "generating"


class ChatStreamRegistry:
    """同一会话同时只允许一条在途生成（进程内状态；sidecar 单进程）。

    锁的配对唯一：accept 内 acquire（受理失败即在 accept 内释放），
    受理成功后由 stream_events 的 finally 释放（锁生命周期 = SSE 流生命周期，
    跨函数边界，contextmanager 无法覆盖）。
    """

    def __init__(self) -> None:
        self._active: set[str] = set()

    def acquire(self, session_id: str) -> bool:
        if session_id in self._active:
            return False
        self._active.add(session_id)
        return True

    def release(self, session_id: str) -> None:
        self._active.discard(session_id)


@dataclass(frozen=True)
class AcceptedMessage:
    """受理结果：user 行已落库（或补答复用），流式生成从这里开始。

    web_search 为当轮生效的搜索客户端：请求标志开启且已配置可用 key 才非空
    （无 key 时后端无视标志强制不挂工具，B1 双保险）。
    """

    session_id: str
    user_row_id: str
    content: str
    provider: LlmProviderConfig
    web_search: SearchProvider | None = None


@dataclass(frozen=True)
class SessionPromptContext:
    """喂入 LLM 的上下文与挂载会话的引用校验材料。"""

    messages: list[AnyMessage]
    scope: ChatScope = ChatScope.FREE
    transcript: str | None = None  # 挂载会话的当前转写全文；自由聊天为 None
    record_id: str | None = None
    course_id: str | None = None  # COURSE 会话挂载的课程
    library: LibraryContext | None = None  # COURSE/ALL 会话的记录标题清单
    web_search: bool = False  # 本轮联网生效（已含 key 双保险）；自由聊天也可为 True

    @property
    def mounted(self) -> MountedMaterial | None:
        """挂载材料（record_id 与 transcript 成对）；自由聊天或半对时为 None。"""
        if self.record_id is None or self.transcript is None:
            return None
        return MountedMaterial(record_id=self.record_id, transcript=self.transcript)

    @property
    def should_parse_citations(self) -> bool:
        """挂载与跨范围会话恒解析引用块；自由聊天仅本轮联网时解析（产出 web 条目）。"""
        return self.record_id is not None or self.library is not None or self.web_search


def _sse(event: str, payload: Mapping[str, object]) -> ServerSentEvent:
    return ServerSentEvent(event=event, data=json.dumps(payload, separators=(",", ":")))


async def _last_message(session: AsyncSession, session_id: str) -> ChatMessage | None:
    return await session.scalar(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(1)
    )


async def _course_available(session: AsyncSession, chat: ChatSession) -> bool:
    """COURSE 会话挂载课程是否存活（软删即失效，对齐 record_deleted 先例）。"""
    if chat.course_id is None:
        return False
    course = await session.get(Course, chat.course_id)
    return course is not None and course.deleted_at is None


def _scope_record_filters(scope: ChatScope, course_id: str | None) -> list[Any]:
    """范围条件：COURSE = 该课程全部未软删记录；ALL = 全部未软删记录（含收件箱，
    软删课程下的记录随课程排除，口径同 record_options）。"""
    if scope == ChatScope.COURSE:
        return [Record.deleted_at.is_(None), Record.course_id == course_id]
    return [
        Record.deleted_at.is_(None),
        or_(
            Record.course_id.is_(None),
            and_(Course.id.is_not(None), Course.deleted_at.is_(None)),
        ),
    ]


async def _scope_library_rows(
    session: AsyncSession, scope: ChatScope, course_id: str | None
) -> list[tuple[str, str, Any, bool]]:
    """课程 / 全部范围的记录行（updated_at 降序）：(id, title, updated_at, has_transcript)。"""
    stmt = (
        select(
            Record.id,
            Record.title,
            Record.updated_at,
            Transcript.id.is_not(None).label("has_transcript"),
        )
        .outerjoin(
            Transcript,
            and_(Transcript.record_id == Record.id, Transcript.deleted_at.is_(None)),
        )
        .outerjoin(Course, Course.id == Record.course_id)
        .where(*_scope_record_filters(scope, course_id))
        .order_by(Record.updated_at.desc(), Record.id.desc())
    )
    rows = (await session.execute(stmt)).all()
    return [(str(row.id), str(row.title), row.updated_at, bool(row.has_transcript)) for row in rows]


async def _load_library_context(
    session: AsyncSession, scope: ChatScope, course_id: str | None
) -> LibraryContext:
    """课程 / 全部范围的清单上下文（只含标题 + 日期 + 有无转写，不携带正文）。"""
    if scope == ChatScope.COURSE:
        course = await session.get(Course, course_id or "")
        scope_label = f"课程「{course.name}」" if course is not None else "课程"
    else:
        scope_label = "全部资料"
    rows = await _scope_library_rows(session, scope, course_id)
    return LibraryContext(
        scope_label=scope_label,
        records=tuple(
            LibraryRecordRow(
                title=title,
                updated_date=updated_at.strftime("%Y-%m-%d"),
                has_transcript=has_transcript,
            )
            for _id, title, updated_at, has_transcript in rows
        ),
    )


async def _load_library_materials(
    session_factory: async_sessionmaker[AsyncSession],
    scope: ChatScope,
    course_id: str | None,
) -> list[LibraryRecordMaterial]:
    """跨记录引用校验材料：范围内全部未软删记录的转写全文（个人量级，#24 背书）。"""
    async with session_factory() as session:
        stmt = (
            select(Record.id, Record.title, Transcript.content)
            .join(
                Transcript,
                and_(Transcript.record_id == Record.id, Transcript.deleted_at.is_(None)),
            )
            .outerjoin(Course, Course.id == Record.course_id)
            .where(*_scope_record_filters(scope, course_id))
            .order_by(Record.updated_at.desc(), Record.id.desc())
        )
        rows = (await session.execute(stmt)).all()
        return [
            LibraryRecordMaterial(
                record_id=str(row.id), title=str(row.title), transcript=str(row.content)
            )
            for row in rows
        ]


async def _session_context(
    session_factory: async_sessionmaker[AsyncSession], session_id: str, *, web_search: bool = False
) -> SessionPromptContext:
    async with session_factory() as session:
        chat = await ChatSessionService.get(session, session_id)
        if chat is None:
            raise CodedHTTPException(
                code="CHAT_SESSION_NOT_FOUND", status_code=404, detail="对话不存在或已删除"
            )
        if chat.scope == ChatScope.COURSE and not await _course_available(session, chat):
            # 失效态运行时推导：挂载课程软删后流式上下文拒绝组装（accept 已先拦一道）。
            raise CodedHTTPException(
                code="CHAT_COURSE_UNAVAILABLE",
                status_code=409,
                detail="CHAT_COURSE_UNAVAILABLE：课程已删除，对话已失效",
            )
        rows = (
            await session.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at, ChatMessage.id)
            )
        ).all()
        record_context = None
        transcript_text: str | None = None
        record_id: str | None = None
        library_context: LibraryContext | None = None
        if chat.record_id is not None:
            record = await RecordService.get(session, chat.record_id)
            if record is None:
                raise CodedHTTPException(
                    code="CHAT_RECORD_UNAVAILABLE",
                    status_code=409,
                    detail="CHAT_RECORD_UNAVAILABLE：原记录已删除",
                )
            transcript = await RecordService.get_transcript(session, record.id)
            if transcript is None:
                raise CodedHTTPException(
                    code="TRANSCRIPT_NOT_READY",
                    status_code=409,
                    detail="TRANSCRIPT_NOT_READY：转写尚未生成",
                )
            record_context = RecordContext(transcript=transcript.content)
            transcript_text = transcript.content
            record_id = record.id
            if len(transcript.content) > CHAT_TRANSCRIPT_MAX_CHARS:
                summary = await session.scalar(
                    select(AiSummary)
                    .where(
                        AiSummary.record_id == record.id,
                        AiSummary.deleted_at.is_(None),
                        AiSummary.status == AiSummaryStatus.CONFIRMED,
                        AiSummary.transcript_source_version == transcript.source_version,
                    )
                    .order_by(AiSummary.version_no.desc())
                    .limit(1)
                )
                points = (
                    await session.scalars(
                        select(KnowledgePoint)
                        .where(
                            KnowledgePoint.record_id == record.id,
                            KnowledgePoint.deleted_at.is_(None),
                            KnowledgePoint.generation_status
                            == KnowledgePointGenerationStatus.ACTIVE,
                        )
                        .order_by(KnowledgePoint.created_at, KnowledgePoint.id)
                    )
                ).all()
                record_context = RecordContext(
                    transcript=transcript.content,
                    summary=(
                        f"{summary.topic}\n{summary.abstract}\n"
                        + json.dumps(json.loads(summary.summary_json), ensure_ascii=False)
                    )
                    if summary is not None
                    else "",
                    knowledge_points="\n\n".join(
                        f"{point.name}\n{point.detail}" for point in points
                    ),
                )
        elif chat.scope in (ChatScope.COURSE, ChatScope.ALL):
            library_context = await _load_library_context(session, chat.scope, chat.course_id)
        return SessionPromptContext(
            scope=chat.scope,
            messages=build_context_messages(
                [
                    ContextRow(
                        id=row.id,
                        role=row.role,
                        content=row.content,
                        cited_excerpts=_cited_excerpts(row.citations_json, chat.record_id),
                    )
                    for row in rows
                ],
                record=record_context,
                library=library_context,
                web_search=web_search,
            ),
            transcript=transcript_text,
            record_id=record_id,
            course_id=chat.course_id if chat.scope == ChatScope.COURSE else None,
            library=library_context,
            web_search=web_search,
        )


def _cited_excerpts(raw: str | None, record_id: str | None) -> tuple[str, ...]:
    """消费 citations_json 的 quote（限本记录、≤80 字），供长转写时回喂近三轮引用摘录。"""
    if raw is None or record_id is None:
        return ()
    try:
        value = cast(object, json.loads(raw))
    except ValueError:
        return ()
    if not isinstance(value, list):
        return ()
    excerpts: list[str] = []
    for entry in cast(list[object], value):
        if not isinstance(entry, dict):
            continue
        item = cast(dict[str, object], entry)
        quote = item.get("quote")
        if item.get("record_id") == record_id and isinstance(quote, str) and 0 < len(quote) <= 80:
            excerpts.append(quote)
    return tuple(excerpts)


class ChatMessageService:
    @staticmethod
    async def list_messages(session: AsyncSession, session_id: str) -> list[ChatMessage] | None:
        """按时间顺序返回会话全部消息；会话不存在或已删返回 None。"""
        chat = await ChatSessionService.get(session, session_id)
        if chat is None:
            return None
        return list(
            (
                await session.scalars(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session_id)
                    .order_by(ChatMessage.created_at, ChatMessage.id)
                )
            ).all()
        )

    @staticmethod
    async def accept(
        *,
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
        registry: ChatStreamRegistry,
        session_id: str,
        content: str,
        web_search: bool = False,
    ) -> AcceptedMessage:
        """受理发送：校验供应商与在途状态，落库 user 行（补答复用原行）。

        web_search 标志仅在已配置可用 key 时生效（无 key 强制不挂工具）。
        """
        provider = await asyncio.to_thread(load_llm_provider, data_dir)
        if provider is None or not provider.api_key:
            raise CodedHTTPException(
                code="LLM_PROVIDER_UNCONFIGURED",
                status_code=409,
                detail="LLM_PROVIDER_UNCONFIGURED：未配置 AI 服务，请先完成供应商配置",
            )
        web_search_provider: SearchProvider | None = None
        if web_search:
            config = await asyncio.to_thread(load_web_search_config, data_dir)
            if config is not None:
                web_search_provider = TavilySearchClient(config.api_key)
        if not registry.acquire(session_id):
            raise CodedHTTPException(
                code="CHAT_STREAM_IN_PROGRESS",
                status_code=409,
                detail="CHAT_STREAM_IN_PROGRESS：该对话正在生成回答，请稍候",
            )
        try:
            async with session_factory() as session, session.begin():
                chat = await ChatSessionService.get(session, session_id)
                if chat is None:
                    raise CodedHTTPException(
                        code="CHAT_SESSION_NOT_FOUND", status_code=404, detail="对话不存在或已删除"
                    )
                if (
                    chat.record_id is not None
                    and (await RecordService.get(session, chat.record_id)) is None
                ):
                    # 失效态运行时推导：挂载记录软删后发送被拒，会话只读。
                    raise CodedHTTPException(
                        code="CHAT_RECORD_UNAVAILABLE",
                        status_code=409,
                        detail="CHAT_RECORD_UNAVAILABLE：原记录已删除，对话已失效",
                    )
                if chat.scope == ChatScope.COURSE and not await _course_available(session, chat):
                    # 失效态运行时推导：挂载课程软删后发送被拒，会话只读。
                    raise CodedHTTPException(
                        code="CHAT_COURSE_UNAVAILABLE",
                        status_code=409,
                        detail="CHAT_COURSE_UNAVAILABLE：课程已删除，对话已失效",
                    )
                last = await _last_message(session, session_id)
                if last is not None and last.role == ChatRole.USER:
                    # 补答：会话末尾是无回复的 user 消息，复用原行重新生成，不重复落库。
                    last.content = content
                    user_row_id = last.id
                else:
                    user_row_id = str(uuid4())
                    session.add(
                        ChatMessage(
                            id=user_row_id,
                            session_id=session_id,
                            role=ChatRole.USER,
                            content=content,
                            citations_json=None,
                            model=None,
                            token_usage_json=None,
                            created_at=utcnow(),
                        )
                    )
                if chat.title is None:
                    chat.title = content[:CHAT_TITLE_MAX_CHARS]
                chat.updated_at = utcnow()
                await session.flush()
        except BaseException:
            registry.release(session_id)
            raise
        return AcceptedMessage(
            session_id=session_id,
            user_row_id=user_row_id,
            content=content,
            provider=provider,
            web_search=web_search_provider,
        )

    @staticmethod
    async def stream_events(
        *,
        session_factory: async_sessionmaker[AsyncSession],
        checkpointer: BaseCheckpointSaver[str],
        registry: ChatStreamRegistry,
        accepted: AcceptedMessage,
    ) -> AsyncGenerator[ServerSentEvent, None]:
        """流式生成回答：status → token… → done / error；中断不落库、finally 释放锁。"""
        session_id = accepted.session_id
        try:
            yield _sse("status", {"phase": STREAM_STATUS_GENERATING})
            outcome = ChatStreamOutcome()
            parts: list[str] = []
            try:
                prompt_context = await _session_context(
                    session_factory, session_id, web_search=accepted.web_search is not None
                )
                # 课程 / 全部范围：绑定跨记录检索范围（与挂载互斥，见 stream_chat_reply）。
                library_binding = (
                    LibrarySearchContext(
                        scope=prompt_context.scope,
                        course_id=prompt_context.course_id,
                        session_factory=session_factory,
                    )
                    if prompt_context.library is not None
                    else None
                )
                async for event in stream_chat_reply(
                    session_factory=session_factory,
                    checkpointer=checkpointer,
                    provider=accepted.provider,
                    context_messages=prompt_context.messages,
                    session_id=session_id,
                    outcome=outcome,
                    mounted=prompt_context.mounted,
                    library=library_binding,
                    web_search=accepted.web_search,
                ):
                    if isinstance(event, ChatTokenEvent):
                        parts.append(event.text)
                        yield _sse("token", {"text": event.text})
                    elif isinstance(event, ChatToolCallEvent):
                        yield _sse("tool_call", {"tool": event.tool, "query": event.query})
                    else:
                        yield _sse(
                            "tool_result",
                            {"tool": event.tool, "hits": event.hits, "ok": event.ok},
                        )
            except ChatContextTooLargeError:
                yield _sse(
                    "error",
                    {
                        "code": "CHAT_CONTEXT_TOO_LARGE",
                        "detail": "摘要与知识点仍超过上下文预算，请精简材料后重试",
                    },
                )
                return
            except Exception:
                logger.error(
                    "chat_generation_failed", session_id=session_id, error_code="CHAT_STREAM_FAILED"
                )
                yield _sse(
                    "error",
                    {"code": "CHAT_STREAM_FAILED", "detail": "回答生成失败，请稍后重试"},
                )
                return
            content = "".join(parts)
            if not content:
                yield _sse("error", {"code": "EMPTY_REPLY", "detail": "回答为空，请重试"})
                return
            # 引用块解析：挂载与跨范围对话恒解析（转写摘录逐字校验、跨记录条目按
            # 「（来源：标题）」裁定归属）；自由聊天仅本轮联网时解析（产出 web 条目）。
            citations: list[dict[str, int | str]] = []
            if prompt_context.should_parse_citations:
                if prompt_context.library is not None:
                    materials = await _load_library_materials(
                        session_factory, prompt_context.scope, prompt_context.course_id
                    )
                    parsed = parse_library_citation_reply(content, materials)
                else:
                    parsed = parse_citation_reply(
                        content,
                        transcript=prompt_context.transcript or "",
                        record_id=prompt_context.record_id or "",
                    )
                content = parsed.content
                citations = parsed.citations
            if not content:
                yield _sse("error", {"code": "EMPTY_REPLY", "detail": "回答为空，请重试"})
                return
            for citation in citations:
                yield _sse("citation", citation)
            assistant_id = str(uuid4())
            async with session_factory() as session, session.begin():
                session.add(
                    ChatMessage(
                        id=assistant_id,
                        session_id=session_id,
                        role=ChatRole.ASSISTANT,
                        content=content,
                        citations_json=json.dumps(citations, separators=(",", ":"))
                        if citations
                        else None,
                        model=accepted.provider.model,
                        token_usage_json=json.dumps(outcome.token_usage, separators=(",", ":"))
                        if outcome.token_usage
                        else None,
                        created_at=utcnow(),
                    )
                )
                chat = await ChatSessionService.get(session, session_id)
                if chat is not None:
                    chat.updated_at = utcnow()
            yield _sse("done", {"message_id": assistant_id, "content": content})
        finally:
            registry.release(session_id)
