from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import ProcessingJob
from app.schemas.document import (
    ProcessingJobErrorCode,
    ProcessingJobOut,
    ProcessingJobStatus,
    ProcessingJobType,
)
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
        retryable = job.error_code == ProcessingJobErrorCode.TEMPORARY_IO
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
