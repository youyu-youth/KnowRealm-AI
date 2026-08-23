import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.base import utcnow
from app.models.course import Course
from app.models.document import AiSummary, ProcessingJob, Transcript
from app.models.record import Record
from app.schemas.document import AiSummaryStatus, ProcessingJobStatus, ProcessingJobType
from app.schemas.record import RecordStatus
from app.schemas.summary import (
    SummaryAction,
    SummaryBlockedReason,
    SummaryOut,
    SummaryReadOut,
    SummarySection,
)
from app.services.local_config import (
    LlmProviderConfig,
    llm_consent,
    llm_provider_fingerprint,
    load_llm_provider,
)


@dataclass(frozen=True)
class SubmittedSummaryJob:
    job_id: str
    created: bool


def _summary_out(summary: AiSummary) -> SummaryOut:
    payload = cast(object, json.loads(summary.summary_json))
    payload_dict = cast(dict[str, object], payload) if isinstance(payload, dict) else {}
    sections = payload_dict.get("sections")
    section_items = cast(list[object], sections) if isinstance(sections, list) else []
    return SummaryOut(
        id=summary.id,
        record_id=summary.record_id,
        version_no=summary.version_no,
        transcript_source_version=summary.transcript_source_version,
        topic=summary.topic,
        abstract=summary.abstract,
        sections=[SummarySection.model_validate(item) for item in section_items],
        status=summary.status,
        model=summary.model,
        prompt_version=summary.prompt_version,
        created_at=summary.created_at,
    )


async def _provider_state(data_dir: Path) -> tuple[LlmProviderConfig | None, bool]:
    provider, consent = await asyncio.gather(
        asyncio.to_thread(load_llm_provider, data_dir),
        asyncio.to_thread(llm_consent, data_dir),
    )
    return provider, consent[1]


class SummaryService:
    @staticmethod
    async def read(
        session: AsyncSession,
        data_dir: Path,
        record_id: str,
    ) -> SummaryReadOut:
        record = (
            await session.scalars(
                select(Record).where(Record.id == record_id, Record.deleted_at.is_(None))
            )
        ).one_or_none()
        if record is None:
            raise HTTPException(status_code=404, detail="学习记录不存在或已删除")
        current = (
            await session.scalars(
                select(AiSummary)
                .where(
                    AiSummary.record_id == record_id,
                    AiSummary.deleted_at.is_(None),
                    AiSummary.status == AiSummaryStatus.GENERATED,
                )
                .order_by(AiSummary.version_no.desc())
                .limit(1)
            )
        ).one_or_none()
        if current is not None:
            return SummaryReadOut(
                summary=_summary_out(current),
                action_required=SummaryAction.NONE,
            )
        active_job = (
            await session.scalars(
                select(ProcessingJob)
                .where(
                    ProcessingJob.record_id == record_id,
                    ProcessingJob.job_type == ProcessingJobType.SUMMARY,
                    ProcessingJob.status.in_(
                        (ProcessingJobStatus.PENDING, ProcessingJobStatus.RUNNING)
                    ),
                )
                .order_by(ProcessingJob.created_at.desc())
                .limit(1)
            )
        ).one_or_none()
        if active_job is not None:
            return SummaryReadOut(
                summary=None,
                action_required=SummaryAction.NONE,
                active_job_id=active_job.id,
            )
        course = await session.get(Course, record.course_id) if record.course_id else None
        if course is None or course.deleted_at is not None or course.status != "ACTIVE":
            return SummaryReadOut(
                summary=None,
                action_required=SummaryAction.NONE,
                blocked_reason=SummaryBlockedReason.COURSE_ARCHIVED,
            )
        transcript = (
            await session.scalars(
                select(Transcript).where(
                    Transcript.record_id == record_id,
                    Transcript.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        if transcript is None:
            return SummaryReadOut(
                summary=None,
                action_required=SummaryAction.NONE,
                blocked_reason=SummaryBlockedReason.TRANSCRIPT_NOT_READY,
            )
        provider, consent_current = await _provider_state(data_dir)
        if provider is None or not provider.api_key:
            return SummaryReadOut(summary=None, action_required=SummaryAction.CONFIGURE_PROVIDER)
        if not consent_current:
            return SummaryReadOut(summary=None, action_required=SummaryAction.GRANT_CONSENT)
        failed_job = (
            await session.scalars(
                select(ProcessingJob)
                .where(
                    ProcessingJob.record_id == record_id,
                    ProcessingJob.job_type == ProcessingJobType.SUMMARY,
                    ProcessingJob.status == ProcessingJobStatus.FAILED,
                )
                .order_by(ProcessingJob.created_at.desc())
                .limit(1)
            )
        ).one_or_none()
        return SummaryReadOut(
            summary=None,
            action_required=(
                SummaryAction.RETRY
                if record.status == RecordStatus.FAILED and failed_job is not None
                else SummaryAction.GENERATE
            ),
        )

    @staticmethod
    async def submit(
        session: AsyncSession,
        data_dir: Path,
        record_id: str,
    ) -> SubmittedSummaryJob:
        provider, consent_current = await _provider_state(data_dir)
        if provider is None or not provider.api_key:
            raise HTTPException(status_code=409, detail="请先配置 LLM Provider")
        if not consent_current:
            raise HTTPException(status_code=409, detail="请先同意发送 Transcript")
        async with session.begin():
            return await SummaryService._enqueue(
                session,
                record_id,
                provider,
                allow_retry=True,
            )

    @staticmethod
    async def enqueue_if_eligible(
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
        record_id: str,
    ) -> SubmittedSummaryJob | None:
        provider, consent_current = await _provider_state(data_dir)
        if provider is None or not provider.api_key or not consent_current:
            return None
        async with session_factory() as session, session.begin():
            try:
                return await SummaryService._enqueue(
                    session,
                    record_id,
                    provider,
                    allow_retry=False,
                )
            except HTTPException:
                return None

    @staticmethod
    async def _enqueue(
        session: AsyncSession,
        record_id: str,
        provider: LlmProviderConfig,
        *,
        allow_retry: bool,
    ) -> SubmittedSummaryJob:
        record = (
            await session.scalars(
                select(Record).where(Record.id == record_id, Record.deleted_at.is_(None))
            )
        ).one_or_none()
        if record is None:
            raise HTTPException(status_code=404, detail="学习记录不存在或已删除")
        active = (
            await session.scalars(
                select(ProcessingJob).where(
                    ProcessingJob.record_id == record_id,
                    ProcessingJob.job_type == ProcessingJobType.SUMMARY,
                    ProcessingJob.status.in_(
                        (ProcessingJobStatus.PENDING, ProcessingJobStatus.RUNNING)
                    ),
                )
            )
        ).one_or_none()
        if active is not None:
            return SubmittedSummaryJob(active.id, False)
        course = await session.get(Course, record.course_id) if record.course_id else None
        if course is None or course.deleted_at is not None or course.status != "ACTIVE":
            raise HTTPException(status_code=409, detail="归档课程不能生成总结")
        transcript = (
            await session.scalars(
                select(Transcript).where(
                    Transcript.record_id == record_id,
                    Transcript.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        if transcript is None:
            raise HTTPException(status_code=409, detail="Transcript 尚未生成")
        if record.status == RecordStatus.FAILED and allow_retry:
            failed = (
                await session.scalars(
                    select(ProcessingJob)
                    .where(
                        ProcessingJob.record_id == record_id,
                        ProcessingJob.job_type == ProcessingJobType.SUMMARY,
                        ProcessingJob.status == ProcessingJobStatus.FAILED,
                    )
                    .order_by(ProcessingJob.created_at.desc())
                    .limit(1)
                )
            ).one_or_none()
            if failed is not None:
                failed.status = ProcessingJobStatus.PENDING
                failed.progress = 0
                failed.attempts = 0
                failed.next_run_at = None
                failed.result_json = None
                failed.error_code = None
                failed.error_message = None
                failed.started_at = None
                failed.finished_at = None
                failed.updated_at = utcnow()
                record.status = RecordStatus.SUMMARY_PENDING
                record.updated_at = utcnow()
                return SubmittedSummaryJob(failed.id, False)
        if record.status != RecordStatus.SUMMARY_PENDING:
            raise HTTPException(status_code=409, detail="当前状态不能生成总结")
        now = utcnow()
        job = ProcessingJob(
            id=str(uuid4()),
            record_id=record_id,
            job_type=ProcessingJobType.SUMMARY,
            status=ProcessingJobStatus.PENDING,
            progress=0,
            attempts=0,
            max_attempts=1,
            next_run_at=None,
            waiting_reason=None,
            input_json=json.dumps(
                {
                    "transcript_source_version": transcript.source_version,
                    "provider_fingerprint": llm_provider_fingerprint(provider),
                },
                separators=(",", ":"),
            ),
            result_json=None,
            error_code=None,
            error_message=None,
            started_at=None,
            finished_at=None,
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        await session.flush()
        return SubmittedSummaryJob(job.id, True)
