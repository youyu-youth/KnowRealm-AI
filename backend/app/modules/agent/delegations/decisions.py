"""不确定请求的等待快照与显式决定；不改写任何 checkpoint。"""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.modules.agent.delegations.models import AgentDelegation, DelegationDecision
from app.modules.agent.delegations.schemas import DelegationSelection
from app.modules.agent.delegations.service import (
    cancel_children,
    conflict,
    emit_state,
    job_delegation,
    unresolved_requests,
)
from app.modules.agent.message_service import validate_sendable_chat
from app.modules.agent.models import ChatSession
from app.modules.agent.turns.effects import effect_args_fingerprint
from app.modules.agent.turns.models import ChatTurn, ChatTurnWait
from app.modules.agent.turns.schemas import (
    ChatTurnResumeRequest,
    ChatTurnWaitingKind,
    ChatTurnWaitingReason,
)
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.schemas import ProcessingJobStatus
from app.modules.settings.config import load_llm_provider


async def reconcile_uncertain(
    session: AsyncSession, turn: ChatTurn, waits: list[ChatTurnWait]
) -> bool:
    children = [
        child for wait in waits if (child := await job_delegation(session, wait)) is not None
    ]
    if not children or any(child.status in ("QUEUED", "RUNNING") for child in children):
        return False
    unsafe = next(
        (
            child
            for child in children
            if child.status == "INTERRUPTED"
            and child.error_code in ("MODEL_CONTEXT_INCOMPATIBLE", "CHAT_TURN_RESUME_UNSAFE")
        ),
        None,
    )
    if unsafe:
        turn.status, turn.updated_at = "WAITING_USER", utcnow()
        turn.waiting_reason = ChatTurnWaitingReason(
            kind=ChatTurnWaitingKind.CHECKPOINT_MISSING
            if unsafe.error_code == "CHAT_TURN_RESUME_UNSAFE"
            else ChatTurnWaitingKind.GRAPH_INCOMPATIBLE,
            detail="子执行状态无法兼容恢复，请停止后重新提问",
        ).model_dump_json()
        return True
    unknown = [
        DelegationSelection(
            execution_id=child.id,
            execution_attempt=child.attempt,
            request_ids=await unresolved_requests(session, child),
        )
        for child in children
        if child.status == "INTERRUPTED"
    ]
    if not unknown:
        return False
    turn.status, turn.updated_at = "WAITING_USER", utcnow()
    turn.waiting_reason = ChatTurnWaitingReason(
        kind=ChatTurnWaitingKind.DELEGATION_UNCERTAIN,
        snapshot_id=str(uuid4()),
        detail="知识任务的模型请求结果不明；重试可能再次计费，也可接受已有结果。",
        delegations=unknown,
    ).model_dump_json()
    return True


async def apply_decision(
    factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
    turn_id: str,
    payload: ChatTurnResumeRequest,
) -> None:
    from app.modules.agent.turns.service import (
        ensure_turn_job,
        load_execution,
        resume_blocked_reason,
    )

    if payload.decision_id is None or payload.snapshot_id is None:
        raise conflict("委派决定需要稳定决定 ID 和等待快照")
    fingerprint = effect_args_fingerprint(payload.model_dump())
    provider = await asyncio.to_thread(load_llm_provider, data_dir)
    async with factory() as session, session.begin():
        await session.execute(
            update(ChatTurn).where(ChatTurn.id == turn_id).values(updated_at=ChatTurn.updated_at)
        )
        previous = await session.get(DelegationDecision, payload.decision_id)
        if previous is not None:
            if previous.turn_id != turn_id or previous.fingerprint != fingerprint:
                raise conflict("同一决定 ID 的参数不一致")
            return
        root = await session.get(ChatTurn, turn_id)
        if root is None or root.cancel_requested or root.status != "WAITING_USER":
            raise conflict("原等待已结束或任务已停止")
        reason = ChatTurnWaitingReason.model_validate_json(root.waiting_reason or "{}")
        if (
            reason.kind != ChatTurnWaitingKind.DELEGATION_UNCERTAIN
            or reason.snapshot_id != payload.snapshot_id
        ):
            raise conflict("等待快照已过期")
        available = {item.execution_id: item for item in reason.delegations}
        selected = {item.execution_id: item for item in payload.delegations}
        if (
            not selected
            or len(selected) != len(payload.delegations)
            or any(key not in available or item != available[key] for key, item in selected.items())
        ):
            raise conflict("选择与原子执行尝试或不确定请求不一致")
        if payload.decision_kind == "ACCEPT_PARTIAL" and selected != available:
            raise conflict("接受已有结果需要确认全部不确定分支")
        blocked = await resume_blocked_reason(data_dir, load_execution(root), provider)
        if blocked is not None:
            raise conflict(blocked[1])
        chat = await session.get(ChatSession, root.session_id)
        if chat is None:
            raise conflict("对话已删除")
        await validate_sendable_chat(session, chat)
        children: list[AgentDelegation] = []
        for item in selected.values():
            child = await session.get(AgentDelegation, item.execution_id)
            if (
                child is None
                or child.turn_id != turn_id
                or child.attempt != item.execution_attempt
                or child.status != "INTERRUPTED"
                or await unresolved_requests(session, child) != item.request_ids
            ):
                raise conflict("子执行事实与等待快照不一致")
            children.append(child)
        session.add(
            DelegationDecision(
                id=payload.decision_id,
                turn_id=turn_id,
                fingerprint=fingerprint,
                snapshot_id=payload.snapshot_id,
                decision_json=payload.model_dump_json(),
            )
        )
        await session.flush()
        now = utcnow()
        if payload.decision_kind == "RETRY_DELEGATIONS":
            for child in children:
                selection = selected[child.id]
                if len(selection.request_ids) != 1:
                    raise conflict("无法可靠关联多个不确定请求，请接受已有结果或新任务")
                child.status, child.result_json, child.error_code = "QUEUED", None, None
                child.retry_request_id, child.decision_id = (
                    selection.request_ids[0],
                    payload.decision_id,
                )
                child.claim_token, child.finished_at, child.updated_at = None, None, now
                job = await session.get(ProcessingJob, child.job_id)
                if job is None:
                    raise conflict("原子任务调度记录缺失")
                job.status, job.finished_at, job.next_run_at = (
                    ProcessingJobStatus.PENDING,
                    None,
                    None,
                )
                job.error_code, job.error_message, job.updated_at = None, None, now
                waits = (
                    await session.scalars(
                        select(ChatTurnWait).where(
                            ChatTurnWait.turn_id == turn_id,
                            ChatTurnWait.target_type == "JOB",
                            ChatTurnWait.target_id == child.job_id,
                        )
                    )
                ).all()
                for wait in waits:
                    wait.result_json = None
                    wait.execution_attempt = None
                await emit_state(session, child)
            root.status, root.waiting_reason = (
                "WAITING_JOB",
                json.dumps({"kind": "BACKGROUND_TASK"}),
            )
        elif payload.decision_kind == "ACCEPT_PARTIAL":
            await cancel_children(session, turn_id, "用户接受已有结果；不确定请求和消费仍保留")
            root.status, root.waiting_reason = "QUEUED", None
            await ensure_turn_job(session, turn_id, now)
        else:
            raise conflict("原继续操作不授权重发不确定请求")
        root.updated_at = now
