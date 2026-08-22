import asyncio
import errno
import json
from datetime import timedelta
from pathlib import Path
from typing import cast

from loguru import logger
from sqlalchemy import or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.base import utcnow
from app.models.document import ProcessingJob, RecordFile, Transcript
from app.models.record import Record
from app.schemas.document import (
    ProcessingJobErrorCode,
    ProcessingJobStatus,
    ProcessingJobType,
)
from app.schemas.record import RecordStatus
from app.services.document_parser import DocumentParseError, extract_document_text
from app.services.processing_job_lifecycle import cancel_nonterminal_jobs
from app.services.processing_job_policy import RETRYABLE_PROCESSING_JOB_ERROR_CODES
from app.services.record_invalidation import RecordInvalidationNotifier

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


def _is_sqlite_busy(error: OperationalError) -> bool:
    message = str(error.orig).lower()
    return "database is locked" in message or "database is busy" in message


def _is_temporary_io_error(error: OSError) -> bool:
    return error.errno in {errno.EAGAIN, errno.EBUSY, errno.EINTR, errno.ETIMEDOUT} or getattr(
        error, "winerror", None
    ) in {32, 33}


class DocumentWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
        record_notifier: RecordInvalidationNotifier,
    ) -> None:
        self._session_factory = session_factory
        self._data_dir = data_dir
        self._record_notifier = record_notifier
        self._stopped = asyncio.Event()

    def stop(self) -> None:
        self._stopped.set()

    async def recover_interrupted(self) -> None:
        async with self._session_factory() as session, session.begin():
            await cancel_nonterminal_jobs(
                session,
                record_filter=ProcessingJob.record_id.in_(
                    select(Record.id).where(Record.deleted_at.is_not(None))
                ),
                now=utcnow(),
            )
        await self._recover_running(ProcessingJobErrorCode.WORKER_INTERRUPTED)

    async def _recover_running(self, code: ProcessingJobErrorCode) -> None:
        now = utcnow()
        record_ids: set[str] = set()
        async with self._session_factory() as session, session.begin():
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
            await self._record_notifier.notify(record_id)

    async def run(self) -> None:
        while not self._stopped.is_set():
            try:
                if await self._process_one():
                    continue
            except OperationalError as exc:
                if not _is_sqlite_busy(exc):
                    raise
                logger.warning(
                    "document_worker_retryable_failure",
                    error_code=ProcessingJobErrorCode.SQLITE_BUSY,
                )
                await self._recover_running(ProcessingJobErrorCode.SQLITE_BUSY)
                continue
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=0.05)
            except TimeoutError:
                pass

    async def _process_one(self) -> bool:
        claimed = await self._claim_one()
        if claimed is None:
            return False
        job_id, record_id, path = claimed
        await self._record_notifier.notify(record_id)
        if not await self._can_continue(job_id, record_id):
            return True
        try:
            content = await asyncio.to_thread(extract_document_text, path)
        except DocumentParseError as exc:
            await self._fail(job_id, record_id, exc.code)
        except OSError as exc:
            code = (
                ProcessingJobErrorCode.TEMPORARY_IO
                if _is_temporary_io_error(exc)
                else ProcessingJobErrorCode.INTERNAL_ERROR
            )
            logger.error("document_parse_failed", error_code=code)
            await self._fail(job_id, record_id, code)
        except Exception:
            logger.error(
                "document_parse_failed",
                error_code=ProcessingJobErrorCode.INTERNAL_ERROR,
            )
            await self._fail(job_id, record_id, ProcessingJobErrorCode.INTERNAL_ERROR)
        else:
            await self._succeed(job_id, record_id, content)
        return True

    async def _can_continue(self, job_id: str, record_id: str) -> bool:
        async with self._session_factory() as session:
            active_job = (
                await session.execute(
                    select(ProcessingJob.id)
                    .join(Record, ProcessingJob.record_id == Record.id)
                    .where(
                        ProcessingJob.id == job_id,
                        ProcessingJob.status == ProcessingJobStatus.RUNNING,
                        Record.id == record_id,
                        Record.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
        return active_job is not None

    async def _claim_one(self) -> tuple[str, str, Path] | None:
        now = utcnow()
        async with self._session_factory() as session, session.begin():
            job = (
                await session.scalars(
                    select(ProcessingJob)
                    .join(Record, ProcessingJob.record_id == Record.id)
                    .where(
                        ProcessingJob.job_type == ProcessingJobType.DOCUMENT_PARSE,
                        ProcessingJob.status == ProcessingJobStatus.PENDING,
                        Record.deleted_at.is_(None),
                        or_(
                            ProcessingJob.next_run_at.is_(None),
                            ProcessingJob.next_run_at <= now,
                        ),
                    )
                    .order_by(ProcessingJob.created_at)
                    .limit(1)
                )
            ).one_or_none()
            if job is None or job.record_id is None:
                return None
            result = cast(
                CursorResult[tuple[()]],
                await session.execute(
                    update(ProcessingJob)
                    .where(
                        ProcessingJob.id == job.id,
                        ProcessingJob.status == ProcessingJobStatus.PENDING,
                    )
                    .values(
                        status=ProcessingJobStatus.RUNNING,
                        attempts=ProcessingJob.attempts + 1,
                        started_at=now,
                        updated_at=now,
                    )
                ),
            )
            if result.rowcount != 1:
                return None
            input_data: object = json.loads(job.input_json)
            if not isinstance(input_data, dict):
                return job.id, job.record_id, Path()
            input_dict = cast(dict[str, object], input_data)
            record_file_id = input_dict.get("record_file_id")
            if not isinstance(record_file_id, str):
                return job.id, job.record_id, Path()
            record_file = (
                await session.scalars(
                    select(RecordFile).where(
                        RecordFile.id == record_file_id,
                        RecordFile.record_id == job.record_id,
                        RecordFile.deleted_at.is_(None),
                    )
                )
            ).one_or_none()
            if record_file is None:
                return job.id, job.record_id, Path()
            path = (self._data_dir / record_file.file_path).resolve()
            files_root = (self._data_dir / "files").resolve()
            if not path.is_relative_to(files_root):
                return job.id, job.record_id, Path()
            return job.id, job.record_id, path

    async def _succeed(self, job_id: str, record_id: str, content: str) -> None:
        now = utcnow()
        async with self._session_factory() as session, session.begin():
            job = await session.get(ProcessingJob, job_id)
            record = (
                await session.scalars(
                    select(Record).where(
                        Record.id == record_id,
                        Record.deleted_at.is_(None),
                    )
                )
            ).one_or_none()
            if job is None or record is None or job.status != ProcessingJobStatus.RUNNING:
                return
            session.add(
                Transcript(
                    record_id=record_id,
                    language="und",
                    content=content,
                    source_version=1,
                    edited_by_user=False,
                    created_at=now,
                    updated_at=now,
                )
            )
            job.status = ProcessingJobStatus.SUCCEEDED
            job.progress = 1
            job.next_run_at = None
            job.error_code = None
            job.error_message = None
            job.finished_at = now
            job.updated_at = now
            record.status = RecordStatus.SUMMARY_PENDING
            record.updated_at = now
            await session.flush()
        await self._record_notifier.notify(record_id)

    async def _fail(
        self,
        job_id: str,
        record_id: str,
        code: ProcessingJobErrorCode,
    ) -> None:
        now = utcnow()
        async with self._session_factory() as session, session.begin():
            job = await session.get(ProcessingJob, job_id)
            record = (
                await session.scalars(
                    select(Record).where(
                        Record.id == record_id,
                        Record.deleted_at.is_(None),
                    )
                )
            ).one_or_none()
            if job is None or record is None or job.status != ProcessingJobStatus.RUNNING:
                return
            if code in RETRYABLE_PROCESSING_JOB_ERROR_CODES and job.attempts < job.max_attempts:
                job.status = ProcessingJobStatus.PENDING
                job.next_run_at = now + timedelta(seconds=2 ** (job.attempts - 1))
                job.error_code = code.value
                job.error_message = ERROR_MESSAGES[code]
                job.updated_at = now
            else:
                job.status = ProcessingJobStatus.FAILED
                job.error_code = code.value
                job.error_message = ERROR_MESSAGES[code]
                job.finished_at = now
                job.updated_at = now
                record.status = RecordStatus.FAILED
                record.updated_at = now
            await session.flush()
        await self._record_notifier.notify(record_id)
