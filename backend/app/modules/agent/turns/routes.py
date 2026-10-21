"""ChatTurn 公开 API：提交（202）、列表、快照、事件订阅（SSE）与取消。

事件订阅只读已提交事件：连接断开仅解除订阅，不触发状态转换；慢客户端不
阻塞生成（广播满即丢，超时按数据库游标补发）。SSE 事件词汇与旧流式路径
一致（status / token / tool_call / tool_result / citation / done / error），
前端与测试的载荷形状保持兼容。
"""

import asyncio
import json
from collections.abc import AsyncGenerator, Mapping
from datetime import datetime
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.modules.agent.turns.models import ChatTurn, ChatTurnEvent
from app.modules.agent.turns.projection import (
    build_output_text,
    event_payload,
    process_out_for,
)
from app.modules.agent.turns.runtime import TurnEventBroadcaster
from app.modules.agent.turns.schemas import (
    ChatTurnCancelOut,
    ChatTurnEventType,
    ChatTurnOut,
    ChatTurnResumeOut,
    ChatTurnResumeRequest,
    ChatTurnsPage,
    ChatTurnStatus,
    ChatTurnSubmitRequest,
)
from app.modules.agent.turns.service import ChatTurnService, parse_waiting_reason, turn_out
from app.shared.deps import get_db, require_launch_token
from app.shared.errors import CodedHTTPException
from app.shared.schemas import ErrorResponse

router = APIRouter(
    tags=["chat-turns"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)

# 通知丢失兜底：订阅端最长等待后按数据库游标补拉（慢客户端重连同步同路径）。
EVENT_POLL_FALLBACK_SECONDS = 15.0


def _sse(event: str, payload: Mapping[str, object]) -> ServerSentEvent:
    return ServerSentEvent(event=event, data=json.dumps(payload, separators=(",", ":")))


def _process_payload(turn: ChatTurn, events: list[ChatTurnEvent]) -> dict[str, object]:
    return process_out_for(turn, events).model_dump(mode="json")


def _event_sse(row: ChatTurnEvent, turn: ChatTurn, seen: list[ChatTurnEvent]) -> ServerSentEvent:
    """单条持久事件 → 旧词汇 SSE 载荷（process 随已见事件投影刷新）。"""
    payload = event_payload(row)
    event_type = ChatTurnEventType(row.type)
    meta = {
        "seq": row.seq,
        "attempt": row.attempt,
        "output_revision": row.output_revision,
    }
    if event_type == ChatTurnEventType.TOKEN:
        return _sse(
            "token",
            {"text": payload.get("text", ""), "segment_id": row.segment_id or "", **meta},
        )
    if event_type == ChatTurnEventType.COMMENTARY:
        return _sse(
            "status",
            {
                "phase": "process_updated",
                "process": _process_payload(turn, seen),
                **meta,
            },
        )
    if event_type == ChatTurnEventType.TOOL_CALL:
        return _sse(
            "tool_call",
            {
                "tool": payload.get("tool", ""),
                "query": payload.get("query", ""),
                "tool_call_id": row.tool_call_id or "",
                "segment_id": row.segment_id or "",
                "process": _process_payload(turn, seen),
                **meta,
            },
        )
    if event_type == ChatTurnEventType.TOOL_RESULT:
        return _sse(
            "tool_result",
            {
                "tool": payload.get("tool", ""),
                "hits": payload.get("hits", 0),
                "ok": payload.get("ok", True),
                "tool_call_id": row.tool_call_id or "",
                "process": _process_payload(turn, seen),
                **meta,
            },
        )
    if event_type == ChatTurnEventType.CITATION:
        return _sse("citation", dict(payload))
    if event_type == ChatTurnEventType.REVISION:
        # 续跑正文版本边界（票 02）：被替换 segment 的本地拼接清空，后续 token
        # 追加在快照基准之后（不拼接两份半段正文）。baseline＝此刻服务端投影
        # （已剔除被替换段）：被替换段不在客户端本地分段（恢复 / 刷新后固化进
        # 快照 baseline）时，客户端以它重置基准（规格 §10 替换跨恢复生效）。
        return _sse(
            "status",
            {
                "phase": "revising",
                "replaces_segment": payload.get("replaces_segment"),
                "baseline": build_output_text(seen),
                **meta,
            },
        )
    # done：权威最终快照（message_id / content / memory_used / 提案与回执扩展）。
    done_payload: dict[str, object] = {
        "message_id": payload.get("message_id", ""),
        "content": payload.get("content", ""),
        "memory_used": payload.get("memory_used", []),
        **meta,
    }
    for key in (
        "memory_proposals",
        "research_proposals",
        "operation_proposals",
        "executed_operations",
    ):
        if key in payload:
            done_payload[key] = payload[key]
    done_payload["process"] = _process_payload(turn, seen)
    return _sse("done", done_payload)


def _terminal_sse(turn: ChatTurn, seen: list[ChatTurnEvent]) -> ServerSentEvent | None:
    """观察收口标记：FAILED → error，WAITING_USER → 带原因，其余停止态 → status。"""
    status = ChatTurnStatus(turn.status)
    if status == ChatTurnStatus.COMPLETED:
        return None  # done 事件已持久，无需合成
    if status == ChatTurnStatus.FAILED:
        code = turn.error_code or "CHAT_TURN_FAILED"
        return _sse(
            "error",
            {
                "code": code,
                "detail": turn.error_message or "回答生成失败，请稍后重试",
                "process": _process_payload(turn, seen),
            },
        )
    if status == ChatTurnStatus.WAITING_USER:
        reason = parse_waiting_reason(turn.waiting_reason)
        return _sse(
            "status",
            {
                "phase": "waiting_user",
                "reason": reason.model_dump(mode="json") if reason is not None else None,
                "process": _process_payload(turn, seen),
            },
        )
    return _sse(
        "status",
        {
            "phase": "cancelled" if status == ChatTurnStatus.CANCELLED else "interrupted",
            "process": _process_payload(turn, seen),
        },
    )


async def _event_stream(
    *,
    factory: async_sessionmaker[AsyncSession],
    broadcaster: TurnEventBroadcaster,
    turn_id: str,
    after_seq: int,
) -> AsyncGenerator[ServerSentEvent, None]:
    queue = broadcaster.subscribe(turn_id)
    cursor = after_seq
    last_status: str | None = None
    try:
        # 过程投影状态从 0 号事件完整重建（续订客户端只补流 after_seq 之后的事件，
        # 但 process 载荷须包含此前全部条目）；流只发 cursor 之后的事件。
        turn, all_events = await ChatTurnService.read_events_after(factory, turn_id, 0)
        seen = [row for row in all_events if row.seq <= after_seq]
        yield _sse("status", {"phase": "generating", "process": _process_payload(turn, seen)})
        while True:
            turn, events = await ChatTurnService.read_events_after(factory, turn_id, cursor)
            if (
                last_status == ChatTurnStatus.WAITING_JOB.value
                and turn.status == ChatTurnStatus.RUNNING.value
            ):
                yield _sse(
                    "status", {"phase": "generating", "process": _process_payload(turn, seen)}
                )
            last_status = turn.status
            if turn.compacted_seq > cursor:
                snapshot = turn_out(turn)
                seen = []
                cursor = snapshot.last_seq
                yield _sse(
                    "status",
                    {
                        "phase": "reset",
                        "snapshot": snapshot.model_dump(mode="json"),
                        "baseline": snapshot.output_text,
                        "seq": cursor,
                        "process": snapshot.process.model_dump(mode="json")
                        if snapshot.process
                        else None,
                    },
                )
            for row in events:
                seen.append(row)
                cursor = row.seq
                yield _event_sse(row, turn, seen)
            # 观察侧终态收口（含 INTERRUPTED）：订阅必须结束并带明确阶段，
            # 否则前端中断原因分支与观察收尾不可达；会话占用仍按业务终态。
            if ChatTurnStatus(turn.status).is_observer_terminal and cursor >= turn.last_seq:
                marker = _terminal_sse(turn, seen)
                if marker is not None:
                    yield marker
                return
            if turn.status == ChatTurnStatus.WAITING_JOB.value:
                snapshot = await ChatTurnService.get_snapshot(factory, turn_id)
                yield _sse(
                    "status",
                    {
                        "phase": "waiting_job",
                        "process": _process_payload(turn, seen),
                        "reason": {"kind": "BACKGROUND_TASK"},
                        "tasks": [
                            task.model_dump(mode="json") for task in snapshot.background_tasks
                        ]
                        if snapshot
                        else [],
                    },
                )
            # 通知降低延迟；丢失通知由超时补拉兜底（慢客户端断开后可重连同步）。
            try:
                await asyncio.wait_for(queue.get(), timeout=EVENT_POLL_FALLBACK_SECONDS)
            except TimeoutError:
                pass
    finally:
        broadcaster.unsubscribe(turn_id, queue)


@router.post(
    "/api/chat-sessions/{session_id}/turns",
    response_model=ChatTurnOut,
    status_code=202,
)
async def submit_chat_turn(
    session_id: UUID,
    payload: ChatTurnSubmitRequest,
    request: Request,
) -> ChatTurnOut:
    """提交回答生成：原子受理（user 消息 + 轮次 + job 同事务），立即返回实际状态。"""
    app = request.app
    snapshot, _created = await ChatTurnService.submit_turn(
        session_factory=app.state.session_factory,
        data_dir=app.state.data_dir,
        session_id=str(session_id),
        payload=payload,
    )
    return snapshot


@router.get("/api/chat-sessions/{session_id}/turns", response_model=ChatTurnsPage)
async def list_chat_turns(
    session_id: UUID,
    session: AsyncSession = Depends(get_db),
    active_only: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    before_seq_cursor: str | None = Query(default=None),
) -> ChatTurnsPage:
    """会话轮次列表（新到旧游标分页）；active_only 只取非终态轮次（至多一条）。"""
    before: tuple[datetime, str] | None = None
    if before_seq_cursor is not None:
        try:
            created_at_raw, turn_id = before_seq_cursor.split("|", 1)
            before = (datetime.fromisoformat(created_at_raw), turn_id)
        except ValueError:
            raise CodedHTTPException(
                code="CHAT_TURN_CURSOR_INVALID",
                status_code=400,
                detail="CHAT_TURN_CURSOR_INVALID：轮次游标无效",
            ) from None
    turns = await ChatTurnService.list_session_turn_outs(
        session,
        str(session_id),
        active_only=active_only,
        limit=limit,
        before=before,
    )
    next_before: tuple[datetime, str] | None = None
    if len(turns) == limit and not active_only:
        last = turns[-1]
        next_before = (last.created_at, last.id)
    return ChatTurnsPage(turns=turns, next_before=next_before)


@router.get("/api/chat-turns/{turn_id}", response_model=ChatTurnOut)
async def get_chat_turn(turn_id: UUID, request: Request) -> ChatTurnOut:
    app = request.app
    snapshot = await ChatTurnService.get_snapshot(app.state.session_factory, str(turn_id))
    if snapshot is None:
        raise CodedHTTPException(
            code="CHAT_TURN_NOT_FOUND", status_code=404, detail="对话轮次不存在"
        )
    return snapshot


@router.post("/api/chat-turns/{turn_id}/compact", response_model=ChatTurnOut)
async def compact_chat_turn(turn_id: UUID, request: Request) -> ChatTurnOut:
    snapshot = await ChatTurnService.compact_events(request.app.state.session_factory, str(turn_id))
    if snapshot is None:
        raise CodedHTTPException(
            code="CHAT_TURN_NOT_FOUND", status_code=404, detail="对话轮次不存在"
        )
    return snapshot


@router.get("/api/chat-turns/{turn_id}/events", response_class=EventSourceResponse)
async def chat_turn_events(
    turn_id: UUID,
    request: Request,
    after_seq: int = Query(default=0, ge=0),
) -> EventSourceResponse:
    """订阅轮次事件：补发 after_seq 之后的已提交事件并持续观察到终态。

    卸载 / 切换 / 刷新只关闭本连接（解除订阅），不影响后端执行；停止须经
    cancel 端点的持久指令落实。
    """
    app = request.app
    factory = app.state.session_factory
    # 先做存在性校验（生成器内的异常无法转为 HTTP 错误）。
    await ChatTurnService.read_events_after(factory, str(turn_id), after_seq)
    return EventSourceResponse(
        _event_stream(
            factory=factory,
            broadcaster=cast(TurnEventBroadcaster, app.state.turn_broadcaster),
            turn_id=str(turn_id),
            after_seq=after_seq,
        )
    )


@router.post("/api/chat-turns/{turn_id}/cancel", response_model=ChatTurnCancelOut)
async def cancel_chat_turn(turn_id: UUID, request: Request) -> ChatTurnCancelOut:
    """持久取消：返回实际状态与 cancel_requested（RUNNING 在途＝「正在停止」）。"""
    app = request.app
    snapshot = await ChatTurnService.cancel_turn(
        session_factory=app.state.session_factory,
        turn_id=str(turn_id),
        active=app.state.turn_active_registry,
    )
    if snapshot is None:
        raise CodedHTTPException(
            code="CHAT_TURN_NOT_FOUND", status_code=404, detail="对话轮次不存在"
        )
    from app.modules.agent.delegations.worker import cleanup_turn

    await cleanup_turn(app.state.session_factory, app.state.chat_checkpointer, str(turn_id))
    return ChatTurnCancelOut(turn=snapshot)


@router.post("/api/chat-turns/{turn_id}/resume", response_model=ChatTurnResumeOut)
async def resume_chat_turn(
    turn_id: UUID, _payload: ChatTurnResumeRequest, request: Request
) -> ChatTurnResumeOut:
    """继续执行（票 02）：重验等待原因与恢复条件后重新排队。

    类型化决定（RETRY_AFTER_FIX）只是声明阻塞条件已处理；不批准业务提案、
    不构成重新授权、不改写原输入／模型／范围。继续与停止都是持久指令。
    """
    app = request.app
    if _payload.decision_kind != "RETRY_AFTER_FIX":
        from app.modules.agent.delegations.decisions import apply_decision

        await apply_decision(app.state.session_factory, app.state.data_dir, str(turn_id), _payload)
        if _payload.decision_kind == "ACCEPT_PARTIAL":
            from app.modules.agent.delegations.worker import cleanup_turn

            await cleanup_turn(app.state.session_factory, app.state.chat_checkpointer, str(turn_id))
        snapshot = await ChatTurnService.get_snapshot(app.state.session_factory, str(turn_id))
        if snapshot is None:
            raise CodedHTTPException(
                code="CHAT_TURN_NOT_FOUND", status_code=404, detail="对话轮次不存在"
            )
        return ChatTurnResumeOut(turn=snapshot)
    snapshot = await ChatTurnService.resume_turn(
        session_factory=app.state.session_factory,
        data_dir=app.state.data_dir,
        turn_id=str(turn_id),
    )
    if snapshot is None:
        raise CodedHTTPException(
            code="CHAT_TURN_NOT_FOUND", status_code=404, detail="对话轮次不存在"
        )
    return ChatTurnResumeOut(turn=snapshot)
