import json
from typing import cast

from fastapi import HTTPException
from sqlalchemy import case, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utcnow
from app.models.document import ProcessingJob
from app.models.record import Record
from app.schemas.document import (
    AsrChunkStatus,
    ProcessingJobErrorCode,
    ProcessingJobOut,
    ProcessingJobStatus,
    ProcessingJobType,
    ProcessingJobWaitingReason,
    RecordJobsOut,
)
from app.schemas.record import RecordStatus
from app.services.processing_job_policy import RETRYABLE_PROCESSING_JOB_ERROR_CODES
from app.services.record_service import RecordService


def _reset_failed_asr_chunk(value: object) -> object:
    if not isinstance(value, dict):
        return value
    state = cast(dict[str, object], value)
    if state.get("status") not in (AsrChunkStatus.FAILED, AsrChunkStatus.EXPIRED):
        return state
    return {"index": state.get("index"), "status": AsrChunkStatus.PENDING}


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
            waiting_reason=(
                ProcessingJobWaitingReason(job.waiting_reason)
                if job.waiting_reason is not None
                else None
            ),
            error_code=(
                ProcessingJobErrorCode(job.error_code) if job.error_code is not None else None
            ),
            retryable=retryable,
        )

    @staticmethod
    async def list_for_record(session: AsyncSession, record_id: str) -> RecordJobsOut:
        if await RecordService.get(session, record_id) is None:
            raise HTTPException(status_code=404, detail="学习记录不存在或已删除")
        jobs = list(
            (
                await session.scalars(
                    select(ProcessingJob)
                    .where(ProcessingJob.record_id == record_id)
                    .order_by(
                        case(
                            (ProcessingJob.job_type == ProcessingJobType.AUDIO_TRANSCODE, 0),
                            (ProcessingJob.job_type == ProcessingJobType.DOCUMENT_PARSE, 1),
                            (ProcessingJob.job_type == ProcessingJobType.ASR, 2),
                            else_=3,
                        ),
                        ProcessingJob.created_at,
                        ProcessingJob.id,
                    )
                )
            ).all()
        )
        progress = sum(job.progress for job in jobs) / len(jobs) if jobs else 0
        return RecordJobsOut(
            jobs=[ProcessingJobService.to_out(job) for job in jobs],
            progress=progress,
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
        now = utcnow()
        job = await session.get(ProcessingJob, job_id)
        if (
            job is None
            or job.status != ProcessingJobStatus.FAILED
            or job.error_code not in {code.value for code in RETRYABLE_PROCESSING_JOB_ERROR_CODES}
        ):
            raise HTTPException(status_code=409, detail="当前处理任务不能重试")

        if job.job_type == ProcessingJobType.ASR and job.result_json:
            raw_checkpoint: object = json.loads(job.result_json)
            if isinstance(raw_checkpoint, dict):
                checkpoint = cast(dict[str, object], raw_checkpoint)
                raw_chunks = checkpoint.get("chunks")
                if isinstance(raw_chunks, list):
                    chunks = cast(list[object], raw_chunks)
                    checkpoint["chunks"] = [_reset_failed_asr_chunk(state) for state in chunks]
                    job.result_json = json.dumps(checkpoint, separators=(",", ":"))
        elif job.job_type != ProcessingJobType.ASR:
            job.result_json = None

        if job.job_type not in (
            ProcessingJobType.DOCUMENT_PARSE,
            ProcessingJobType.AUDIO_TRANSCODE,
            ProcessingJobType.ASR,
        ):
            raise HTTPException(status_code=409, detail="当前处理任务不能重试")

        job_result = await session.execute(
            update(ProcessingJob)
            .where(
                ProcessingJob.id == job_id,
                ProcessingJob.record_id == record_id,
                ProcessingJob.status == ProcessingJobStatus.FAILED,
                ProcessingJob.error_code.in_(
                    {code.value for code in RETRYABLE_PROCESSING_JOB_ERROR_CODES}
                ),
            )
            .values(
                status=ProcessingJobStatus.PENDING,
                progress=0,
                attempts=0,
                next_run_at=None,
                waiting_reason=None,
                error_code=None,
                error_message=None,
                started_at=None,
                finished_at=None,
                result_json=job.result_json,
                updated_at=now,
            )
        )
        if not isinstance(job_result, CursorResult) or job_result.rowcount != 1:
            raise HTTPException(status_code=409, detail="当前处理任务不能重试")
        record_result = await session.execute(
            update(Record)
            .where(Record.id == record_id, Record.deleted_at.is_(None))
            .values(status=RecordStatus.CONTENT_PROCESSING, updated_at=now)
        )
        if not isinstance(record_result, CursorResult) or record_result.rowcount != 1:
            raise HTTPException(status_code=404, detail="学习记录不存在或已删除")
        await session.commit()
        await session.refresh(job)
        return ProcessingJobService.to_out(job)
