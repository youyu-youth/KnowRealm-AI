"""文档解析执行体描述（任务循环骨架见 job_runner.py，ADR-0012）。"""

import asyncio
import errno
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast

from loguru import logger
from sqlalchemy import or_, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.models.document import ProcessingJob, RecordFile
from app.models.record import Record
from app.schemas.document import (
    ProcessingJobErrorCode,
    ProcessingJobStatus,
    ProcessingJobType,
)
from app.schemas.record import RecordStatus
from app.services.document_parser import DocumentParseError, extract_document_text
from app.services.job_runner import (
    ClaimCheck,
    ClaimedJob,
    LoopFailure,
    Ready,
    RunnerContext,
    WorkerSpec,
    mark_failed,
    mark_retry_backoff,
)
from app.services.processing_job_lifecycle import cancel_nonterminal_jobs
from app.services.processing_job_policy import RETRYABLE_PROCESSING_JOB_ERROR_CODES
from app.services.record_invalidation import RecordInvalidationNotifier
from app.services.transcript_finalizer import complete_source_job, finalize_record_if_ready

ERROR_MESSAGES = {
    ProcessingJobErrorCode.NON_UTF8_TEXT: "文本文件不是 UTF-8 编码",
    ProcessingJobErrorCode.CORRUPT_DOCUMENT: "文档已损坏，无法读取",
    ProcessingJobErrorCode.PASSWORD_PROTECTED: "文档受密码保护，无法读取",
    ProcessingJobErrorCode.FORMAT_MISMATCH: "文件内容与扩展名不匹配",
    ProcessingJobErrorCode.NO_EXTRACTABLE_TEXT: "文档没有可提取的文本",
    ProcessingJobErrorCode.TEMPORARY_IO: "文档暂时无法读取",
    ProcessingJobErrorCode.SQLITE_BUSY: "本地数据库暂时繁忙",
    ProcessingJobErrorCode.WORKER_INTERRUPTED: "文档处理被意外中断",
    ProcessingJobErrorCode.INTERNAL_ERROR: "文档处理失败",
}


@dataclass(frozen=True)
class ClaimedDocument(ClaimedJob):
    path: Path


def _is_sqlite_busy(error: OperationalError) -> bool:
    message = str(error.orig).lower()
    return "database is locked" in message or "database is busy" in message


def _is_temporary_io_error(error: OSError) -> bool:
    return error.errno in {errno.EAGAIN, errno.EBUSY, errno.EINTR, errno.ETIMEDOUT} or getattr(
        error, "winerror", None
    ) in {32, 33}


async def find_candidate(session: AsyncSession, now: datetime) -> ProcessingJob | None:
    return (
        await session.scalars(
            select(ProcessingJob)
            .join(Record, ProcessingJob.record_id == Record.id)
            .where(
                ProcessingJob.job_type == ProcessingJobType.DOCUMENT_PARSE,
                ProcessingJob.status == ProcessingJobStatus.PENDING,
                Record.deleted_at.is_(None),
                Record.status == RecordStatus.CONTENT_PROCESSING,
                or_(
                    ProcessingJob.next_run_at.is_(None),
                    ProcessingJob.next_run_at <= now,
                ),
            )
            .order_by(ProcessingJob.created_at)
            .limit(1)
        )
    ).one_or_none()


async def validate_claim(
    session: AsyncSession,
    job: ProcessingJob,
    record_id: str,
    data_dir: Path,
) -> ClaimCheck[ClaimedDocument]:
    """抢占前装载解析路径；输入异常仍抢占（Path() 空路径 → 解析失败，现状保真）。"""
    path = Path()
    input_data: object = json.loads(job.input_json)
    if isinstance(input_data, dict):
        record_file_id = cast(dict[str, object], input_data).get("record_file_id")
        if isinstance(record_file_id, str):
            record_file = (
                await session.scalars(
                    select(RecordFile).where(
                        RecordFile.id == record_file_id,
                        RecordFile.record_id == record_id,
                        RecordFile.deleted_at.is_(None),
                    )
                )
            ).one_or_none()
            if record_file is not None:
                candidate = (data_dir / record_file.file_path).resolve()
                files_root = (data_dir / "files").resolve()
                if candidate.is_relative_to(files_root):
                    path = candidate
    return Ready(ClaimedDocument(job_id=job.id, record_id=record_id, path=path))


async def execute(
    ctx: ClaimedDocument,
    _runtime: RunnerContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> str | None:
    """领取后二次确认仍 RUNNING 且记录未删，才执行解析（删除竞态防线）。"""
    async with session_factory() as session:
        active_job = (
            await session.execute(
                select(ProcessingJob.id)
                .join(Record, ProcessingJob.record_id == Record.id)
                .where(
                    ProcessingJob.id == ctx.job_id,
                    ProcessingJob.status == ProcessingJobStatus.RUNNING,
                    Record.id == ctx.record_id,
                    Record.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
    if active_job is None:
        return None
    return await asyncio.to_thread(extract_document_text, ctx.path)


async def writeback(
    ctx: ClaimedDocument,
    content: str,
    session_factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
) -> bool:
    cache_dir = (data_dir / "cache" / "sources" / ctx.record_id).resolve()
    cache_root = (data_dir / "cache").resolve()
    if not cache_dir.is_relative_to(cache_root):
        return False
    cache_dir.mkdir(parents=True, exist_ok=True)
    source_path = cache_dir / f"{ctx.job_id}.txt"
    await asyncio.to_thread(source_path.write_text, content, encoding="utf-8")
    accepted = await complete_source_job(
        session_factory,
        data_dir,
        ctx.record_id,
        ctx.job_id,
        json.dumps({"source_text_path": source_path.relative_to(data_dir).as_posix()}),
    )
    if not accepted:
        await asyncio.to_thread(shutil.rmtree, cache_dir, ignore_errors=True)
    return True


def failure_code(ctx: ClaimedDocument, exc: Exception) -> str | None:
    if isinstance(exc, DocumentParseError):
        return exc.code
    if isinstance(exc, OSError):
        code = (
            ProcessingJobErrorCode.TEMPORARY_IO
            if _is_temporary_io_error(exc)
            else ProcessingJobErrorCode.INTERNAL_ERROR
        )
        logger.error("document_parse_failed", error_code=code)
        return code
    logger.error("document_parse_failed", error_code=ProcessingJobErrorCode.INTERNAL_ERROR)
    return ProcessingJobErrorCode.INTERNAL_ERROR


async def apply_failure(
    ctx: ClaimedDocument,
    session: AsyncSession,
    job: ProcessingJob,
    record: Record | None,
    error_code: str,
    now: datetime,
) -> bool:
    del ctx, session
    # 旧行为：记录已软删则静默不动 job（select 恒带 deleted_at IS NULL 过滤）
    if record is None or record.deleted_at is not None:
        return False
    code = ProcessingJobErrorCode(error_code)
    if code in RETRYABLE_PROCESSING_JOB_ERROR_CODES and job.attempts < job.max_attempts:
        # 退避公式与 recover 不一致——原样保真，见 job_runner.mark_retry_backoff
        mark_retry_backoff(job, code=code.value, message=ERROR_MESSAGES[code], now=now)
    else:
        mark_failed(job, code=code.value, message=ERROR_MESSAGES[code], now=now)
        record.status = RecordStatus.FAILED
        record.updated_at = now
    return True


async def recover_running(
    session_factory: async_sessionmaker[AsyncSession],
    record_notifier: RecordInvalidationNotifier,
    code: ProcessingJobErrorCode,
) -> None:
    now = utcnow()
    record_ids: set[str] = set()
    async with session_factory() as session, session.begin():
        jobs = (
            await session.scalars(
                select(ProcessingJob)
                .join(Record, ProcessingJob.record_id == Record.id)
                .where(
                    ProcessingJob.job_type == ProcessingJobType.DOCUMENT_PARSE,
                    ProcessingJob.status == ProcessingJobStatus.RUNNING,
                    Record.deleted_at.is_(None),
                )
            )
        ).all()
        for job in jobs:
            if job.record_id is not None:
                record_ids.add(job.record_id)
            if job.attempts < job.max_attempts:
                job.status = ProcessingJobStatus.PENDING
                # ponytail: 此处退避用 2**attempts，fail 路径用 2**(attempts-1)——
                # 现状不一致，行为冻结原样保真，修复须另立工单（job-runner issue 01）。
                job.next_run_at = now + timedelta(seconds=2 ** max(job.attempts, 0))
            else:
                job.status = ProcessingJobStatus.FAILED
                job.finished_at = now
                if job.record_id is not None:
                    record = await session.get(Record, job.record_id)
                    if record is not None:
                        record.status = RecordStatus.FAILED
                        record.updated_at = now
            job.error_code = code.value
            job.error_message = ERROR_MESSAGES[code]
            job.updated_at = now
        await session.flush()
    for record_id in record_ids:
        await record_notifier.notify(record_id)


def classify_loop_error(exc: Exception) -> LoopFailure:
    if isinstance(exc, OperationalError) and _is_sqlite_busy(exc):
        return LoopFailure(
            event="document_worker_retryable_failure",
            level="warning",
            error_code=ProcessingJobErrorCode.SQLITE_BUSY,
            pause=False,
        )
    return LoopFailure(
        event="document_worker_unexpected_failure",
        error_code=ProcessingJobErrorCode.INTERNAL_ERROR,
        pause=False,
    )


def document_spec(
    session_factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
    record_notifier: RecordInvalidationNotifier,
) -> WorkerSpec[None, ClaimedDocument, str]:
    async def recover() -> None:
        async with session_factory() as session, session.begin():
            await cancel_nonterminal_jobs(
                session,
                record_filter=ProcessingJob.record_id.in_(
                    select(Record.id).where(Record.deleted_at.is_not(None))
                ),
                now=utcnow(),
            )
        await recover_running(
            session_factory, record_notifier, ProcessingJobErrorCode.WORKER_INTERRUPTED
        )
        async with session_factory() as session:
            record_ids = list(
                (
                    await session.scalars(
                        select(ProcessingJob.record_id)
                        .where(
                            ProcessingJob.job_type == ProcessingJobType.DOCUMENT_PARSE,
                            ProcessingJob.status == ProcessingJobStatus.SUCCEEDED,
                            ProcessingJob.record_id.is_not(None),
                        )
                        .distinct()
                    )
                ).all()
            )
        for record_id in record_ids:
            if record_id is not None:
                await finalize_record_if_ready(session_factory, data_dir, record_id)

    return WorkerSpec(
        name="document_worker",
        job_type=ProcessingJobType.DOCUMENT_PARSE,
        poll_interval=1,
        find_candidate=find_candidate,
        validate_claim=lambda session, job, record_id, _payload: validate_claim(
            session, job, record_id, data_dir
        ),
        execute=lambda ctx, runtime: execute(ctx, runtime, session_factory),
        writeback=lambda ctx, content: writeback(ctx, content, session_factory, data_dir),
        failure_code=failure_code,
        apply_failure=apply_failure,
        recover_interrupted=recover,
        classify_loop_error=classify_loop_error,
        on_loop_failure=lambda code: recover_running(
            session_factory, record_notifier, ProcessingJobErrorCode(code)
        ),
        clock=utcnow,  # 工厂调用时解析本模块 utcnow，测试冻结时钟经此生效
    )
