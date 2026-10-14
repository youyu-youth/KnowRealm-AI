"""对话消息与上下文组装：历史消息（含过程投影）与喂入 LLM 的会话上下文。

回答生成执行已迁移 ChatTurn（票 01：提交 / 观察 / 控制分离，见 turns/）；
本模块保留：消息历史查询（旧 ChatResponseProcess 行 + 新轮次事件投影合并）、
会话上下文组装（ChatTurn worker 复用）与挂载对象校验。
"""

import json
from dataclasses import dataclass
from datetime import datetime, tzinfo
from typing import Any, cast

from langchain_core.messages import AnyMessage
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.agent.citations import (
    LibraryItemMaterial,
    LibraryRecordMaterial,
)
from app.modules.agent.context import (
    CHAT_TRANSCRIPT_MAX_CHARS,
    ActiveRunSummary,
    ContextRow,
    LibraryContext,
    LibraryRecordRow,
    PageHint,
    RecordContext,
    build_context_messages,
)
from app.modules.agent.graph import stream_chat_reply
from app.modules.agent.models import ChatMessage, ChatResponseProcess, ChatSession
from app.modules.agent.response_process import process_out
from app.modules.agent.runs.models import AgentOperation
from app.modules.agent.runs.schemas import OperationStatus
from app.modules.agent.runs.service import list_nonterminal_runs
from app.modules.agent.schemas import (
    ChatMessageOut,
    ChatMessageTurnOut,
    ChatMode,
    ChatPageSnapshot,
    ChatResponseProcessOut,
    ChatRole,
    ChatScope,
    ChatTurnResultOut,
)
from app.modules.agent.session_service import ChatSessionService
from app.modules.agent.tools.time_utils import format_time_hint
from app.modules.agent.turns.models import ChatTurn, ChatTurnEvent
from app.modules.agent.turns.projection import (
    build_output_text,
    event_payload,
    process_out_for,
    project_revisions,
)
from app.modules.agent.turns.schemas import ChatTurnEventType, ChatTurnStatus
from app.modules.course.models import Course
from app.modules.knowledge_point.models import KnowledgePoint
from app.modules.knowledge_point.schemas import KnowledgePointGenerationStatus
from app.modules.learner.service import build_learner_context
from app.modules.library.models import LibraryItem, LibraryItemRecord
from app.modules.library.shared_refs import (
    shared_alive_item_ids,
    shared_alive_record_ids,
)
from app.modules.record.models import Record
from app.modules.record.service import RecordService
from app.modules.summary.models import AiSummary
from app.modules.summary.schemas import AiSummaryStatus
from app.modules.transcript.models import DocumentSegment, Transcript
from app.shared.errors import CodedHTTPException

# stream_chat_reply 经本模块属性调用（turns worker 的测试替换缝隙先例保留）。
__all__ = ["ChatMessageService", "SessionPromptContext", "stream_chat_reply"]

# 部分输出恢复口径（规格 §5/§15）：终态或中断且无最终消息时，历史行按轮次引用
# 携带已持久化部分输出；RUNNING 由前端流式态负责，不在此重复。
_PARTIAL_OUTPUT_STATUSES = (
    ChatTurnStatus.CANCELLED.value,
    ChatTurnStatus.FAILED.value,
    ChatTurnStatus.INTERRUPTED.value,
)


def _str_list(value: object) -> list[str]:
    items = cast("list[object]", value) if isinstance(value, list) else []
    return [item for item in items if isinstance(item, str)]


def _dict_list(value: object) -> list[dict[str, Any]]:
    items = cast("list[object]", value) if isinstance(value, list) else []
    return [cast("dict[str, Any]", item) for item in items if isinstance(item, dict)]


def _turn_ref(turn: ChatTurn, events: list[ChatTurnEvent]) -> ChatMessageTurnOut:
    """轮次引用投影（规格 §15）：部分输出（终态 / 中断且无最终消息）与完成载荷
    展示子集（本轮注入记忆与新建提案，跨会话 / 重启恢复确认卡）。"""
    output_text = (
        build_output_text(events)
        if turn.final_message_id is None and turn.status in _PARTIAL_OUTPUT_STATUSES
        else ""
    )
    result: ChatTurnResultOut | None = None
    if turn.snapshot_json is not None:
        saved = cast(dict[str, Any], json.loads(turn.snapshot_json))
        if turn.final_message_id is None and turn.status in _PARTIAL_OUTPUT_STATUSES:
            output_text = str(saved["turn"]["output_text"])
        payload = saved.get("done")
        if isinstance(payload, dict):
            payload = cast(dict[str, Any], payload)
            result = ChatTurnResultOut(
                memory_used=_str_list(payload.get("memory_used")),
                memory_proposals=_dict_list(payload.get("memory_proposals")),
                research_proposals=_dict_list(payload.get("research_proposals")),
            )
    for row in events:
        if row.type != ChatTurnEventType.DONE.value:
            continue
        payload = event_payload(row)
        result = ChatTurnResultOut(
            memory_used=_str_list(payload.get("memory_used")),
            memory_proposals=_dict_list(payload.get("memory_proposals")),
            research_proposals=_dict_list(payload.get("research_proposals")),
        )
        break
    return ChatMessageTurnOut(
        id=turn.id,
        status=turn.status,
        output_text=output_text,
        result=result,
        revisions=project_revisions(events, turn),
    )


# 会话标题默认取首条用户消息的截断长度。
CHAT_TITLE_MAX_CHARS = 30
# 未结束任务摘要条数上限（工单 05：只提示最近几条，避免提示块随任务数膨胀）。
ACTIVE_RUN_SUMMARY_LIMIT = 3


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
    # 页面快照（工单 01）：page 为重校验后的快照（失效引用已丢弃，进运行时
    # 上下文）；page_hint 为注入模型上下文的提示投影（含对象名标签）。
    page: ChatPageSnapshot | None = None
    page_hint: PageHint | None = None

    @property
    def learner_injected(self) -> bool:
        return bool(self.learner)

    @property
    def should_parse_citations(self) -> bool:
        """挂载与范围会话恒解析引用块；自由聊天仅本轮联网时解析（产出 web 条目）。"""
        return self.record_id is not None or self.library is not None or self.web_search


async def validate_sendable_chat(session: AsyncSession, chat: ChatSession) -> None:
    """发送前校验（受理与执行共用）：挂载对象失效即拒绝（软删/归档，会话只读）。"""
    if chat.record_id is not None and (await RecordService.get(session, chat.record_id)) is None:
        raise CodedHTTPException(
            code="CHAT_RECORD_UNAVAILABLE",
            status_code=409,
            detail="CHAT_RECORD_UNAVAILABLE：原记录已删除，对话已失效",
        )
    if chat.scope == ChatScope.COURSE and not await _course_available(session, chat):
        raise CodedHTTPException(
            code="CHAT_COURSE_UNAVAILABLE",
            status_code=409,
            detail="CHAT_COURSE_UNAVAILABLE：课程已删除，对话已失效",
        )
    if chat.scope == ChatScope.LIBRARY_ITEM:
        await _require_library_item(session, chat.library_item_id)


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
    COURSE = 该课程全部未软删记录 + 共享引用覆盖的存活资料记录（工单 05）；
    ALL = 全部未软删记录（含收件箱，软删课程下的记录随课程排除，口径同
    record_options）；LIBRARY_ITEM = 该资料关联的未软删记录。"""
    if scope == ChatScope.COURSE:
        return [
            Record.deleted_at.is_(None),
            or_(
                Record.course_id == scope_id,
                Record.id.in_(shared_alive_record_ids(cast(str, scope_id))),
            ),
        ]
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
    excluded_sources: list[str] | None = None,
) -> LibraryContext:
    """范围会话的清单上下文（标题 + 日期 + 有无转写）。

    LIBRARY_ITEM 档另携挂载条目正文（item_content，各来源段带【来源：标题】头，
    超过 CHAT_TRANSCRIPT_MAX_CHARS 降级为 None 回退清单 + 检索模式，对齐 RECORD 档）；
    COURSE/ALL 仅清单（多记录聚合不注入正文）。
    """
    if scope == ChatScope.LIBRARY_ITEM:
        item = await _require_library_item(session, library_item_id)
        excluded = excluded_sources or []
        rows = [
            row
            for row in await _scope_library_rows(session, scope, item.id)
            if f"record:{row[0]}" not in excluded
        ]
        record_materials, item_materials = await _load_scope_materials(session, scope, item.id)
        record_materials = [
            material
            for material in record_materials
            if f"record:{material.record_id}" not in excluded
        ]
        item_materials = [
            material
            for material in item_materials
            if f"library:{material.library_item_id}" not in excluded
        ]
        if f"library:{item.id}" in excluded:
            record_materials, item_materials, rows = [], [], []
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
    rows = [
        row
        for row in await _scope_library_rows(session, scope, course_id)
        if f"record:{row[0]}" not in (excluded_sources or [])
    ]
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
    COURSE 档纳入共享引用覆盖的资料（工单 05），shared 标注归属他空间的材料
    （引用行「共享来源」徽章依据）。
    """
    stmt = (
        select(Record.id, Record.title, Record.course_id, Transcript.content)
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
            record_id=str(row.id),
            title=str(row.title),
            transcript=str(row.content),
            shared=scope == ChatScope.COURSE and row.course_id != scope_id,
        )
        for row in rows
    ]
    # 条目材料：COURSE/ALL 取范围内 ACTIVE 条目的直挂分片正文（COURSE 含共享
    # 引用条目，工单 05）；LIBRARY_ITEM 只取挂载条目（边界=该资料）。
    item_stmt = (
        select(
            LibraryItem.id,
            LibraryItem.title,
            LibraryItem.course_id,
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
        item_stmt = item_stmt.where(
            or_(
                LibraryItem.course_id == scope_id,
                LibraryItem.id.in_(shared_alive_item_ids(cast(str, scope_id))),
            )
        )
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
    item_shared: dict[str, bool] = {}
    for row in item_rows:
        contents.setdefault(str(row.id), []).append(str(row.content))
        titles[str(row.id)] = str(row.title)
        item_shared[str(row.id)] = scope == ChatScope.COURSE and row.course_id != scope_id
    items = [
        LibraryItemMaterial(
            library_item_id=item_id,
            title=titles[item_id],
            content="\n".join(parts),
            shared=item_shared[item_id],
        )
        for item_id, parts in contents.items()
    ]
    return records, items


async def load_library_materials(
    session_factory: async_sessionmaker[AsyncSession],
    scope: ChatScope,
    scope_id: str | None,
) -> tuple[list[LibraryRecordMaterial], list[LibraryItemMaterial]]:
    """范围会话引用校验材料（流式结束后调用，开独立 session 取最新快照）。"""
    async with session_factory() as session:
        return await _load_scope_materials(session, scope, scope_id)


async def _validate_page_snapshot(
    session: AsyncSession, page: ChatPageSnapshot | None
) -> tuple[ChatPageSnapshot | None, PageHint | None]:
    """页面快照后端重校验（工单 01，spec 实施决策 11）：对象不存在/已删除时
    丢弃引用仅保留页面标签（提示是参考信息，失效即静默降级，不影响发送）；
    快照不落库、不构成授权、不扩大读取范围。"""
    if page is None:
        return None, None
    entity_label: str | None = None
    entity_id = page.entity_id
    if page.page_type == "course" and entity_id is not None:
        course = await session.get(Course, entity_id)
        if course is not None and course.deleted_at is None:
            suffix = "（已归档）" if course.status == "ARCHIVED" else ""
            entity_label = f"课程「{course.name}」{suffix}"
        else:
            entity_id = None
    elif page.page_type == "record" and entity_id is not None:
        record = await RecordService.get(session, entity_id)
        if record is not None:
            entity_label = f"记录「{record.title}」"
        else:
            entity_id = None
    validated = page if entity_id == page.entity_id else page.model_copy(update={"entity_id": None})
    return validated, PageHint(page_type=page.page_type, entity_label=entity_label)


@dataclass
class _RunCounts:
    """任务逐项计数聚合（摘要投影用：已成功 / 失败或跳过 / 合计）。"""

    total: int = 0
    succeeded: int = 0
    failed: int = 0


async def _active_run_summaries(session: AsyncSession, session_id: str) -> list[ActiveRunSummary]:
    """本会话未结束任务摘要（工单 05，上限 3 条，最近在前）。

    只读投影：状态 + 逐项计数（已成功 / 失败或跳过）+ 等待原因。任务状态以
    agent_runs 为唯一事实源（断线 / 重启后同样可查），注入文本框定为提示非指令。
    """
    runs = await list_nonterminal_runs(session, session_id, limit=ACTIVE_RUN_SUMMARY_LIMIT)
    if not runs:
        return []
    counts = {run.id: _RunCounts() for run in runs}
    operations = (
        await session.execute(
            select(AgentOperation.run_id, AgentOperation.status).where(
                AgentOperation.run_id.in_([run.id for run in runs])
            )
        )
    ).all()
    for run_id, status in operations:
        bucket = counts.get(cast(str, run_id))
        if bucket is None:
            continue
        bucket.total += 1
        if status == OperationStatus.SUCCEEDED.value:
            bucket.succeeded += 1
        elif status in (OperationStatus.FAILED.value, OperationStatus.SKIPPED.value):
            bucket.failed += 1
    return [
        ActiveRunSummary(
            status=run.status,
            total=counts[run.id].total,
            succeeded=counts[run.id].succeeded,
            failed=counts[run.id].failed,
            waiting_reason=run.waiting_reason,
        )
        for run in runs
    ]


async def session_context(
    session_factory: async_sessionmaker[AsyncSession],
    session_id: str,
    *,
    web_search: bool = False,
    memory_allowed: bool = False,
    page: ChatPageSnapshot | None = None,
    user_timezone: tzinfo | None = None,
    preview_content: str | None = None,
    input_messages: list[AnyMessage] | None = None,
    context_turn_id: str | None = None,
) -> SessionPromptContext:
    async with session_factory() as session:
        chat = await ChatSessionService.get(session, session_id)
        if chat is None:
            raise CodedHTTPException(
                code="CHAT_SESSION_NOT_FOUND", status_code=404, detail="对话不存在或已删除"
            )
        if chat.scope == ChatScope.COURSE and not await _course_available(session, chat):
            # 失效态运行时推导：挂载课程软删后流式上下文拒绝组装（提交受理已先拦一道）。
            raise CodedHTTPException(
                code="CHAT_COURSE_UNAVAILABLE",
                status_code=409,
                detail="CHAT_COURSE_UNAVAILABLE：课程已删除，对话已失效",
            )
        if chat.scope == ChatScope.LIBRARY_ITEM:
            # 失效态运行时推导：挂载资料软删/归档后拒绝组装（提交受理已先拦一道）。
            await _require_library_item(session, chat.library_item_id)
        rows = (
            await session.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at, ChatMessage.id)
            )
        ).all()
        from app.modules.agent.context_budget.rules import (
            context_rules,
            evidence_excluded,
            history_identities,
            turn_allowed,
        )

        segment, rules = await context_rules(
            session, session_id, turn_id=context_turn_id, current=context_turn_id is None
        )
        identities = await history_identities(session, session_id, list(rows))
        rows = [
            row
            for row in rows
            if row.role == ChatRole.SYSTEM
            or (
                turn_allowed(rules, segment, *identities.get(row.id, (None, 1, ""))[:2])
                and not evidence_excluded(
                    json.loads(row.citations_json) if row.citations_json else [], rules
                )
            )
        ]
        record_context = None
        transcript_text: str | None = None
        record_id: str | None = chat.record_id
        retrieval_course_id: str | None = None
        library_context: LibraryContext | None = None
        record = await RecordService.get(session, chat.record_id) if chat.record_id else None
        if chat.record_id and record is None:
            raise CodedHTTPException(
                code="CHAT_RECORD_UNAVAILABLE",
                status_code=409,
                detail="CHAT_RECORD_UNAVAILABLE：原记录已删除",
            )
        if record:
            # 排除资料只改变选材，课程范围与独立记忆范围保留。
            retrieval_course_id = record.course_id
            record_context = RecordContext(transcript="")
        if record and f"record:{record.id}" not in rules.excluded_source_ids:
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
        elif chat.scope in (ChatScope.LIBRARY_ITEM, ChatScope.COURSE, ChatScope.ALL):
            # LIBRARY_ITEM 的清单 = 该资料关联记录（资料自身进 scope_label）；
            # 检索边界课程：LIBRARY_ITEM=资料所属课程（概念扩展用），COURSE=挂载课程。
            if chat.scope == ChatScope.LIBRARY_ITEM:
                item = await _require_library_item(session, chat.library_item_id)
                retrieval_course_id = item.course_id
                library_context = await _load_library_context(
                    session, chat.scope, None, chat.library_item_id, rules.excluded_source_ids
                )
            else:
                retrieval_course_id = chat.course_id
                library_context = await _load_library_context(
                    session, chat.scope, chat.course_id, excluded_sources=rules.excluded_source_ids
                )
        # 学习者记忆块（工单 06）：确定性聚合，注入范围 = 全局偏好恒可 +
        # 课程状态仅对应课程范围（scope != ALL 且有边界课程）；关闭外发即零注入。
        learner = await build_learner_context(
            session,
            scope=chat.scope,
            course_id=retrieval_course_id,
            injection_allowed=memory_allowed,
        )
        learner_block = learner.text or None
        validated_page, page_hint = await _validate_page_snapshot(session, page)
        active_runs = await _active_run_summaries(session, session_id)
        # 时间提示行（时间能力 v1）：用户时区当前时间快照，与页面提示同款每轮重建。
        time_hint = (
            format_time_hint(datetime.now(user_timezone)) if user_timezone is not None else None
        )
        from app.modules.agent.context_budget.retrieval import validate_evidence

        context_rows: list[ContextRow] = []
        for row in rows:
            valid_citations: list[object] = []
            invalid_citations = False
            if row.citations_json:
                try:
                    value: object = json.loads(row.citations_json)
                except ValueError:
                    value = None
                citations = cast(list[object], value) if isinstance(value, list) else []
                invalid_citations = not isinstance(value, list)
                for citation in citations:
                    try:
                        await validate_evidence(session, chat, [citation], rules=rules)
                        valid_citations.append(citation)
                    except CodedHTTPException:
                        invalid_citations = True
            context_rows.append(
                ContextRow(
                    id=row.id,
                    role=row.role,
                    content=row.content
                    if not invalid_citations
                    else "此历史回复的引用来源已失效，原文暂停使用。",
                    cited_excerpts=_cited_excerpts(json.dumps(valid_citations), chat.record_id),
                )
            )
        if preview_content is not None:
            if context_rows and context_rows[-1].role == ChatRole.USER:
                context_rows.pop()
            context_rows.append(
                ContextRow(id="preview", role=ChatRole.USER, content=preview_content)
            )
        return SessionPromptContext(
            mode=chat.mode,
            scope=chat.scope,
            messages=input_messages
            if input_messages is not None
            else build_context_messages(
                context_rows,
                record=record_context,
                library=library_context,
                web_search=web_search,
                learner=learner_block,
                mode=chat.mode,
                page_hint=page_hint,
                active_runs=active_runs,
                time_hint=time_hint,
                durable_history=True,
            ),
            transcript=transcript_text,
            record_id=record_id,
            course_id=retrieval_course_id,
            library=library_context,
            library_item_id=chat.library_item_id if chat.scope == ChatScope.LIBRARY_ITEM else None,
            web_search=web_search,
            learner=learner_block,
            learner_memories=learner.memories,
            page=validated_page,
            page_hint=page_hint,
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
    async def list_message_outputs(
        session: AsyncSession, session_id: str
    ) -> list[ChatMessageOut] | None:
        """历史消息 + 过程视图：旧 ChatResponseProcess 行与 ChatTurn 事件投影合并。

        新轮次不再写第二套执行状态机（规格实施决策 1），过程视图由轮次事件
        投影（id=turn_id）；旧行保持只读可查，同一 user 消息按开始时间排序。
        """
        messages = await ChatMessageService.list_messages(session, session_id)
        if messages is None:
            return None
        processes = await session.scalars(
            select(ChatResponseProcess)
            .where(ChatResponseProcess.session_id == session_id)
            .order_by(ChatResponseProcess.started_at, ChatResponseProcess.id)
        )
        by_user: dict[str, list[ChatResponseProcessOut]] = {}
        for row in processes:
            by_user.setdefault(row.user_message_id, []).append(process_out(row))
        turn_by_user: dict[str, ChatMessageTurnOut] = {}
        turns = list(
            (
                await session.scalars(
                    select(ChatTurn)
                    .where(ChatTurn.session_id == session_id)
                    .order_by(ChatTurn.created_at, ChatTurn.id)
                )
            ).all()
        )
        if turns:
            events = list(
                (
                    await session.scalars(
                        select(ChatTurnEvent)
                        .where(ChatTurnEvent.turn_id.in_([turn.id for turn in turns]))
                        .order_by(ChatTurnEvent.turn_id, ChatTurnEvent.seq)
                    )
                ).all()
            )
            events_by_turn: dict[str, list[ChatTurnEvent]] = {}
            for event in events:
                events_by_turn.setdefault(event.turn_id, []).append(event)
            for turn in turns:
                turn_events = events_by_turn.get(turn.id, [])
                process = process_out_for(turn, turn_events)
                bucket = by_user.setdefault(turn.user_message_id, [])
                bucket.append(process)
                bucket.sort(key=lambda item: (item.started_at, item.id))
                turn_by_user[turn.user_message_id] = _turn_ref(turn, turn_events)
        result = [ChatMessageOut.model_validate(message) for message in messages]
        for message in result:
            message.response_processes = by_user.get(message.id, [])
            message.turn = turn_by_user.get(message.id)
        return result

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
