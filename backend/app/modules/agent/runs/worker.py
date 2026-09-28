"""AGENT_RUN 推进 worker（通用 Agent 第二阶段工单 05，spec 决策 6/7/8）。

JobRunner 内以 ``WorkerSpec`` 声明式接入（ADR-0012）：触发 job 是无状态触发器
（input 仅 run_id），Run 状态是唯一事实源；推进 worker 只认 RUNNING，唤醒仅由
显式动作触发（继续指令 / 失败项重试 / 取消，见 service.RunControlService）。

逐 operation 一事务原子执行（业务写与 operation 终态同事务；失败整体回滚＝
未发生，再以独立小事务落 FAILED＋稳定错误码——直执行先例）：

- 每步前重检取消 / 授权 / 版本（快照重验）；授权＝Run 固化依据叠加同进程会话
  覆盖取更严格者——同进程降档即时约束后续步骤（升档不放宽；重启后覆盖为空＝
  仅固化依据）；
- 部分失败：独立项继续；依赖失败项（或跳过项）的后续步骤置 SKIPPED；
- 冲突（OPERATION_SNAPSHOT_STALE）与需确认（OPERATION_APPROVAL_REQUIRED）
  转 WAITING_USER 保留已成功结果，等用户显式处理后唤醒；
- 终态判定：全部成功＝COMPLETED；存在失败 / 跳过项＝PARTIAL_COMPLETED；
  取消＝CANCELLED；系统性故障由失败记账落 FAILED。

触发交接（工单 05 review）：job 收尾时 Run 仍 RUNNING 即补投触发——显式唤醒可能
落在「推进已停止、job 未收尾」的窗口里被 enqueue_trigger 的守卫跳过；不补投会留下
「RUNNING 且无活动触发」的悬挂任务。

计划结构损坏（run.plan_json 非法 JSON / 形状不符）：执行口径严格读计划，整任务
停止并落 AGENT_RUN_PLAN_INVALID（未执行项 SKIPPED）——不得降级为空计划继续执行
（排序与依赖判定会静默失效，工单 05 review）。

循环有界：每一步必定落定一个操作（成功 / 失败 / 跳过）或转入等待 / 终态，
步数上界＝操作数＋1，无死循环可能。
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.modules.agent.auth_mode import effective_session_auth_mode
from app.modules.agent.operations.registry import (
    OPERATION_TRANSIENT_ERROR,
    TRANSIENT_MAX_RETRIES,
    OperationSpec,
    get_operation,
    is_transient_exception,
    run_operation_applier,
    should_execute_directly,
)
from app.modules.agent.runs.models import AgentOperation, AgentRun
from app.modules.agent.runs.schemas import (
    AGENT_RUN_PLAN_INVALID,
    OPERATION_DEPENDENCY_FAILED,
    WAITABLE_OPERATION_ERROR_CODES,
    AuthMode,
    OperationStatus,
    PlanCorruptError,
    RunStatus,
    plan_dependencies,
    require_plan_out,
)
from app.modules.agent.runs.service import (
    AGENT_RUN_JOB_TYPE,
    append_attempt,
    cancel_pending_operations,
    enqueue_trigger,
    list_run_operations,
    operation_snapshot_stale,
    order_run_operations,
    settle_run,
)
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.runner import (
    CancelClaim,
    ClaimCheck,
    ClaimedJob,
    LoopFailure,
    Ready,
    RunnerContext,
    WorkerSpec,
    mark_failed,
    recover_running_to_failed,
)
from app.modules.jobs.schemas import ProcessingJobStatus
from app.shared.errors import CodedHTTPException
from app.shared.events import RecordInvalidationNotifier

# 系统性故障（非编码异常 / 环境故障）的稳定错误码：job 与 Run 一并落 FAILED。
AGENT_RUN_FAILED = "AGENT_RUN_FAILED"


@dataclass(frozen=True)
class _ClaimedRun(ClaimedJob):
    """Run 级任务：无 record 主体（record_id 坐标位承载 run_id，notifier 协议点
    以此为准，先例见课程级 QUIZ_GRADING）。"""

    run_id: str


async def find_candidate(session: AsyncSession, now: datetime) -> ProcessingJob | None:
    return (
        await session.scalars(
            select(ProcessingJob)
            .where(
                ProcessingJob.job_type == AGENT_RUN_JOB_TYPE.value,
                ProcessingJob.status == ProcessingJobStatus.PENDING,
                (ProcessingJob.next_run_at.is_(None) | (ProcessingJob.next_run_at <= now)),
            )
            .order_by(ProcessingJob.created_at)
            .limit(1)
        )
    ).one_or_none()


async def validate_claim(
    session: AsyncSession,
    job: ProcessingJob,
    _record_id: str,
    _preflight: None,
) -> ClaimCheck[_ClaimedRun]:
    """领取闸门：Run 不存在或已非 RUNNING（等待 / 终态）即作废触发 job。

    等待态不消费触发（唤醒只由显式动作重新投递，spec 决策 7）；已终态 Run 的
    残留触发直接取消（不再推进）。
    """
    input_data: object = json.loads(job.input_json)
    run_id = (
        cast(dict[str, object], input_data).get("run_id") if isinstance(input_data, dict) else None
    )
    if not isinstance(run_id, str):
        return CancelClaim("run_missing")
    run = await session.get(AgentRun, run_id)
    if run is None:
        return CancelClaim("run_missing")
    if run.status != RunStatus.RUNNING.value:
        return CancelClaim("run_not_running")
    return Ready(_ClaimedRun(job_id=job.id, record_id=run_id, run_id=run_id))


def _operation_params(operation: AgentOperation) -> dict[str, Any]:
    """操作载荷 JSON（计划项逐项参数）：坏值转稳定错误码（单项失败不炸推进）。"""
    try:
        value: object = json.loads(operation.payload_json)
    except ValueError as exc:
        raise CodedHTTPException(
            code="PROPOSAL_PAYLOAD_INVALID",
            status_code=422,
            detail="操作载荷不符合该动作的结构要求",
        ) from exc
    if not isinstance(value, dict):
        raise CodedHTTPException(
            code="PROPOSAL_PAYLOAD_INVALID",
            status_code=422,
            detail="操作载荷不符合该动作的结构要求",
        )
    return cast(dict[str, Any], value)


def _authorized(run: AgentRun, spec: OperationSpec[Any]) -> bool:
    """每步前授权重检（spec 决策 6/9、用户故事 6）：按 Run 固化依据执法，并叠加
    同进程会话覆盖取更严格者——同进程降档即时约束后续步骤（继续 / 重试不构成
    重新授权）；升档不放宽。覆盖为空（未切过档 / 重启后）＝仅固化依据，跨重启
    接续不回放会话档位。

    - 已批准计划（proposal_id 非空）：对象集合＋参数＋版本即授权，操作只从计划
      建立，恒在已批准集合内（显式批准保留，spec Q3）；
    - 档位授权 Run（proposal_id 空）：按固化档与会话覆盖中更严格者的分流规则复核
      该操作级别；已不允许自动执行该级别 → 授权失效，转等待用户确认。
    """
    if run.proposal_id is not None:
        return True
    mode = AuthMode(run.auth_mode)
    if run.session_id is not None:
        mode = effective_session_auth_mode(run.session_id, mode)
    return should_execute_directly(mode, spec.level)


def _mark_operation(
    operation: AgentOperation,
    status: OperationStatus,
    *,
    now: datetime,
    error_code: str | None = None,
    result: object | None = None,
) -> None:
    operation.status = status.value
    operation.error_code = error_code
    if result is not None:
        operation.result_json = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    operation.updated_at = now
    operation.finished_at = now
    if error_code is not None:
        append_attempt(operation, error_code, now=now)


def _wait_for_user(run: AgentRun, error_code: str, *, now: datetime) -> None:
    """冲突 / 需确认：停止推进转 WAITING_USER，保留已成功结果（spec 决策 7/8）。"""
    run.status = RunStatus.WAITING_USER.value
    run.waiting_reason = error_code
    run.updated_at = now


def _settle_from_operations(run: AgentRun, operations: list[AgentOperation]) -> None:
    """终态判定：存在失败 / 跳过项＝部分完成，其余（全部成功）＝完成。

    按目标取最新一次操作结局：冲突解决走「重新预览授权 → 为该目标新建操作」，
    旧失败行保留为历史，被后续成功操作取代的目标不再计入部分完成（spec 决策 3
    的终态判定以任务目标的实际结局为准，operation 行是逐项历史）。
    """
    latest: dict[str, str] = {}
    for operation in operations:
        key = (
            f"{operation.action}:{operation.target_id}"
            if operation.target_id is not None
            else operation.id
        )
        latest[key] = operation.status
    failed = any(
        status in (OperationStatus.FAILED.value, OperationStatus.SKIPPED.value)
        for status in latest.values()
    )
    settle_run(run, RunStatus.PARTIAL_COMPLETED if failed else RunStatus.COMPLETED)


def _dependency_blocked(dependencies: list[str], statuses: dict[str, str]) -> bool:
    """依赖项未全部成功即阻塞（依赖失败 / 跳过的后续步骤置 SKIPPED，spec 决策 8）。"""
    return any(
        statuses.get(dependency) != OperationStatus.SUCCEEDED.value for dependency in dependencies
    )


async def _record_step_retry(
    session_factory: async_sessionmaker[AsyncSession], run_id: str, operation_id: str
) -> bool:
    """瞬时失败记账（独立小事务，工单 06 spec 决策 20）：attempts 递增＋
    attempts_json 留痕、状态保持 PLANNED（交回推进循环重试，下轮从头重检
    取消 / 授权 / 版本）。返回 False＝重试额度耗尽（调用方转失败记账）。"""
    now = utcnow()
    async with session_factory() as session, session.begin():
        operation = await session.get(AgentOperation, operation_id)
        if (
            operation is None
            or operation.status != OperationStatus.PLANNED.value
            or operation.attempts >= 1 + TRANSIENT_MAX_RETRIES
        ):
            return False
        operation.attempts += 1
        operation.updated_at = now
        append_attempt(operation, OPERATION_TRANSIENT_ERROR, now=now)
        logger.info(
            "agent_run_step_transient_retry",
            run_id=run_id,
            step_id=operation_id,
            attempt=operation.attempts,
        )
        return True


async def _record_step_failure(
    session_factory: async_sessionmaker[AsyncSession], run_id: str, operation_id: str, code: str
) -> None:
    """失败记账（独立小事务，业务写已随主事务回滚＝未发生）：operation 落 FAILED
    ＋稳定错误码；冲突 / 需确认再转 WAITING_USER 等用户处理。"""
    now = utcnow()
    async with session_factory() as session, session.begin():
        operation = await session.get(AgentOperation, operation_id)
        run = await session.get(AgentRun, run_id)
        if operation is not None and operation.status == OperationStatus.PLANNED.value:
            _mark_operation(operation, OperationStatus.FAILED, now=now, error_code=code)
        if run is not None and run.status == RunStatus.RUNNING.value:
            if code in WAITABLE_OPERATION_ERROR_CODES:
                _wait_for_user(run, code, now=now)


async def advance_step(session_factory: async_sessionmaker[AsyncSession], run_id: str) -> bool:
    """推进一个操作（一次原子事务）；返回是否继续推进。

    事务内顺序：取消检查 → 待执行项 → 依赖阻塞 → 注册项装载 → 授权重检 →
    版本（快照）重验 → 应用器执行＋operation 落定。执行期编码异常整体回滚后由
    :func:`_record_step_failure` 落 FAILED；非编码异常上抛，由失败记账把 job 与
    Run 一并翻 FAILED（系统性故障停止推进，spec 决策 8）。
    """
    operation_id: str | None = None
    async with session_factory() as session:
        try:
            async with session.begin():
                run = await session.get(AgentRun, run_id)
                if run is None or run.status != RunStatus.RUNNING.value:
                    return False
                if run.cancel_requested:
                    # 取消：不新增动作、已提交结果保留（spec 用户故事 26）。取消
                    # 不读计划（不推进任何步骤，坏的 plan_json 也不影响收尾）。
                    cancelled = await cancel_pending_operations(session, run)
                    settle_run(run, RunStatus.CANCELLED)
                    logger.info("agent_run_cancelled", run_id=run_id, cancelled=cancelled)
                    return False
                # 执行口径严格读计划：损坏即上抛（失败记账落 AGENT_RUN_PLAN_INVALID、
                # Run FAILED、未执行项 SKIPPED），绝不降级为空计划继续执行（排序与
                # 依赖判定会静默失效，spec 决策 8/13）。
                plan = require_plan_out(run.plan_json, run.plan_version)
                operations = order_run_operations(
                    await list_run_operations(session, run_id), run.plan_json, run.plan_version
                )
                pending = [
                    operation
                    for operation in operations
                    if operation.status == OperationStatus.PLANNED.value
                ]
                if not pending:
                    _settle_from_operations(run, operations)
                    logger.info("agent_run_settled", run_id=run_id, status=run.status)
                    return False
                operation = pending[0]
                operation_id = operation.id
                now = utcnow()
                statuses = {item.id: item.status for item in operations}
                if _dependency_blocked(
                    plan_dependencies(plan).get(operation.id, []),
                    statuses,
                ):
                    _mark_operation(
                        operation,
                        OperationStatus.SKIPPED,
                        now=now,
                        error_code=OPERATION_DEPENDENCY_FAILED,
                    )
                    logger.info("agent_run_step_skipped", run_id=run_id, step_id=operation.id)
                    return True
                spec = get_operation(operation.action)
                if spec is None:
                    _mark_operation(
                        operation,
                        OperationStatus.FAILED,
                        now=now,
                        error_code="OPERATION_NOT_REGISTERED",
                    )
                    _wait_for_user(run, "OPERATION_NOT_REGISTERED", now=now)
                    return False
                if not _authorized(run, spec):
                    _mark_operation(
                        operation,
                        OperationStatus.FAILED,
                        now=now,
                        error_code="OPERATION_APPROVAL_REQUIRED",
                    )
                    _wait_for_user(run, "OPERATION_APPROVAL_REQUIRED", now=now)
                    logger.info(
                        "agent_run_step_approval_required", run_id=run_id, step_id=operation.id
                    )
                    return False
                params = _operation_params(operation)
                if await operation_snapshot_stale(session, spec, operation, params):
                    _mark_operation(
                        operation,
                        OperationStatus.FAILED,
                        now=now,
                        error_code="OPERATION_SNAPSHOT_STALE",
                    )
                    _wait_for_user(run, "OPERATION_SNAPSHOT_STALE", now=now)
                    logger.info("agent_run_step_conflict", run_id=run_id, step_id=operation.id)
                    return False
                result = await run_operation_applier(session, spec, operation.payload_json)
                _mark_operation(
                    operation,
                    OperationStatus.SUCCEEDED,
                    now=now,
                    result=result.model_dump(mode="json"),
                )
                run.updated_at = now
                return True
        except CodedHTTPException as exc:
            # 业务写已回滚（未发生）；独立小事务落 FAILED＋稳定错误码（诊断不断链）。
            assert operation_id is not None
            await _record_step_failure(session_factory, run_id, operation_id, exc.code)
            logger.info(
                "agent_run_step_failed", run_id=run_id, step_id=operation_id, error_code=exc.code
            )
            return exc.code not in WAITABLE_OPERATION_ERROR_CODES
        except OperationalError as exc:
            # 瞬时故障（SQLITE_BUSY 等锁竞争，工单 06 spec 决策 20）：原 operation
            # 身份下自动重试 ≤2 次——业务事务已回滚＝未发生，独立小事务记账
            # （attempts 递增留痕、保持 PLANNED）后交回推进循环；重试轮从头重检
            # 取消 / 授权 / 版本。耗尽按独立项失败落 FAILED 继续推进其余步骤；
            # 非瞬时 OperationalError 上抛（系统性故障口径不变）。
            assert operation_id is not None
            if not is_transient_exception(exc):
                raise
            if await _record_step_retry(session_factory, run_id, operation_id):
                return True
            await _record_step_failure(
                session_factory, run_id, operation_id, OPERATION_TRANSIENT_ERROR
            )
            logger.info(
                "agent_run_step_transient_exhausted",
                run_id=run_id,
                step_id=operation_id,
            )
            return True


async def advance_run(session_factory: async_sessionmaker[AsyncSession], run_id: str) -> str:
    """推进循环：逐步执行至终态 / 等待 / 无待执行项，返回 Run 最终状态。"""
    while await advance_step(session_factory, run_id):
        pass
    async with session_factory() as session:
        run = await session.get(AgentRun, run_id)
        return run.status if run is not None else RunStatus.FAILED.value


async def execute(
    ctx: _ClaimedRun,
    _runtime: RunnerContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> str:
    return await advance_run(session_factory, ctx.run_id)


async def writeback(
    ctx: _ClaimedRun,
    run_status: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> bool:
    """触发 job 收尾：记 Run 落定状态（job 是无状态触发器，不承载任务状态）。

    收尾兼做**触发交接**（工单 05 review）：显式唤醒（继续 / 重试 / 计划追加）可能
    落在本 job 收尾前的窗口——那时 :func:`enqueue_trigger` 看到本 job 仍 RUNNING
    而跳过投递；Run 若已被重新置为 RUNNING（推进事务已提交、job 未收尾）就必须在
    这里补投，否则留下「RUNNING 且无活动触发」的悬挂任务（只能等重启恢复）。
    先 flush 落定 job，守卫与部分唯一索引才都看到它不再是活动触发。
    """
    async with session_factory() as session, session.begin():
        job = await session.get(ProcessingJob, ctx.job_id)
        if job is None or job.status != ProcessingJobStatus.RUNNING:
            return False
        now = utcnow()
        job.status = ProcessingJobStatus.SUCCEEDED
        job.progress = 1
        job.next_run_at = None
        job.result_json = json.dumps(
            {"run_id": ctx.run_id, "run_status": run_status}, separators=(",", ":")
        )
        job.error_code = None
        job.error_message = None
        job.finished_at = now
        job.updated_at = now
        await session.flush()
        run = await session.get(AgentRun, ctx.run_id)
        if run is not None and run.status == RunStatus.RUNNING.value:
            await enqueue_trigger(session, run.id)
            logger.info("agent_run_trigger_handoff", run_id=run.id)
    return True


def failure_code(ctx: _ClaimedRun, exc: Exception) -> str | None:
    """系统性故障码：计划损坏单独成码（稳定可诊断），其余归 AGENT_RUN_FAILED。"""
    if isinstance(exc, PlanCorruptError):
        logger.warning("agent_run_plan_corrupt", run_id=ctx.run_id)
        return AGENT_RUN_PLAN_INVALID
    return AGENT_RUN_FAILED


async def apply_failure(
    ctx: _ClaimedRun,
    session: AsyncSession,
    job: ProcessingJob,
    _record: Any,
    error_code: str,
    now: datetime,
) -> bool:
    """系统性故障：job 与 Run 一并落 FAILED，未执行项置 SKIPPED（停止推进）。"""
    mark_failed(job, code=error_code, message="任务推进失败", now=now)
    run = await session.get(AgentRun, ctx.run_id)
    if run is not None and run.status == RunStatus.RUNNING.value:
        for operation in await list_run_operations(session, ctx.run_id):
            if operation.status == OperationStatus.PLANNED.value:
                operation.status = OperationStatus.SKIPPED.value
                operation.updated_at = now
                operation.finished_at = now
        settle_run(run, RunStatus.FAILED, now=now)
    return True


def agent_run_spec(
    session_factory: async_sessionmaker[AsyncSession],
    record_notifier: RecordInvalidationNotifier,
) -> WorkerSpec[None, _ClaimedRun, str]:
    def classify(_exc: Exception) -> LoopFailure:
        return LoopFailure(
            event="agent_run_advance_unexpected_failure", error_code=AGENT_RUN_FAILED
        )

    async def recover() -> None:
        """重启恢复（spec 决策 7）：先按先例把中断的活动触发翻 FAILED，再扫描
        「RUNNING 且无活动触发 job」的 Run 重投触发——推进只认 PLANNED 操作，
        已成功项天然不重做。等待态 Run 不投递（唤醒仅显式动作）。"""
        await recover_running_to_failed(
            session_factory,
            record_notifier,
            AGENT_RUN_JOB_TYPE,
            "任务推进被意外中断",
        )
        async with session_factory() as session, session.begin():
            runs = list(
                (
                    await session.scalars(
                        select(AgentRun).where(AgentRun.status == RunStatus.RUNNING.value)
                    )
                ).all()
            )
            for run in runs:
                await enqueue_trigger(session, run.id)

    return WorkerSpec(
        name="agent_run_worker",
        job_type=AGENT_RUN_JOB_TYPE,
        poll_interval=0.25,
        find_candidate=find_candidate,
        validate_claim=validate_claim,
        execute=lambda ctx, runtime: execute(ctx, runtime, session_factory),
        writeback=lambda ctx, run_status: writeback(ctx, run_status, session_factory),
        failure_code=failure_code,
        apply_failure=apply_failure,
        recover_interrupted=recover,
        classify_loop_error=classify,
    )
