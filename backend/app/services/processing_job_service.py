from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utcnow
from app.models.document import ProcessingJob
from app.models.record import Record
from app.schemas.document import (
    ProcessingJobErrorCode,
    ProcessingJobOut,
    ProcessingJobStatus,
    ProcessingJobType,
)
from app.schemas.record import RecordStatus
from app.services.processing_job_policy import RETRYABLE_PROCESSING_JOB_ERROR_CODES
from app.services.record_service import RecordService


class ProcessingJobService:
    @staticmethod
    async def get(session: AsyncSession, job_id: str) -> ProcessingJob | None:
        job = (
            await session.scalars(select(ProcessingJob).where(ProcessingJob.id == job_id))
        ).one_or_none()
        if job is None or job.record_id is None:
            return None
        if await RecordService.get(session, job.record_id) is None:
            return None
        return job

    @staticmethod
    def to_out(job: ProcessingJob) -> ProcessingJobOut:
        retryable = (
            job.error_code is not None
            and ProcessingJobErrorCode(job.error_code) in RETRYABLE_PROCESSING_JOB_ERROR_CODES
        )
        return ProcessingJobOut(
            id=job.id,
            record_id=job.record_id,
            job_type=ProcessingJobType(job.job_type),
            status=ProcessingJobStatus(job.status),
            progress=job.progress,
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            error_code=(
                ProcessingJobErrorCode(job.error_code) if job.error_code is not None else None
            ),
            retryable=retryable,
        )

    @staticmethod
    async def retry(
        session: AsyncSession,
        job_id: str,
        record_id: str,
    ) -> ProcessingJobOut:
        job_link = (
            await session.execute(select(ProcessingJob.record_id).where(ProcessingJob.id == job_id))
        ).scalar_one_or_none()
        if job_link is None:
            raise HTTPException(status_code=404, detail="处理任务不存在")
        if job_link != record_id:
            raise HTTPException(status_code=409, detail="处理任务与学习记录不匹配")
        record_exists = (
            await session.execute(
                select(Record.id).where(Record.id == record_id, Record.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if record_exists is None:
            raise HTTPException(status_code=404, detail="学习记录不存在或已删除")
        await session.rollback()

        now = utcnow()
        async with session.begin():
            job = (
                await session.scalars(
                    update(ProcessingJob)
                    .where(
                        ProcessingJob.id == job_id,
                        ProcessingJob.record_id == record_id,
                        ProcessingJob.job_type == ProcessingJobType.DOCUMENT_PARSE,
                        ProcessingJob.status == ProcessingJobStatus.FAILED,
                        ProcessingJob.error_code.in_(
                            code.value for code in RETRYABLE_PROCESSING_JOB_ERROR_CODES
                        ),
                    )
                    .values(
                        status=ProcessingJobStatus.PENDING,
                        progress=0,
                        attempts=0,
                        next_run_at=None,
                        result_json=None,
                        error_code=None,
                        error_message=None,
                        started_at=None,
                        finished_at=None,
                        updated_at=now,
                    )
                    .returning(ProcessingJob)
                )
            ).one_or_none()
            if job is None:
                raise HTTPException(status_code=409, detail="当前处理任务不能重试")
            record_result = await session.execute(
                update(Record)
                .where(Record.id == record_id, Record.deleted_at.is_(None))
                .values(status=RecordStatus.CONTENT_PROCESSING, updated_at=now)
            )
            if not isinstance(record_result, CursorResult) or record_result.rowcount != 1:
                raise HTTPException(status_code=404, detail="学习记录不存在或已删除")

        return ProcessingJobService.to_out(job)
