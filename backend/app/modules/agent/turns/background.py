"""ChatTurn 后台结果等待：复用领域任务、框架 interrupt 与 JobRunner 领取对账。"""

import json
from collections.abc import Sequence
from enum import StrEnum
from typing import Any, Literal, cast
from uuid import uuid4

from langgraph.types import Interrupt
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.agent.runs.models import AgentOperation, AgentRun
from app.modules.agent.runs.schemas import RUN_TERMINAL_STATUSES, RunStatus
from app.modules.agent.runtime import AgentRuntimeContext
from app.modules.agent.turns.effects import current_tool_call_identity
from app.modules.agent.turns.models import ChatTurn, ChatTurnRun, ChatTurnWait
from app.modules.agent.turns.schemas import ChatTurnStatus, ChatTurnTaskOut
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.schemas import ProcessingJobStatus


class RunControlScope(StrEnum):
    EXCLUSIVE = "EXCLUSIVE"
    SHARED = "SHARED"
    INDEPENDENT = "INDEPENDENT"


def interrupt_bindings(items: Sequence[Interrupt]) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for item in items:
        raw: object = item.value
        value = cast(dict[str, object], raw) if isinstance(raw, dict) else {}
        wait_id = value.get("wait_id")
        if value.get("kind") == "BACKGROUND_TASK" and isinstance(wait_id, str):
            bindings[item.id] = wait_id
    return bindings


async def bind_run(
    session: AsyncSession, turn_id: str | None, run_id: str, scope: RunControlScope
) -> None:
    if turn_id is None:
        return
    existing = await session.get(ChatTurnRun, (turn_id, run_id))
    if scope == RunControlScope.INDEPENDENT or (
        existing is None and scope == RunControlScope.SHARED
    ):
        await session.execute(
            update(ChatTurnRun)
            .where(
                ChatTurnRun.run_id == run_id,
                ChatTurnRun.control_scope == RunControlScope.EXCLUSIVE.value,
            )
            .values(control_scope=scope.value)
        )
    if existing is not None:
        if scope == RunControlScope.INDEPENDENT:
            existing.control_scope = scope.value
        return
    session.add(ChatTurnRun(turn_id=turn_id, run_id=run_id, control_scope=scope.value))


def _result(value: str | None) -> dict[str, Any]:
    parsed: object = json.loads(value or "{}")
    return cast(dict[str, Any], parsed) if isinstance(parsed, dict) else {}


async def source_result(session: AsyncSession, wait: ChatTurnWait) -> dict[str, Any] | None:
    """只消费原对象的真实结果；失败/取消交模型明确转述，不重投来源任务。"""
    if wait.target_type == "RUN":
        run = await session.get(AgentRun, wait.target_id)
        if run is not None and run.status not in {s.value for s in RUN_TERMINAL_STATUSES}:
            return None
        operations = list(
            (
                await session.scalars(
                    select(AgentOperation)
                    .where(AgentOperation.run_id == wait.target_id)
                    .order_by(AgentOperation.created_at, AgentOperation.id)
                )
            ).all()
        )
        outputs: list[dict[str, Any]] = []
        for op in operations:
            result = _result(op.result_json)
            job_id = result.get("awaited_job_id")
            job = await session.get(ProcessingJob, job_id) if isinstance(job_id, str) else None
            outputs.append(
                {
                    "operation_id": op.id,
                    "action": op.action,
                    "status": op.status,
                    "result": result,
                    "error_code": op.error_code,
                    "background_result": _result(job.result_json) if job is not None else None,
                    "background_status": job.status if job is not None else None,
                    "background_error_code": job.error_code if job is not None else None,
                }
            )
        return {
            "ok": run is not None and run.status == RunStatus.COMPLETED.value,
            "run_id": wait.target_id,
            "status": run.status if run is not None else "MISSING",
            "operations": outputs,
        }
    from app.modules.agent.delegations.service import job_delegation, result_payload

    child = await job_delegation(session, wait)
    if child is not None:
        result = result_payload(child)
        if result is not None:
            wait.execution_attempt = child.attempt
        return result
    job = await session.get(ProcessingJob, wait.target_id)
    if job is not None and job.status in (ProcessingJobStatus.PENDING, ProcessingJobStatus.RUNNING):
        return None
    return {
        "ok": job is not None and job.status == ProcessingJobStatus.SUCCEEDED,
        "job_id": wait.target_id,
        "status": job.status if job is not None else "MISSING",
        "result": _result(job.result_json) if job is not None else {},
        "error_code": job.error_code if job is not None else None,
    }


async def prepare_wait(
    runtime: AgentRuntimeContext, target_type: Literal["RUN", "JOB"], target_id: str
) -> ChatTurnWait | None:
    identity = current_tool_call_identity()
    if runtime.turn_id is None or identity is None:
        return None
    async with runtime.session_factory() as session, session.begin():
        if not await runtime.turn_write_allowed(session):
            return None
        existing = await session.scalar(
            select(ChatTurnWait).where(
                ChatTurnWait.turn_id == runtime.turn_id,
                ChatTurnWait.namespace == identity.namespace,
                ChatTurnWait.logical_call_id == identity.logical_call_id,
            )
        )
        if existing is not None:
            if existing.target_type != target_type or existing.target_id != target_id:
                return None
            return existing
        source_operation_id: str | None = None
        if target_type == "RUN":
            run = await session.get(AgentRun, target_id)
            if run is None or run.session_id != runtime.session_id:
                return None
            await bind_run(session, runtime.turn_id, target_id, RunControlScope.SHARED)
        else:
            from app.modules.agent.delegations.service import job_delegation

            delegated = await job_delegation(
                session, ChatTurnWait(turn_id=runtime.turn_id, target_id=target_id)
            )
            # 任务引用必须来自本会话的已提交业务回执，不能凭模型猜 ID 取得结果。
            operation = await session.scalar(
                select(AgentOperation)
                .outerjoin(AgentRun, AgentOperation.run_id == AgentRun.id)
                .where(
                    func.json_extract(AgentOperation.result_json, "$.awaited_job_id") == target_id,
                    (AgentRun.session_id == runtime.session_id)
                    | (
                        func.json_extract(AgentOperation.authorization_json, "$.session_id")
                        == runtime.session_id
                    ),
                )
            )
            if operation is None and delegated is None:
                return None
            source_operation_id = operation.id if operation else None
            if operation is not None and operation.run_id is not None:
                await bind_run(session, runtime.turn_id, operation.run_id, RunControlScope.SHARED)
        wait = ChatTurnWait(
            id=str(uuid4()),
            turn_id=runtime.turn_id,
            namespace=identity.namespace,
            logical_call_id=identity.logical_call_id,
            target_type=target_type,
            target_id=target_id,
            source_operation_id=source_operation_id,
        )
        session.add(wait)
        await session.flush()
        result = await source_result(session, wait)
        if result is not None:
            wait.result_json = json.dumps(result, ensure_ascii=False)
        return wait


async def park_turn(
    session: AsyncSession, turn_id: str, claim_token: str, interrupts: dict[str, str]
) -> bool:
    claimed = await session.scalar(
        update(ChatTurn)
        .where(
            ChatTurn.id == turn_id,
            ChatTurn.claim_token == claim_token,
            ChatTurn.status == ChatTurnStatus.RUNNING.value,
            ChatTurn.cancel_requested.is_(False),
        )
        .values(status=ChatTurnStatus.WAITING_JOB.value, updated_at=utcnow())
        .returning(ChatTurn.id)
    )
    if claimed is None:
        return False
    turn = await session.get(ChatTurn, turn_id)
    assert turn is not None
    turn.waiting_reason = json.dumps({"kind": "BACKGROUND_TASK"})
    for interrupt_id, wait_id in interrupts.items():
        wait = await session.get(ChatTurnWait, wait_id)
        if wait is None or wait.turn_id != turn_id:
            raise ValueError("Invalid background interrupt binding")
        wait.interrupt_id = interrupt_id
    return True


async def task_states(session: AsyncSession, turn_id: str) -> list[ChatTurnTaskOut]:
    states: dict[tuple[str, str], ChatTurnTaskOut] = {}
    links = list(
        (await session.scalars(select(ChatTurnRun).where(ChatTurnRun.turn_id == turn_id))).all()
    )
    for link in links:
        run = await session.get(AgentRun, link.run_id)
        states[("RUN", link.run_id)] = ChatTurnTaskOut(
            target_type="RUN",
            target_id=link.run_id,
            status=run.status if run else "MISSING",
            control_scope=cast(Literal["EXCLUSIVE", "SHARED", "INDEPENDENT"], link.control_scope),
        )
    waits = list(
        (await session.scalars(select(ChatTurnWait).where(ChatTurnWait.turn_id == turn_id))).all()
    )
    for wait in waits:
        if wait.target_type == "JOB":
            from app.modules.agent.delegations.service import job_delegation

            child = await job_delegation(session, wait)
            job = await session.get(ProcessingJob, wait.target_id)
            states[("JOB", wait.target_id)] = ChatTurnTaskOut(
                target_type="JOB",
                target_id=wait.target_id,
                status=child.status if child else job.status if job else "MISSING",
                control_scope="EXCLUSIVE" if child else "SHARED",
                execution_id=child.id if child else None,
                agent_id="knowledge" if child else None,
                execution_attempt=child.attempt if child else None,
            )
    return list(states.values())


async def reconcile_waits(session: AsyncSession) -> None:
    # 复用调度入口；通知缺失与重启都按持久关系核对，不占执行槽轮询网络。
    from app.modules.agent.turns.service import ensure_turn_job

    await session.execute(
        update(ChatTurn)
        .where(ChatTurn.status == ChatTurnStatus.WAITING_JOB.value)
        .values(updated_at=ChatTurn.updated_at)
    )

    turns = list(
        (
            await session.scalars(
                select(ChatTurn).where(
                    ChatTurn.status == ChatTurnStatus.WAITING_JOB.value,
                    ChatTurn.cancel_requested.is_(False),
                )
            )
        ).all()
    )
    for turn in turns:
        waits = list(
            (
                await session.scalars(
                    select(ChatTurnWait).where(
                        ChatTurnWait.turn_id == turn.id,
                        ChatTurnWait.interrupt_id.is_not(None),
                    )
                )
            ).all()
        )
        ready = bool(waits)
        from app.modules.agent.delegations.decisions import reconcile_uncertain

        if await reconcile_uncertain(session, turn, waits):
            continue
        for wait in waits:
            from app.modules.agent.delegations.service import TERMINAL, job_delegation

            child = await job_delegation(session, wait)
            if child is not None and (
                child.status not in TERMINAL or wait.execution_attempt != child.attempt
            ):
                wait.result_json = None
            if wait.result_json is None:
                result = await source_result(session, wait)
                if result is not None:
                    wait.result_json = json.dumps(result, ensure_ascii=False)
            ready = ready and wait.result_json is not None
        if ready:
            claimed = await session.scalar(
                update(ChatTurn)
                .where(
                    ChatTurn.id == turn.id,
                    ChatTurn.status == ChatTurnStatus.WAITING_JOB.value,
                    ChatTurn.cancel_requested.is_(False),
                )
                .values(
                    status=ChatTurnStatus.QUEUED.value, waiting_reason=None, updated_at=utcnow()
                )
                .returning(ChatTurn.id)
            )
            if claimed is not None:
                await ensure_turn_job(session, turn.id, utcnow())


async def resume_results(
    runtime: AgentRuntimeContext, interrupts: dict[str, str]
) -> dict[str, object]:
    results: dict[str, object] = {}
    async with runtime.session_factory() as session:
        for interrupt_id, wait_id in interrupts.items():
            wait = await session.get(ChatTurnWait, wait_id)
            if wait is not None and wait.turn_id == runtime.turn_id:
                from app.modules.agent.delegations.service import job_delegation

                child = await job_delegation(session, wait)
                result = (
                    _result(wait.result_json)
                    if wait.result_json is not None
                    and (child is None or wait.execution_attempt == child.attempt)
                    else await source_result(session, wait)
                )
                if result is not None:
                    results[interrupt_id] = result
    return results
