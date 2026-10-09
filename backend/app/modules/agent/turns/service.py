"""ChatTurn 领域服务：受理（幂等）、快照、事件读取、取消与启动对账。

职责边界（规格实施决策 1/4/5/6）：
- 受理在同一事务保存用户消息、轮次与 CHAT_TURN job，任一步失败全部回滚；
- 事件服务只读已提交事件；快照与 last_seq 来自同一数据库一致视图；
- 取消是持久控制指令：先落 cancel_requested；QUEUED / 无在途执行的 RUNNING /
  INTERRUPTED 直接收口 CANCELLED（释放路径，防崩溃死锁会话）；在途执行由执行
  侧落实，完成提交与取消裁决共享事务内的条件检查（取消先提交则拒绝完成，
  不写最终消息与完成事件）；
- 启动对账把 RUNNING 翻 INTERRUPTED 并保留内容，禁止不安全续跑（票 01）。
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Any, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.modules.agent.message_service import validate_sendable_chat
from app.modules.agent.models import ChatMessage, ChatSession
from app.modules.agent.runs.schemas import AuthMode
from app.modules.agent.schemas import ChatRole
from app.modules.agent.turns.models import ChatTurn, ChatTurnEvent
from app.modules.agent.turns.projection import build_output_text, process_out_for
from app.modules.agent.turns.runtime import ActiveTurnRegistry, TurnEventBroadcaster
from app.modules.agent.turns.schemas import (
    ChatTurnEventType,
    ChatTurnOut,
    ChatTurnStatus,
    ChatTurnSubmitRequest,
)
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.runner import recover_running_to_failed
from app.modules.jobs.schemas import ProcessingJobStatus, ProcessingJobType
from app.modules.library.proposals import ProposalService
from app.modules.settings.config import (
    LlmProviderConfig,
    agent_default_auth_mode,
    llm_consent,
    load_llm_provider,
    memory_outbound_enabled,
    resolve_user_timezone,
)
from app.shared.errors import CodedHTTPException
from app.shared.events import RecordInvalidationNotifier

# 会话标题默认取首条用户消息的截断长度（先例：message_service）。
CHAT_TITLE_MAX_CHARS = 30

CHAT_TURN_JOB_TYPE = ProcessingJobType.CHAT_TURN

_TERMINAL_JOB_STATUSES = (
    ProcessingJobStatus.SUCCEEDED,
    ProcessingJobStatus.FAILED,
    ProcessingJobStatus.CANCELLED,
)

_ACTIVE_TURN_FILTER = ChatTurn.status.notin_(
    (
        ChatTurnStatus.COMPLETED.value,
        ChatTurnStatus.FAILED.value,
        ChatTurnStatus.CANCELLED.value,
    )
)


class TurnCompletionOutcome(StrEnum):
    """完成提交结果：提交成功 / 被已提交的取消拒绝 / 执行身份或状态失配。"""

    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    LOST = "LOST"


def turn_job_input(turn_id: str) -> str:
    return json.dumps({"turn_id": turn_id}, separators=(",", ":"))


def request_fingerprint(payload: ChatTurnSubmitRequest) -> str:
    """客户端原请求的规范化指纹（内容/联网/页面/授权档）；不含全局配置。"""
    normalized = {
        "content": payload.content,
        "web_search": payload.web_search,
        "page": payload.page.model_dump(mode="json") if payload.page is not None else None,
        "auth_mode": payload.auth_mode.value if payload.auth_mode is not None else None,
    }
    return sha256(
        json.dumps(normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def serialize_timezone(tz: tzinfo | None) -> str | None:
    """执行快照里的时区序列化：ZoneInfo 存键名，固定偏移存秒数。"""
    if tz is None:
        return None
    key = getattr(tz, "key", None)
    if isinstance(key, str):
        return key
    offset = datetime.now(UTC).astimezone(tz).utcoffset()
    return None if offset is None else f"offset:{int(offset.total_seconds())}"


def parse_timezone(raw: str | None) -> tzinfo | None:
    if raw is None:
        return None
    if raw.startswith("offset:"):
        try:
            seconds = int(raw.removeprefix("offset:"))
        except ValueError:
            return None
        return timezone(timedelta(seconds=seconds))
    try:
        return ZoneInfo(raw)
    except Exception:
        return None


def load_execution(row: ChatTurn) -> dict[str, Any]:
    try:
        value: object = json.loads(row.execution_json)
    except ValueError:
        return {}
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


async def get_turn(session: AsyncSession, turn_id: str) -> ChatTurn | None:
    return await session.get(ChatTurn, turn_id)


async def find_active_turn(session: AsyncSession, session_id: str) -> ChatTurn | None:
    """会话当前非终态轮次（含 QUEUED/RUNNING/INTERRUPTED/WAITING_*）；至多一条。"""
    return await session.scalar(
        select(ChatTurn)
        .where(ChatTurn.session_id == session_id, _ACTIVE_TURN_FILTER)
        .order_by(ChatTurn.created_at, ChatTurn.id)
        .limit(1)
    )


async def list_turn_events(session: AsyncSession, turn_id: str) -> list[ChatTurnEvent]:
    return list(
        (
            await session.scalars(
                select(ChatTurnEvent)
                .where(ChatTurnEvent.turn_id == turn_id)
                .order_by(ChatTurnEvent.seq)
            )
        ).all()
    )


def turn_out(turn: ChatTurn, events: list[ChatTurnEvent] | None = None) -> ChatTurnOut:
    """轮次快照投影；events 提供时一并投影正文与过程（同一一致视图读取）。"""
    return ChatTurnOut(
        id=turn.id,
        session_id=turn.session_id,
        user_message_id=turn.user_message_id,
        final_message_id=turn.final_message_id,
        status=ChatTurnStatus(turn.status),
        cancel_requested=bool(turn.cancel_requested),
        attempt=turn.attempt,
        output_revision=turn.output_revision,
        last_seq=turn.last_seq,
        error_code=turn.error_code,
        error_message=turn.error_message,
        created_at=turn.created_at,
        updated_at=turn.updated_at,
        started_at=turn.started_at,
        finished_at=turn.finished_at,
        output_text=build_output_text(events) if events is not None else "",
        process=process_out_for(turn, events) if events is not None else None,
    )


def _assert_request_identity(existing: ChatTurn, session_id: str, fingerprint: str) -> None:
    if existing.session_id != session_id or existing.request_fingerprint != fingerprint:
        raise CodedHTTPException(
            code="CHAT_TURN_REQUEST_CONFLICT",
            status_code=409,
            detail="CHAT_TURN_REQUEST_CONFLICT：同一请求身份与上次提交内容不一致，请刷新后重试",
        )


def _turn_in_progress_error() -> CodedHTTPException:
    return CodedHTTPException(
        code="CHAT_TURN_IN_PROGRESS",
        status_code=409,
        detail="CHAT_TURN_IN_PROGRESS：该对话正在生成回答，请稍候或先停止",
    )


async def _submit_in_transaction(
    session: AsyncSession,
    *,
    session_id: str,
    payload: ChatTurnSubmitRequest,
    turn_id: str,
    fingerprint: str,
    execution: dict[str, Any],
    now: datetime,
) -> None:
    chat = await session.get(ChatSession, session_id)
    if chat is None:
        raise CodedHTTPException(
            code="CHAT_SESSION_NOT_FOUND", status_code=404, detail="对话不存在或已删除"
        )
    await validate_sendable_chat(session, chat)
    if await find_active_turn(session, session_id) is not None:
        raise _turn_in_progress_error()
    content = payload.content
    last = await session.scalar(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(1)
    )
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
                created_at=now,
            )
        )
        # 新消息 = 话题翻篇：本会话待确认计划草案提案批量弃置（补答复用不弃置）。
        await ProposalService.discard_session_plan_drafts(session, session_id)
    if chat.title is None:
        chat.title = content[:CHAT_TITLE_MAX_CHARS]
    chat.updated_at = now
    session.add(
        ChatTurn(
            id=turn_id,
            session_id=session_id,
            user_message_id=user_row_id,
            request_id=payload.request_id,
            request_fingerprint=fingerprint,
            status=ChatTurnStatus.QUEUED.value,
            execution_json=json.dumps(execution, ensure_ascii=False, separators=(",", ":")),
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        ProcessingJob(
            job_type=CHAT_TURN_JOB_TYPE,
            status=ProcessingJobStatus.PENDING,
            input_json=turn_job_input(turn_id),
            max_attempts=1,
        )
    )
    await session.flush()


async def _resolve_submit_race(
    session_factory: async_sessionmaker[AsyncSession],
    payload: ChatTurnSubmitRequest,
    session_id: str,
    fingerprint: str,
) -> ChatTurn:
    """并发提交 IntegrityError 后按库内事实分流：幂等命中 / 会话占用 / 未知冲突。"""
    async with session_factory() as session, session.begin():
        existing = await session.scalar(
            select(ChatTurn).where(ChatTurn.request_id == payload.request_id)
        )
        if existing is not None:
            _assert_request_identity(existing, session_id, fingerprint)
            return existing
        if await find_active_turn(session, session_id) is not None:
            raise _turn_in_progress_error()
    raise CodedHTTPException(
        code="CHAT_TURN_SUBMIT_CONFLICT",
        status_code=409,
        detail="CHAT_TURN_SUBMIT_CONFLICT：提交冲突，请重试",
    )


def _load_provider_or_raise(data_dir: Path) -> LlmProviderConfig:
    provider = load_llm_provider(data_dir)
    if provider is None or not provider.api_key:
        raise CodedHTTPException(
            code="LLM_PROVIDER_UNCONFIGURED",
            status_code=409,
            detail="LLM_PROVIDER_UNCONFIGURED：未配置 AI 服务，请先完成供应商配置",
        )
    return provider


def _memory_outbound_allowed(data_dir: Path) -> bool:
    outbound_enabled = memory_outbound_enabled(data_dir)
    _, consent_current = llm_consent(data_dir)
    return outbound_enabled and consent_current


async def _close_turn_job(session: AsyncSession, turn_id: str, status: ProcessingJobStatus) -> None:
    job = await session.scalar(
        select(ProcessingJob).where(
            ProcessingJob.job_type == CHAT_TURN_JOB_TYPE,
            ProcessingJob.input_json == turn_job_input(turn_id),
        )
    )
    if job is None or job.status in _TERMINAL_JOB_STATUSES:
        return
    now = utcnow()
    job.status = status
    job.finished_at = now
    job.updated_at = now


class ChatTurnService:
    @staticmethod
    async def submit_turn(
        *,
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
        session_id: str,
        payload: ChatTurnSubmitRequest,
    ) -> tuple[ChatTurnOut, bool]:
        """受理提交：同事务保存用户消息 + 轮次 + job；返回（快照, 是否新建）。

        幂等与冲突（规格 §4）：相同 request_id + 相同指纹 → 原轮次；同身份但
        内容/联网/页面/授权档不同 → 409；同会话已有非终态轮次 → 409，
        不建隐藏队列、不覆盖已有 USER 消息。
        """
        provider = await asyncio.to_thread(_load_provider_or_raise, data_dir)
        effective_auth_mode = payload.auth_mode or AuthMode(
            await asyncio.to_thread(agent_default_auth_mode, data_dir)
        )
        user_timezone = serialize_timezone(await asyncio.to_thread(resolve_user_timezone, data_dir))
        memory_allowed = await asyncio.to_thread(_memory_outbound_allowed, data_dir)
        fingerprint = request_fingerprint(payload)
        execution: dict[str, Any] = {
            "web_search": payload.web_search,
            "memory_injection_allowed": memory_allowed,
            "auth_mode": effective_auth_mode.value,
            "user_timezone": user_timezone,
            "page": payload.page.model_dump(mode="json") if payload.page is not None else None,
            "provider_model": provider.model,
        }
        now = utcnow()
        turn_id = str(uuid4())
        try:
            async with session_factory() as session, session.begin():
                # 幂等命中优先：网络重试在确认受理结果前保留同一身份。
                existing = await session.scalar(
                    select(ChatTurn).where(ChatTurn.request_id == payload.request_id)
                )
                if existing is not None:
                    _assert_request_identity(existing, session_id, fingerprint)
                    return turn_out(existing), False
                await _submit_in_transaction(
                    session,
                    session_id=session_id,
                    payload=payload,
                    turn_id=turn_id,
                    fingerprint=fingerprint,
                    execution=execution,
                    now=now,
                )
        except IntegrityError:
            # 并发重复提交（同 request_id 或同会话抢占）按库内事实分流。
            turn = await _resolve_submit_race(session_factory, payload, session_id, fingerprint)
            return turn_out(turn), False
        async with session_factory() as session:
            created = await get_turn(session, turn_id)
            assert created is not None  # 上一事务已提交
            return turn_out(created), True

    @staticmethod
    async def get_snapshot(
        session_factory: async_sessionmaker[AsyncSession], turn_id: str
    ) -> ChatTurnOut | None:
        """一致视图返回状态、正文投影与 last_seq（客户端从该序号补发）。"""
        async with session_factory() as session:
            turn = await get_turn(session, turn_id)
            if turn is None:
                return None
            events = await list_turn_events(session, turn_id)
            return turn_out(turn, events)

    @staticmethod
    async def list_session_turns(
        session: AsyncSession,
        session_id: str,
        *,
        active_only: bool = False,
        limit: int = 20,
        before: tuple[datetime, str] | None = None,
    ) -> list[ChatTurn]:
        """会话轮次列表（新到旧游标分页）；active_only 只取非终态（至多一条）。"""
        stmt = select(ChatTurn).where(ChatTurn.session_id == session_id)
        if active_only:
            stmt = stmt.where(_ACTIVE_TURN_FILTER)
        if before is not None:
            before_at, before_id = before
            stmt = stmt.where(
                (ChatTurn.created_at < before_at)
                | ((ChatTurn.created_at == before_at) & (ChatTurn.id < before_id))
            )
        stmt = stmt.order_by(ChatTurn.created_at.desc(), ChatTurn.id.desc()).limit(limit)
        return list((await session.scalars(stmt)).all())

    @staticmethod
    async def list_session_turn_outs(
        session: AsyncSession,
        session_id: str,
        *,
        active_only: bool = False,
        limit: int = 20,
        before: tuple[datetime, str] | None = None,
    ) -> list[ChatTurnOut]:
        """轮次列表投影：active_only（至多一条）带事件投影（返回会话时
        部分输出与过程可见，规格 §15）；其余列表不带事件（轻量元数据）。"""
        rows = await ChatTurnService.list_session_turns(
            session,
            session_id,
            active_only=active_only,
            limit=limit,
            before=before,
        )
        if not active_only:
            return [turn_out(row) for row in rows]
        outs: list[ChatTurnOut] = []
        for row in rows:
            events = await list_turn_events(session, row.id)
            outs.append(turn_out(row, events))
        return outs

    @staticmethod
    async def read_events_after(
        session_factory: async_sessionmaker[AsyncSession], turn_id: str, after_seq: int
    ) -> tuple[ChatTurn, list[ChatTurnEvent]]:
        """只读已提交事件与轮次当前态（同一一致视图）。"""
        async with session_factory() as session:
            turn = await get_turn(session, turn_id)
            if turn is None:
                raise CodedHTTPException(
                    code="CHAT_TURN_NOT_FOUND", status_code=404, detail="对话轮次不存在"
                )
            events = list(
                (
                    await session.scalars(
                        select(ChatTurnEvent)
                        .where(ChatTurnEvent.turn_id == turn_id, ChatTurnEvent.seq > after_seq)
                        .order_by(ChatTurnEvent.seq)
                    )
                ).all()
            )
            return turn, events

    @staticmethod
    async def cancel_turn(
        *,
        session_factory: async_sessionmaker[AsyncSession],
        turn_id: str,
        active: ActiveTurnRegistry,
    ) -> ChatTurnOut | None:
        """持久取消：先落 cancel_requested；可直收口的状态就地翻 CANCELLED。

        RUNNING 且在途执行中 → 仅落标记，执行侧观察器落实（「正在停止」）；
        QUEUED / INTERRUPTED / 无在途执行的 RUNNING → 直接终态收口并关 job。
        """
        async with session_factory() as session, session.begin():
            turn = await get_turn(session, turn_id)
            if turn is None:
                return None
            status = ChatTurnStatus(turn.status)
            if status.is_terminal:
                return turn_out(turn)
            now = utcnow()
            turn.cancel_requested = True
            turn.updated_at = now
            direct = status in (ChatTurnStatus.QUEUED, ChatTurnStatus.INTERRUPTED)
            if status == ChatTurnStatus.RUNNING and turn_id not in active:
                direct = True
            if direct:
                turn.status = ChatTurnStatus.CANCELLED.value
                turn.finished_at = now
                await _close_turn_job(session, turn_id, ProcessingJobStatus.CANCELLED)
            return turn_out(turn)

    @staticmethod
    async def startup_recover(
        session_factory: async_sessionmaker[AsyncSession],
        notifier: RecordInvalidationNotifier,
    ) -> None:
        """启动对账：RUNNING 轮次 → INTERRUPTED（保留内容，禁止不安全续跑）。

        job 侧沿用 recover_running_to_failed（RUNNING job → FAILED(
        WORKER_INTERRUPTED)，max_attempts=1 无自动重投）；轮次侧再独立扫一遍
        RUNNING（覆盖软停机等 job 已终态但轮次仍 RUNNING 的残留）。QUEUED
        轮次照常由 worker 领取。
        """
        await recover_running_to_failed(
            session_factory,
            notifier,
            CHAT_TURN_JOB_TYPE,
            "回答生成被意外中断",
        )
        async with session_factory() as session, session.begin():
            stale = list(
                (
                    await session.scalars(
                        select(ChatTurn).where(ChatTurn.status == ChatTurnStatus.RUNNING.value)
                    )
                ).all()
            )
            now = utcnow()
            for turn in stale:
                turn.status = ChatTurnStatus.INTERRUPTED.value
                turn.finished_at = now
                turn.updated_at = now

    @staticmethod
    async def append_events(
        *,
        session_factory: async_sessionmaker[AsyncSession],
        turn_id: str,
        claim_token: str,
        rows: list[dict[str, Any]],
    ) -> int | None:
        """执行侧事件持久化：同事务推进 seq；执行身份失配返回 None（迟到执行丢弃）。"""
        if not rows:
            return 0
        async with session_factory() as session, session.begin():
            turn = await get_turn(session, turn_id)
            if (
                turn is None
                or turn.claim_token != claim_token
                or turn.status != ChatTurnStatus.RUNNING.value
            ):
                return None
            seq = turn.last_seq
            attempt = turn.attempt
            revision = turn.output_revision
            for row in rows:
                seq += 1
                session.add(
                    ChatTurnEvent(
                        turn_id=turn_id,
                        seq=seq,
                        attempt=attempt,
                        output_revision=revision,
                        type=row["type"],
                        segment_id=row.get("segment_id"),
                        tool_call_id=row.get("tool_call_id"),
                        payload_json=json.dumps(
                            row["payload"], ensure_ascii=False, separators=(",", ":")
                        ),
                    )
                )
            turn.last_seq = seq
            turn.updated_at = utcnow()
        return seq

    @staticmethod
    async def finalize_completed(
        *,
        session_factory: async_sessionmaker[AsyncSession],
        turn_id: str,
        claim_token: str,
        assistant_row: ChatMessage,
        done_payload: dict[str, Any],
        citations: list[dict[str, int | str]] | None = None,
    ) -> TurnCompletionOutcome:
        """最终 assistant、引用、终态与完成事件原子提交（轮次唯一最终消息）。

        完成提交与取消裁决共享事务内的条件检查（规格 §14）：首条语句以条件
        no-op UPDATE 取 SQLite 写锁并原子断言「运行中 + 执行身份匹配 + 未受理
        取消」（先例 runtime.turn_write_allowed）。取消先提交 → 匹配零行，
        拒绝完成（不写最终消息、done 事件与状态，已持久化部分输出保留），
        返回 CANCELLED 交执行侧按取回收口；完成先提交 → 取消随后落库只能读到
        COMPLETED 终态，不产生两个终态。执行身份失配 / 已终态返回 LOST。

        引用条目先于 done 事件逐条落库（SSE 词汇先例：citation 流事件在
        done 之前下发，渲染仍以最终消息的 citations 为事实源）。
        """
        async with session_factory() as session, session.begin():
            result = cast(
                "CursorResult[tuple[()]]",
                await session.execute(
                    update(ChatTurn)
                    .where(
                        ChatTurn.id == turn_id,
                        ChatTurn.claim_token == claim_token,
                        ChatTurn.status == ChatTurnStatus.RUNNING.value,
                        ChatTurn.cancel_requested.is_(False),
                    )
                    .values(claim_token=ChatTurn.claim_token)
                    .execution_options(synchronize_session=False)
                ),
            )
            turn = await get_turn(session, turn_id)
            if turn is None:
                return TurnCompletionOutcome.LOST
            if result.rowcount != 1:
                if (
                    turn.status == ChatTurnStatus.RUNNING.value
                    and turn.claim_token == claim_token
                    and bool(turn.cancel_requested)
                ):
                    # 取消先提交：拒绝完成提交（迟到输出不得转回完成）。
                    return TurnCompletionOutcome.CANCELLED
                return TurnCompletionOutcome.LOST
            now = utcnow()
            session.add(assistant_row)
            await session.flush()
            turn.status = ChatTurnStatus.COMPLETED.value
            turn.final_message_id = assistant_row.id
            turn.finished_at = now
            turn.updated_at = now
            for citation in citations or []:
                turn.last_seq += 1
                session.add(
                    ChatTurnEvent(
                        turn_id=turn_id,
                        seq=turn.last_seq,
                        attempt=turn.attempt,
                        output_revision=turn.output_revision,
                        type=ChatTurnEventType.CITATION.value,
                        payload_json=json.dumps(
                            citation, ensure_ascii=False, separators=(",", ":")
                        ),
                    )
                )
            turn.last_seq += 1
            session.add(
                ChatTurnEvent(
                    turn_id=turn_id,
                    seq=turn.last_seq,
                    attempt=turn.attempt,
                    output_revision=turn.output_revision,
                    type=ChatTurnEventType.DONE.value,
                    payload_json=json.dumps(
                        done_payload, ensure_ascii=False, separators=(",", ":")
                    ),
                )
            )
            chat = await session.get(ChatSession, turn.session_id)
            if chat is not None:
                chat.updated_at = now
        return TurnCompletionOutcome.COMPLETED

    @staticmethod
    async def finalize_terminal(
        *,
        session_factory: async_sessionmaker[AsyncSession],
        turn_id: str,
        claim_token: str,
        status: ChatTurnStatus,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> bool:
        """执行侧终态收口（取消 / 失败）：条件更新，只有一个有效终态。"""
        async with session_factory() as session, session.begin():
            turn = await get_turn(session, turn_id)
            if (
                turn is None
                or turn.claim_token != claim_token
                or turn.status != ChatTurnStatus.RUNNING.value
            ):
                return False
            now = utcnow()
            turn.status = status.value
            turn.error_code = error_code
            turn.error_message = error_message
            turn.finished_at = now
            turn.updated_at = now
        return True


__all__ = [
    "CHAT_TURN_JOB_TYPE",
    "ActiveTurnRegistry",
    "ChatTurnService",
    "TurnCompletionOutcome",
    "TurnEventBroadcaster",
    "find_active_turn",
    "get_turn",
    "load_execution",
    "parse_timezone",
    "serialize_timezone",
    "turn_job_input",
    "turn_out",
]
