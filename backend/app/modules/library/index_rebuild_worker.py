"""INDEX_REBUILD 执行体（工单 05）：单条目索引幂等重建。

索引是可再生衍生数据：重建 = 对条目关联 Record 逐一先删后插
search_index（导航）与 segment_search_index（RAG 片段），同事务幂等，
软删期间意外丢失的行恢复即补齐。执行在 execute 内自持短事务完成全部
写入（无外部副作用），writeback 仅落 Job 终态。
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
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
from app.modules.jobs.schemas import ProcessingJobStatus, ProcessingJobType
from app.modules.library.models import LibraryItem, LibraryItemRecord
from app.modules.record.models import Record
from app.modules.search.segment_service import SegmentSearchService
from app.modules.search.service import SearchService
from app.shared.events import RecordInvalidationNotifier

INDEX_REBUILD_JOB_TYPE = ProcessingJobType.INDEX_REBUILD


@dataclass(frozen=True)
class _ClaimedRebuild(ClaimedJob):
    """条目级任务：无 record 主体（record_id 坐标位承载 library_item_id 的
    派生记录数，notifier 协议点用空串——与课程级任务同先例）。"""

    library_item_id: str


async def find_candidate(session: AsyncSession, now: datetime) -> ProcessingJob | None:
    return (
        await session.scalars(
            select(ProcessingJob)
            .where(
                ProcessingJob.job_type == INDEX_REBUILD_JOB_TYPE,
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
) -> ClaimCheck[_ClaimedRebuild]:
    """领取闸门：条目已物理删除（CASCADE 会带走任务，此处防御性兜底）即取消。"""
    input_data: object = json.loads(job.input_json)
    library_item_id = ""
    if isinstance(input_data, dict):
        raw = cast(dict[str, object], input_data).get("library_item_id")
        if isinstance(raw, str):
            library_item_id = raw
    item = await session.get(LibraryItem, library_item_id) if library_item_id else None
    if item is None:
        return CancelClaim("library_item_deleted")
    return Ready(
        _ClaimedRebuild(
            job_id=job.id,
            record_id="",
            library_item_id=library_item_id,
        )
    )


async def rebuild_item_indexes(
    session_factory: async_sessionmaker[AsyncSession], library_item_id: str
) -> int:
    """对条目关联的未软删 Record 重建两类索引；返回处理的 Record 数。"""
    async with session_factory() as session, session.begin():
        record_ids = list(
            (
                await session.scalars(
                    select(LibraryItemRecord.record_id)
                    .join(Record, Record.id == LibraryItemRecord.record_id)
                    .where(
                        LibraryItemRecord.library_item_id == library_item_id,
                        Record.deleted_at.is_(None),
                    )
                )
            ).all()
        )
        for record_id in record_ids:
            await SearchService.upsert_record_index(session, record_id)
            await SegmentSearchService.upsert_record_segments(session, record_id)
    return len(record_ids)


async def execute(
    ctx: _ClaimedRebuild,
    _runtime: RunnerContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> int:
    return await rebuild_item_indexes(session_factory, ctx.library_item_id)


async def writeback(
    ctx: _ClaimedRebuild,
    rebuilt_records: int,
    session_factory: async_sessionmaker[AsyncSession],
) -> bool:
    async with session_factory() as session, session.begin():
        job = await session.get(ProcessingJob, ctx.job_id)
        if job is None or job.status != ProcessingJobStatus.RUNNING:
            return False
        now = utcnow()
        job.status = ProcessingJobStatus.SUCCEEDED
        job.progress = 1
        job.next_run_at = None
        job.result_json = json.dumps({"rebuilt_records": rebuilt_records})
        job.error_code = None
        job.error_message = None
        job.finished_at = now
        job.updated_at = now
    logger.info("library_index_rebuilt", item_id=ctx.library_item_id, records=rebuilt_records)
    return True


def failure_code(_ctx: _ClaimedRebuild, _exc: Exception) -> str | None:
    return "LIBRARY_INDEX_REBUILD_FAILED"


async def apply_failure(
    _ctx: _ClaimedRebuild,
    _session: AsyncSession,
    job: ProcessingJob,
    _record: Record | None,
    error_code: str,
    now: datetime,
) -> bool:
    mark_failed(job, code=error_code, message="资料索引重建失败", now=now)
    return True


def index_rebuild_spec(
    session_factory: async_sessionmaker[AsyncSession],
    record_notifier: RecordInvalidationNotifier,
) -> WorkerSpec[None, _ClaimedRebuild, int]:
    def classify(_exc: Exception) -> LoopFailure:
        return LoopFailure(event="library_index_rebuild_unexpected_failure")

    async def recover() -> None:
        await recover_running_to_failed(
            session_factory,
            record_notifier,
            INDEX_REBUILD_JOB_TYPE,
            "资料索引重建被意外中断",
        )

    return WorkerSpec(
        name="library_index_rebuild_worker",
        job_type=INDEX_REBUILD_JOB_TYPE,
        poll_interval=2.0,
        find_candidate=find_candidate,
        validate_claim=validate_claim,
        execute=lambda ctx, runtime: execute(ctx, runtime, session_factory),
        writeback=lambda ctx, result: writeback(ctx, result, session_factory),
        failure_code=failure_code,
        apply_failure=apply_failure,
        recover_interrupted=recover,
        classify_loop_error=classify,
    )
