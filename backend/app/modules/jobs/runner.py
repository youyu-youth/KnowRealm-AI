"""任务循环骨架唯一归属（ADR-0012）。

七个 worker（audio / summary / quiz / quiz_grading / knowledge_point / todo / document）的执行体
以 ``WorkerSpec``（声明式钩子描述）注入 ``JobRunner``；轮询、条件抢占、恢复、
失败记账、停止与协议点通知（recover / 领取成功后 / 写回尾 / 失败尾）全部归本
模块，执行体不得自带横切副本。领取协议三态与 CANCELLED 静默为显式契约。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Protocol, TypeVar, cast

from loguru import logger
from sqlalchemy import CursorResult, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.schemas import ProcessingJobStatus, ProcessingJobType
from app.modules.record.events import RecordInvalidationNotifier
from app.modules.record.models import Record

PreflightT = TypeVar("PreflightT")
ResultT = TypeVar("ResultT")


@dataclass(frozen=True)
class ClaimedJob:
    """执行体上下文基类：runner 只依赖 job_id / record_id 两个坐标。"""

    job_id: str
    record_id: str


@dataclass(frozen=True)
class Ready[CtxT: ClaimedJob]:
    """领取校验通过；ctx 由校验阶段装载的实体构建。"""

    ctx: CtxT


@dataclass(frozen=True)
class CancelClaim:
    """前置失效：写 CANCELLED + result_json={"reason"}，提交后静默（不 notify）。"""

    reason: str


@dataclass(frozen=True)
class WaitingClaim:
    """不抢占、不消耗 attempts，仅标注 waiting_reason；reason 真变化才 notify。"""

    reason: str


type ClaimCheck[CtxT: ClaimedJob] = Ready[CtxT] | CancelClaim | WaitingClaim


@dataclass(frozen=True)
class LoopFailure:
    """run 主循环一次异常的分类结局：记什么日志、恢复后是否停拍。"""

    event: str
    level: Literal["error", "warning"] = "error"
    error_code: str = "INTERNAL_ERROR"
    pause: bool = True


def mark_failed(
    job: ProcessingJob,
    *,
    code: str,
    message: str,
    now: datetime,
    clear_next_run: bool = False,
) -> None:
    """共享失败结局一：终态（LLM 四域，无自动重试）。"""
    job.status = ProcessingJobStatus.FAILED
    job.error_code = code
    job.error_message = message
    if clear_next_run:
        job.next_run_at = None
    job.finished_at = now
    job.updated_at = now


def mark_retry_fixed(
    job: ProcessingJob,
    *,
    code: str,
    message: str,
    now: datetime,
    seconds: float = 1,
) -> None:
    """共享失败结局二：固定间隔重试（audio ASR 临时不可用）。"""
    job.status = ProcessingJobStatus.PENDING
    job.error_code = code
    job.error_message = message
    job.next_run_at = now + timedelta(seconds=seconds)
    job.finished_at = None
    job.updated_at = now


def mark_retry_backoff(
    job: ProcessingJob,
    *,
    code: str,
    message: str,
    now: datetime,
) -> None:
    """共享失败结局三：指数退避重试（document）。

    ponytail: fail 路径用 2**(attempts-1)，document 的 recover 用 2**attempts——
    两处现状不一致，行为冻结原样保真，修复须另立工单（job-runner issue 01）。
    """
    job.status = ProcessingJobStatus.PENDING
    job.error_code = code
    job.error_message = message
    job.next_run_at = now + timedelta(seconds=2 ** (job.attempts - 1))
    job.updated_at = now


async def recover_running_to_failed(
    session_factory: async_sessionmaker[AsyncSession],
    notifier: RecordInvalidationNotifier,
    job_type: ProcessingJobType,
    error_message: str,
    *,
    on_job_recovered: Callable[[AsyncSession, ProcessingJob, datetime], Awaitable[None]]
    | None = None,
) -> None:
    """默认恢复：RUNNING → FAILED(WORKER_INTERRUPTED)，提交后逐 record notify。"""
    now = utcnow()
    record_ids: list[str] = []
    async with session_factory() as session, session.begin():
        jobs = list(
            (
                await session.scalars(
                    select(ProcessingJob).where(
                        ProcessingJob.job_type == job_type,
                        ProcessingJob.status == ProcessingJobStatus.RUNNING,
                    )
                )
            ).all()
        )
        for job in jobs:
            job.status = ProcessingJobStatus.FAILED
            job.error_code = "WORKER_INTERRUPTED"
            job.error_message = error_message
            job.finished_at = now
            job.updated_at = now
            if job.record_id is not None:
                record_ids.append(job.record_id)
            if on_job_recovered is not None:
                await on_job_recovered(session, job, now)
    for record_id in record_ids:
        await notifier.notify(record_id)


@dataclass(frozen=True)
class WorkerSpec[PreflightT, CtxT: ClaimedJob, ResultT]:
    """声明式执行体描述：只有领域差异，无横切副本。"""

    name: str
    job_type: ProcessingJobType
    poll_interval: float
    find_candidate: Callable[[AsyncSession, datetime], Awaitable[ProcessingJob | None]]
    validate_claim: Callable[
        [AsyncSession, ProcessingJob, str, PreflightT | None], Awaitable[ClaimCheck[CtxT]]
    ]
    execute: Callable[[CtxT, RunnerContext], Awaitable[ResultT | None]]
    writeback: Callable[[CtxT, ResultT], Awaitable[bool]]
    failure_code: Callable[[CtxT, Exception], str | None]
    apply_failure: Callable[
        [CtxT, AsyncSession, ProcessingJob, Record | None, str, datetime], Awaitable[bool]
    ]
    recover_interrupted: Callable[[], Awaitable[None]]
    classify_loop_error: Callable[[Exception], LoopFailure]
    preflight: Callable[[], Awaitable[PreflightT | None]] | None = None
    on_preempted: (
        Callable[[AsyncSession, ProcessingJob, CtxT, datetime], Awaitable[CtxT]] | None
    ) = None
    on_loop_failure: Callable[[str], Awaitable[None]] | None = None
    finalize_cycle: Callable[[CtxT], Awaitable[None]] | None = None
    clear_waiting_on_claim: bool = False
    clock: Callable[[], datetime] = utcnow  # runner 外壳时钟接缝：领取/失败记账用，测试可冻结推进


class ManagedWorker(Protocol):
    """main.py 注册表项：lifespan 可启动 / 停止 / 恢复的循环体。"""

    def stop(self) -> None: ...

    async def run(self) -> None: ...

    async def recover_interrupted(self) -> None: ...


@dataclass(frozen=True)
class RunnerContext:
    """执行体运行上下文：中途事件 notifier 与停止旗标（audio 域中途事件用）。"""

    record_notifier: RecordInvalidationNotifier
    stopped: asyncio.Event


class JobRunner[PreflightT, CtxT: ClaimedJob, ResultT]:
    """一个 worker 一个 runner 实例、一个 asyncio 任务；禁止合并单循环。"""

    def __init__(
        self,
        spec: WorkerSpec[PreflightT, CtxT, ResultT],
        session_factory: async_sessionmaker[AsyncSession],
        record_notifier: RecordInvalidationNotifier,
    ) -> None:
        self._spec = spec
        self._session_factory = session_factory
        self._notifier = record_notifier
        self._stopped = asyncio.Event()
        self._runtime = RunnerContext(record_notifier, self._stopped)

    def stop(self) -> None:
        self._stopped.set()

    async def recover_interrupted(self) -> None:
        await self._spec.recover_interrupted()

    async def run(self) -> None:
        while not self._stopped.is_set():
            pause = self._spec.poll_interval
            try:
                if await self.process_one():
                    continue
            except Exception as exc:
                pause = await self._handle_loop_error(exc)
                if pause is None:
                    continue
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=pause)
            except TimeoutError:
                pass

    async def process_one(self) -> bool:
        """完整处理一个已领取任务；返回是否处理到任务（True 则立即续跑）。"""
        ctx = await self.claim_one()
        if ctx is None:
            return False
        await self._notifier.notify(ctx.record_id)  # 协议点：领取成功后
        landed = False
        try:
            result = await self._spec.execute(ctx, self._runtime)
        except Exception as exc:
            code = self._spec.failure_code(ctx, exc)
            if code is None:
                raise
            landed = await self._apply_failure(ctx, code)
        else:
            # 写回异常不属执行失败：按现状契约直抛 run 循环走恢复路径
            if result is not None:
                landed = await self._spec.writeback(ctx, result)
        finally:
            if self._spec.finalize_cycle is not None:
                await self._spec.finalize_cycle(ctx)
        if landed:
            await self._notifier.notify(ctx.record_id)  # 协议点：写回尾 / 失败尾
        return True

    async def claim_one(self) -> CtxT | None:
        """领取事务外壳：查候选 → 校验（三态）→ 条件抢占 → 构建上下文。"""
        payload: PreflightT | None = None
        if self._spec.preflight is not None:
            payload = await self._spec.preflight()
            if payload is None:
                return None
        now = self._spec.clock()
        ctx: CtxT | None = None
        waiting_record: str | None = None
        async with self._session_factory() as session, session.begin():
            job = await self._spec.find_candidate(session, now)
            if job is not None:
                # 课程级任务（QUIZ_GRADING）无 record 主体：record 坐标传空串，
                # 执行体从 input_json 取自己的坐标；record 域候选恒有 record_id。
                decision = await self._spec.validate_claim(
                    session,
                    job,
                    job.record_id if job.record_id is not None else "",
                    payload,
                )
                if isinstance(decision, CancelClaim):
                    # 现状契约：前置失效取消，事务提交后静默（不 notify）
                    job.status = ProcessingJobStatus.CANCELLED
                    job.result_json = json.dumps({"reason": decision.reason})
                    job.finished_at = now
                    job.updated_at = now
                elif isinstance(decision, WaitingClaim):
                    if await _mark_waiting(session, job.id, decision.reason, now):
                        waiting_record = job.record_id
                elif await _preempt(session, job.id, now, self._spec.clear_waiting_on_claim):
                    claimed_ctx = decision.ctx
                    if self._spec.on_preempted is not None:
                        claimed_ctx = await self._spec.on_preempted(session, job, claimed_ctx, now)
                    ctx = claimed_ctx
        if waiting_record is not None:
            await self._notifier.notify(waiting_record)  # 协议点：waiting reason 真变化
        return ctx

    async def _apply_failure(self, ctx: CtxT, code: str) -> bool:
        """失败记账事务外壳；job 已被他方终结时静默（返回 False 不 notify）。"""
        now = self._spec.clock()
        async with self._session_factory() as session, session.begin():
            job = await session.get(ProcessingJob, ctx.job_id)
            if job is None or job.status != ProcessingJobStatus.RUNNING:
                return False
            record = await session.get(Record, ctx.record_id)
            return await self._spec.apply_failure(ctx, session, job, record, code, now)

    async def _handle_loop_error(self, exc: Exception) -> float | None:
        failure = self._spec.classify_loop_error(exc)
        if failure.level == "warning":
            logger.warning(failure.event, error_code=failure.error_code)
        else:
            logger.error(failure.event, error_code=failure.error_code)
        if self._spec.on_loop_failure is not None:
            await self._spec.on_loop_failure(failure.error_code)
        else:
            await self.recover_interrupted()
        return self._spec.poll_interval if failure.pause else None


async def _preempt(session: AsyncSession, job_id: str, now: datetime, clear_waiting: bool) -> bool:
    """抢占原语：条件 UPDATE PENDING→RUNNING、attempts+1；rowcount==1 才算抢到。"""
    values: dict[str, object] = {
        "status": ProcessingJobStatus.RUNNING,
        "attempts": ProcessingJob.attempts + 1,
        "started_at": now,
        "updated_at": now,
    }
    if clear_waiting:
        values["waiting_reason"] = None
    result = cast(
        "CursorResult[tuple[()]]",
        await session.execute(
            update(ProcessingJob)
            .where(
                ProcessingJob.id == job_id,
                ProcessingJob.status == ProcessingJobStatus.PENDING,
            )
            .values(**values)
        ),
    )
    return result.rowcount == 1


async def _mark_waiting(session: AsyncSession, job_id: str, reason: str, now: datetime) -> bool:
    """waiting 槽（audio 专用）：幂等标注 waiting_reason，reason 真变化才返回 True。"""
    result = cast(
        "CursorResult[tuple[()]]",
        await session.execute(
            update(ProcessingJob)
            .where(
                ProcessingJob.id == job_id,
                ProcessingJob.status == ProcessingJobStatus.PENDING,
                or_(
                    ProcessingJob.waiting_reason.is_(None),
                    ProcessingJob.waiting_reason != reason,
                ),
            )
            .values(waiting_reason=reason, updated_at=now)
        ),
    )
    return result.rowcount == 1
