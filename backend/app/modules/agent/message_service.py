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
    LibraryItemMaterial,
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
    RecordContext,
    build_context_messages,
)
from app.modules.agent.graph import (
    CHAT_PROMPT_VERSION,
    CHAT_RESEARCH_PROMPT_VERSION,
    ChatMemoryProposalEvent,
    ChatResearchProposalEvent,
    ChatStreamOutcome,
    ChatTokenEvent,
    ChatToolCallEvent,
    stream_chat_reply,
)
from app.modules.agent.models import ChatMessage, ChatSession
from app.modules.agent.schemas import ChatMode, ChatRole, ChatScope
from app.modules.agent.session_service import ChatSessionService
from app.modules.agent.tools.propose_ingest import ResearchIngestContext
from app.modules.agent.tools.propose_memory import MemoryProposalContext
from app.modules.agent.tools.search_library import LibrarySearchContext, ToolCallBudget
from app.modules.course.models import Course
from app.modules.knowledge_point.models import KnowledgePoint
from app.modules.knowledge_point.schemas import KnowledgePointGenerationStatus
from app.modules.learner.service import build_learner_context
from app.modules.library.models import LibraryItem, LibraryItemRecord
from app.modules.record.models import Record
from app.modules.record.service import RecordService
from app.modules.search.integrations.tavily import TavilySearchClient
from app.modules.search.web_search import SearchProvider
from app.modules.settings.config import (
    LlmProviderConfig,
    llm_consent,
    load_llm_provider,
    load_web_search_config,
    memory_outbound_enabled,
)
from app.modules.summary.models import AiSummary
from app.modules.summary.schemas import AiSummaryStatus
from app.modules.transcript.models import DocumentSegment, Transcript
from app.shared.errors import CodedHTTPException

# 会话标题默认取首条用户消息的截断长度。
CHAT_TITLE_MAX_CHARS = 30

STREAM_STATUS_GENERATING = "generating"

# 挂载检索工具的范围（工单 04：五档中 FREE 外统一挂 search_library）。
RETRIEVAL_SCOPES = frozenset(
    {
        ChatScope.RECORD,
        ChatScope.LIBRARY_ITEM,
        ChatScope.COURSE,
        ChatScope.ALL,
    }
)


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
    memory_injection_allowed = 记忆外发开关开启且 LLM 外发同意对当前供应商
    有效（工单 06）；False 时本轮零记忆注入（硬门禁：关闭外发后零发送）。
    """

    session_id: str
    user_row_id: str
    content: str
    provider: LlmProviderConfig
    web_search: SearchProvider | None = None
    memory_injection_allowed: bool = False


@dataclass(frozen=True)
class SessionPromptContext:
    """喂入 LLM 的上下文与范围会话的引用校验材料。"""

    messages: list[AnyMessage]
    mode: ChatMode = ChatMode.ASK  # 研究会话（RESEARCH）换研究指令与提案工具
    scope: ChatScope = ChatScope.FREE
    transcript: str | None = None  # 挂载会话的当前转写全文；自由聊天为 None
    record_id: str | None = None
    # 检索边界课程：COURSE=挂载课程；RECORD/LIBRARY_ITEM=挂载对象所属课程（概念
    # 扩展用）；ALL=None。
    course_id: str | None = None
    library: LibraryContext | None = None  # COURSE/ALL/LIBRARY_ITEM 的清单上下文
    library_item_id: str | None = None  # LIBRARY_ITEM 会话挂载的资料条目
    web_search: bool = False  # 本轮联网生效（已含 key 双保险）；自由聊天也可为 True
    learner: str | None = None  # 本轮注入的学习者记忆块（None=未注入）
    learner_memories: tuple[str, ...] = ()  # 实际注入的记忆条目（done 透传 UI 展示）

    @property
    def learner_injected(self) -> bool:
        return bool(self.learner)

    @property
    def should_parse_citations(self) -> bool:
        """挂载与范围会话恒解析引用块；自由聊天仅本轮联网时解析（产出 web 条目）。"""
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


def _library_item_unavailable_error() -> CodedHTTPException:
    return CodedHTTPException(
        code="CHAT_LIBRARY_ITEM_UNAVAILABLE",
        status_code=409,
        detail="CHAT_LIBRARY_ITEM_UNAVAILABLE：原资料已删除或归档，对话已失效",
    )


async def _require_library_item(session: AsyncSession, item_id: str | None) -> LibraryItem:
    """LIBRARY_ITEM 会话挂载资料存活校验：不存在/软删/归档一律失效（会话只读）。"""
    item = await session.get(LibraryItem, item_id or "")
    if item is None or item.deleted_at is not None or item.status == "ARCHIVED":
        raise _library_item_unavailable_error()
    return item


def _scope_record_filters(scope: ChatScope, scope_id: str | None) -> list[Any]:
    """范围条件（scope_id 语义按 scope：COURSE=课程 id、LIBRARY_ITEM=资料条目 id）：
    COURSE = 该课程全部未软删记录；ALL = 全部未软删记录（含收件箱，软删课程下的
    记录随课程排除，口径同 record_options）；LIBRARY_ITEM = 该资料关联的未软删记录。"""
    if scope == ChatScope.COURSE:
        return [Record.deleted_at.is_(None), Record.course_id == scope_id]
    if scope == ChatScope.LIBRARY_ITEM:
        return [
            Record.deleted_at.is_(None),
            Record.id.in_(
                select(LibraryItemRecord.record_id).where(
                    LibraryItemRecord.library_item_id == scope_id
                )
            ),
        ]
    return [
        Record.deleted_at.is_(None),
        or_(
            Record.course_id.is_(None),
            and_(Course.id.is_not(None), Course.deleted_at.is_(None)),
        ),
    ]


async def _scope_library_rows(
    session: AsyncSession, scope: ChatScope, scope_id: str | None
) -> list[tuple[str, str, Any, bool]]:
    """范围会话的记录行（updated_at 降序）：(id, title, updated_at, has_transcript)。

    scope_id 语义按 scope：COURSE=课程 id，LIBRARY_ITEM=资料条目 id，ALL=None。
    """
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
        .where(*_scope_record_filters(scope, scope_id))
        .order_by(Record.updated_at.desc(), Record.id.desc())
    )
    rows = (await session.execute(stmt)).all()
    return [(str(row.id), str(row.title), row.updated_at, bool(row.has_transcript)) for row in rows]


async def _load_library_context(
    session: AsyncSession,
    scope: ChatScope,
    course_id: str | None,
    library_item_id: str | None = None,
) -> LibraryContext:
    """范围会话的清单上下文（标题 + 日期 + 有无转写）。

    LIBRARY_ITEM 档另携挂载条目正文（item_content，各来源段带【来源：标题】头，
    超过 CHAT_TRANSCRIPT_MAX_CHARS 降级为 None 回退清单 + 检索模式，对齐 RECORD 档）；
    COURSE/ALL 仅清单（多记录聚合不注入正文）。
    """
    if scope == ChatScope.LIBRARY_ITEM:
        item = await _require_library_item(session, library_item_id)
        rows = await _scope_library_rows(session, scope, item.id)
        record_materials, item_materials = await _load_scope_materials(session, scope, item.id)
        parts = [
            f"【来源：{material.title}】\n{material.transcript}" for material in record_materials
        ]
        parts += [f"【来源：{material.title}】\n{material.content}" for material in item_materials]
        content = "\n\n".join(parts)
        return LibraryContext(
            scope_label=f"资料「{item.title}」及其关联学习记录",
            records=tuple(
                LibraryRecordRow(
                    title=title,
                    updated_date=updated_at.strftime("%Y-%m-%d"),
                    has_transcript=has_transcript,
                )
                for _id, title, updated_at, has_transcript in rows
            ),
            item_content=content if len(content) <= CHAT_TRANSCRIPT_MAX_CHARS else None,
        )
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


async def _load_scope_materials(
    session: AsyncSession,
    scope: ChatScope,
    scope_id: str | None,
) -> tuple[list[LibraryRecordMaterial], list[LibraryItemMaterial]]:
    """范围会话材料查询（条目正文注入与流后引用校验共用）。

    记录材料（个人量级，#24 背书）覆盖转写命中；条目材料覆盖资料直挂分片命中
    （03 网页剪藏起），两者共同支撑 library 条目的逐字校验与归属裁定。
    """
    stmt = (
        select(Record.id, Record.title, Transcript.content)
        .join(
            Transcript,
            and_(Transcript.record_id == Record.id, Transcript.deleted_at.is_(None)),
        )
        .outerjoin(Course, Course.id == Record.course_id)
        .where(*_scope_record_filters(scope, scope_id))
        .order_by(Record.updated_at.desc(), Record.id.desc())
    )
    rows = (await session.execute(stmt)).all()
    records = [
        LibraryRecordMaterial(
            record_id=str(row.id), title=str(row.title), transcript=str(row.content)
        )
        for row in rows
    ]
    # 条目材料：COURSE/ALL 取范围内 ACTIVE 条目的直挂分片正文；LIBRARY_ITEM
    # 只取挂载条目（边界=该资料）。
    item_stmt = (
        select(
            LibraryItem.id,
            LibraryItem.title,
            DocumentSegment.content,
            DocumentSegment.sequence_no,
        )
        .join(
            DocumentSegment,
            and_(
                DocumentSegment.library_item_id == LibraryItem.id,
                DocumentSegment.record_id.is_(None),
            ),
        )
        .where(LibraryItem.deleted_at.is_(None), LibraryItem.status == "ACTIVE")
    )
    if scope == ChatScope.LIBRARY_ITEM:
        item_stmt = item_stmt.where(LibraryItem.id == scope_id)
    elif scope == ChatScope.COURSE:
        item_stmt = item_stmt.where(LibraryItem.course_id == scope_id)
    elif scope == ChatScope.ALL:
        item_stmt = item_stmt.where(
            or_(
                LibraryItem.course_id.is_(None),
                Course.id.is_not(None),
            )
        ).outerjoin(Course, and_(Course.id == LibraryItem.course_id, Course.deleted_at.is_(None)))
    item_stmt = item_stmt.order_by(LibraryItem.id, DocumentSegment.sequence_no, DocumentSegment.id)
    item_rows = (await session.execute(item_stmt)).all()
    contents: dict[str, list[str]] = {}
    titles: dict[str, str] = {}
    for row in item_rows:
        contents.setdefault(str(row.id), []).append(str(row.content))
        titles[str(row.id)] = str(row.title)
    items = [
        LibraryItemMaterial(
            library_item_id=item_id, title=titles[item_id], content="\n".join(parts)
        )
        for item_id, parts in contents.items()
    ]
    return records, items


async def _load_library_materials(
    session_factory: async_sessionmaker[AsyncSession],
    scope: ChatScope,
    scope_id: str | None,
) -> tuple[list[LibraryRecordMaterial], list[LibraryItemMaterial]]:
    """范围会话引用校验材料（流式结束后调用，开独立 session 取最新快照）。"""
    async with session_factory() as session:
        return await _load_scope_materials(session, scope, scope_id)


async def _session_context(
    session_factory: async_sessionmaker[AsyncSession],
    session_id: str,
    *,
    web_search: bool = False,
    memory_allowed: bool = False,
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
        if chat.scope == ChatScope.LIBRARY_ITEM:
            # 失效态运行时推导：挂载资料软删/归档后拒绝组装（accept 已先拦一道）。
            await _require_library_item(session, chat.library_item_id)
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
        retrieval_course_id: str | None = None
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
            # 检索边界课程 = 记录所属课程（概念扩展用；RECORD 记录集边界由 record_id 保证）。
            retrieval_course_id = record.course_id
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
        elif chat.scope in (ChatScope.LIBRARY_ITEM, ChatScope.COURSE, ChatScope.ALL):
            # LIBRARY_ITEM 的清单 = 该资料关联记录（资料自身进 scope_label）；
            # 检索边界课程：LIBRARY_ITEM=资料所属课程（概念扩展用），COURSE=挂载课程。
            if chat.scope == ChatScope.LIBRARY_ITEM:
                item = await _require_library_item(session, chat.library_item_id)
                retrieval_course_id = item.course_id
                library_context = await _load_library_context(
                    session, chat.scope, None, chat.library_item_id
                )
            else:
                retrieval_course_id = chat.course_id
                library_context = await _load_library_context(session, chat.scope, chat.course_id)
        # 学习者记忆块（工单 06）：确定性聚合，注入范围 = 全局偏好恒可 +
        # 课程状态仅对应课程范围（scope != ALL 且有边界课程）；关闭外发即零注入。
        learner = await build_learner_context(
            session,
            scope=chat.scope,
            course_id=retrieval_course_id,
            injection_allowed=memory_allowed,
        )
        learner_block = learner.text or None
        return SessionPromptContext(
            mode=chat.mode,
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
                learner=learner_block,
                mode=chat.mode,
            ),
            transcript=transcript_text,
            record_id=record_id,
            course_id=retrieval_course_id,
            library=library_context,
            library_item_id=chat.library_item_id if chat.scope == ChatScope.LIBRARY_ITEM else None,
            web_search=web_search,
            learner=learner_block,
            learner_memories=learner.memories,
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
        # 记忆注入前提（工单 06）：外发开关开启且外发同意对当前供应商有效
        # （供应商地址/密钥变化后同意失效，重新确认前不发送记忆）。
        outbound_enabled = await asyncio.to_thread(memory_outbound_enabled, data_dir)
        _, consent_current = await asyncio.to_thread(llm_consent, data_dir)
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
                if chat.scope == ChatScope.LIBRARY_ITEM:
                    # 失效态运行时推导：挂载资料软删/归档后发送被拒，会话只读。
                    await _require_library_item(session, chat.library_item_id)
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
            memory_injection_allowed=outbound_enabled and consent_current,
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
            memory_proposals: list[dict[str, object]] = []
            research_proposals: list[dict[str, str]] = []
            research_mode = False
            try:
                prompt_context = await _session_context(
                    session_factory,
                    session_id,
                    web_search=accepted.web_search is not None,
                    memory_allowed=accepted.memory_injection_allowed,
                )
                research_mode = prompt_context.mode == ChatMode.RESEARCH
                # 范围会话（RECORD/LIBRARY_ITEM/COURSE/ALL）统一绑定 search_library
                # 检索上下文：作用域 + 目标 id + 本轮工具预算（每轮新建累计器）。
                library_binding = (
                    LibrarySearchContext(
                        scope=prompt_context.scope,
                        course_id=prompt_context.course_id,
                        session_factory=session_factory,
                        record_id=prompt_context.record_id,
                        library_item_id=prompt_context.library_item_id,
                        budget=ToolCallBudget(),
                    )
                    if prompt_context.scope in RETRIEVAL_SCOPES
                    else None
                )
                # 记忆提案工具的运行期绑定（工单 06）：溯源到当前会话。
                memory_binding = MemoryProposalContext(
                    session_factory=session_factory, session_id=session_id
                )
                # 入库提案工具的运行期绑定（研究会话 V1）：仅研究会话挂载；
                # COURSE 范围自动带课程 id，ALL/FREE 落 None 由用户后续整理。
                ingest_binding = (
                    ResearchIngestContext(
                        session_factory=session_factory,
                        session_id=session_id,
                        course_id=prompt_context.course_id,
                    )
                    if research_mode
                    else None
                )
                async for event in stream_chat_reply(
                    session_factory=session_factory,
                    checkpointer=checkpointer,
                    provider=accepted.provider,
                    context_messages=prompt_context.messages,
                    session_id=session_id,
                    outcome=outcome,
                    library=library_binding,
                    web_search=accepted.web_search,
                    memory=memory_binding,
                    ingest=ingest_binding,
                    prompt_version=(
                        CHAT_RESEARCH_PROMPT_VERSION if research_mode else CHAT_PROMPT_VERSION
                    ),
                ):
                    if isinstance(event, ChatTokenEvent):
                        parts.append(event.text)
                        yield _sse("token", {"text": event.text})
                    elif isinstance(event, ChatToolCallEvent):
                        yield _sse("tool_call", {"tool": event.tool, "query": event.query})
                    elif isinstance(event, ChatMemoryProposalEvent):
                        memory_proposals.append(
                            {"proposal_id": event.proposal_id, "items": event.items}
                        )
                    elif isinstance(event, ChatResearchProposalEvent):
                        research_proposals.extend(event.proposals)
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
            # 引用块解析：范围会话（RECORD 之外的挂载范围）按「（来源：标题）」裁定
            # 归属（记录条目优先、资料条目 library 条目次之）；RECORD 单记录按转写
            # 逐字校验；自由聊天仅本轮联网时解析（产出 web 条目）。
            citations: list[dict[str, int | str]] = []
            if prompt_context.should_parse_citations:
                if prompt_context.library is not None:
                    scope_id = (
                        prompt_context.library_item_id
                        if prompt_context.scope == ChatScope.LIBRARY_ITEM
                        else prompt_context.course_id
                    )
                    records, items = await _load_library_materials(
                        session_factory, prompt_context.scope, scope_id
                    )
                    parsed = parse_library_citation_reply(content, records, items)
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
            # done 载荷扩展（工单 06，可选字段向后兼容）：memory_used=本轮实际
            # 注入的记忆条目，恒携带——空数组=本轮零注入（外发关闭/无记忆），
            # 让前端能区分「未询问」与「确认未注入」并展示空态；
            # memory_proposals=模型经 propose_memory 创建的待确认提案（就地确认卡）。
            done_payload: dict[str, object] = {
                "message_id": assistant_id,
                "content": content,
                "memory_used": list(prompt_context.learner_memories),
            }
            if memory_proposals:
                done_payload["memory_proposals"] = memory_proposals
            if research_proposals:
                done_payload["research_proposals"] = research_proposals
            yield _sse("done", done_payload)
        finally:
            registry.release(session_id)
