"""JobRunner 领取三态与协议点通知的单元覆盖（issue job-runner/01 验收项）。"""

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import create_database
from app.db.migrations import run_migrations
from app.models.document import ProcessingJob
from app.models.record import Record
from app.schemas.document import ProcessingJobStatus, ProcessingJobType
from app.services.job_runner import (
    CancelClaim,
    ClaimCheck,
    ClaimedJob,
    JobRunner,
    LoopFailure,
    Ready,
    RunnerContext,
    WaitingClaim,
    WorkerSpec,
    mark_failed,
)
from app.services.record_invalidation import RecordInvalidationNotifier

RECORD_ID = "aaaa1111-1111-4111-8111-111111111111"
JOB_ID = "bbbb2222-2222-4222-8222-222222222222"
NOW = "2026-08-29T00:00:00.000000Z"


@dataclass(frozen=True)
class _ProbeClaim(ClaimedJob):
    pass


@asynccontextmanager
async def runner_env(
    tmp_path: Path,
    decision: str,
    *,
    execute_raises: bool = False,
) -> AsyncGenerator[
    tuple[
        JobRunner[None, _ProbeClaim, str],
        async_sessionmaker[AsyncSession],
        RecordInvalidationNotifier,
    ],
    None,
]:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    engine, session_factory = create_database(db_path)
    try:
        async with session_factory() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO records (id, capture_type, title, status, duration_ms, "
                    "created_at, updated_at, deleted_at) "
                    "VALUES (:id, 'QUICK_NOTE', '探针', 'CONTENT_PROCESSING', 0, "
                    ":now, :now, NULL)"
                ),
                {"id": RECORD_ID, "now": NOW},
            )
            await session.execute(
                text(
                    "INSERT INTO processing_jobs (id, record_id, job_type, status, progress, "
                    "input_json, attempts, max_attempts, created_at, updated_at) VALUES "
                    "(:id, :record_id, 'ASR', 'PENDING', 0, '{}', 0, 3, :now, :now)"
                ),
                {"id": JOB_ID, "record_id": RECORD_ID, "now": NOW},
            )
        notifier = RecordInvalidationNotifier()

        async def find_candidate(session: AsyncSession, now: datetime) -> ProcessingJob | None:
            del now
            return (
                await session.scalars(select(ProcessingJob).where(ProcessingJob.id == JOB_ID))
            ).one_or_none()

        async def validate_claim(
            session: AsyncSession,
            job: ProcessingJob,
            record_id: str,
            payload: None,
        ) -> ClaimCheck[_ProbeClaim]:
            del session, job, payload
            if decision == "cancel":
                return CancelClaim("PREREQUISITE_CHANGED")
            if decision == "waiting":
                return WaitingClaim("CONSENT_REQUIRED")
            return Ready(_ProbeClaim(job_id=JOB_ID, record_id=record_id))

        async def execute(ctx: _ProbeClaim, runtime: RunnerContext) -> str | None:
            del ctx, runtime
            if execute_raises:
                raise RuntimeError("probe explode")
            return "done"

        async def writeback(ctx: _ProbeClaim, result: str) -> bool:
            del ctx, result
            return True

        async def apply_failure(
            ctx: _ProbeClaim,
            session: AsyncSession,
            job: ProcessingJob,
            record: Record | None,
            error_code: str,
            now: datetime,
        ) -> bool:
            del ctx, session, record
            mark_failed(job, code=error_code, message="probe", now=now)
            return True

        async def recover() -> None:
            return None

        spec = WorkerSpec[None, _ProbeClaim, str](
            name="probe_worker",
            job_type=ProcessingJobType.ASR,
            interrupted_error_message="探针被意外中断",
            poll_interval=0.01,
            find_candidate=find_candidate,
            validate_claim=validate_claim,
            execute=execute,
            writeback=writeback,
            failure_code=lambda ctx, exc: "PROBE_FAILED" if isinstance(exc, RuntimeError) else None,
            apply_failure=apply_failure,
            recover_interrupted=recover,
            classify_loop_error=lambda _exc: LoopFailure(event="probe_failure"),
        )
        yield JobRunner(spec, session_factory, notifier), session_factory, notifier
    finally:
        await engine.dispose()


async def _job_row(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, object]:
    async with session_factory() as session:
        job = (await session.scalars(select(ProcessingJob).where(ProcessingJob.id == JOB_ID))).one()
    return {
        "status": job.status,
        "attempts": job.attempts,
        "waiting_reason": job.waiting_reason,
        "result_json": job.result_json,
    }


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_claim_preempts_with_attempts_and_process_notifies_twice(tmp_path: Path) -> None:
    async with runner_env(tmp_path, "ready") as (runner, session_factory, notifier):
        version_before = notifier.version(RECORD_ID)
        claimed = await runner.claim_one()
        assert claimed == _ProbeClaim(job_id=JOB_ID, record_id=RECORD_ID)
        row = await _job_row(session_factory)
        assert row["status"] == ProcessingJobStatus.RUNNING
        assert row["attempts"] == 1
        # 领取原语本身不 notify：协议点在 process_one 领取成功后
        assert notifier.version(RECORD_ID) == version_before


@pytest.mark.anyio
async def test_process_one_notifies_after_claim_and_writeback(tmp_path: Path) -> None:
    async with runner_env(tmp_path, "ready") as (runner, session_factory, notifier):
        version_before = notifier.version(RECORD_ID)
        assert await runner.process_one() is True
        # 领取成功后 + 写回尾共两次 notify；探针写回不改状态
        assert notifier.version(RECORD_ID) == version_before + 2
        row = await _job_row(session_factory)
        assert row["attempts"] == 1


@pytest.mark.anyio
async def test_cancelled_claim_is_silent_and_committed(tmp_path: Path) -> None:
    async with runner_env(tmp_path, "cancel") as (runner, session_factory, notifier):
        version_before = notifier.version(RECORD_ID)
        assert await runner.claim_one() is None
        row = await _job_row(session_factory)
        assert row["status"] == ProcessingJobStatus.CANCELLED
        assert json.loads(cast(str, row["result_json"])) == {"reason": "PREREQUISITE_CHANGED"}
        assert row["attempts"] == 0  # 不抢占不消耗 attempts
        assert notifier.version(RECORD_ID) == version_before  # CANCELLED 静默


@pytest.mark.anyio
async def test_waiting_claim_marks_reason_without_consuming_attempts(tmp_path: Path) -> None:
    async with runner_env(tmp_path, "waiting") as (runner, session_factory, notifier):
        version_before = notifier.version(RECORD_ID)
        assert await runner.claim_one() is None
        row = await _job_row(session_factory)
        assert row["status"] == ProcessingJobStatus.PENDING
        assert row["waiting_reason"] == "CONSENT_REQUIRED"
        assert row["attempts"] == 0
        assert notifier.version(RECORD_ID) == version_before + 1  # reason 真变化才 notify

        assert await runner.claim_one() is None  # 幂等：同 reason 不重复 notify
        assert notifier.version(RECORD_ID) == version_before + 1


@pytest.mark.anyio
async def test_failure_tail_notifies_after_terminal_write(tmp_path: Path) -> None:
    async with runner_env(tmp_path, "ready", execute_raises=True) as (
        runner,
        session_factory,
        notifier,
    ):
        version_before = notifier.version(RECORD_ID)
        assert await runner.process_one() is True
        row = await _job_row(session_factory)
        assert row["status"] == ProcessingJobStatus.FAILED
        assert notifier.version(RECORD_ID) == version_before + 2  # 领取成功后 + 失败尾


@pytest.mark.anyio
async def test_run_loop_stops_cleanly(tmp_path: Path) -> None:
    async with runner_env(tmp_path, "ready") as (runner, _sf, _notifier):
        task = asyncio.create_task(runner.run())
        await asyncio.sleep(0.05)
        runner.stop()
        await asyncio.wait_for(task, timeout=1)
