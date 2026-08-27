import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from fastapi import HTTPException
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.base import utcnow
from app.models.course import Course
from app.models.document import AiSummary, LearningEvent, ProcessingJob, Transcript
from app.models.record import Record
from app.schemas.document import AiSummaryStatus, ProcessingJobStatus, ProcessingJobType
from app.schemas.record import RecordStatus
from app.schemas.summary import (
    SummaryAction,
    SummaryAdjustRequest,
    SummaryBlockedReason,
    SummaryConfirmOut,
    SummaryConfirmRequest,
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
        user_feedback=summary.user_feedback,
        created_at=summary.created_at,
    )


async def _provider_state(data_dir: Path) -> tuple[LlmProviderConfig | None, bool]:
    provider, consent = await asyncio.gather(
        asyncio.to_thread(load_llm_provider, data_dir),
        asyncio.to_thread(llm_consent, data_dir),
    )
    return provider, consent[1]


async def _get_record(session: AsyncSession, record_id: str) -> Record:
    record = (
        await session.scalars(
            select(Record).where(Record.id == record_id, Record.deleted_at.is_(None))
        )
    ).one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="学习记录不存在或已删除")
    return record


async def _active_summary_job(
    session: AsyncSession,
    record_id: str,
) -> ProcessingJob | None:
    return (
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


async def _current_summary(
    session: AsyncSession,
    record_id: str,
    status: AiSummaryStatus,
) -> AiSummary | None:
    return (
        await session.scalars(
            select(AiSummary)
            .where(
                AiSummary.record_id == record_id,
                AiSummary.deleted_at.is_(None),
                AiSummary.status == status,
            )
            .order_by(AiSummary.version_no.desc())
            .limit(1)
        )
    ).one_or_none()


class SummaryService:
    @staticmethod
    async def read(
        session: AsyncSession,
        data_dir: Path,
        record_id: str,
    ) -> SummaryReadOut:
        record = await _get_record(session, record_id)
        active_job = await _active_summary_job(session, record_id)
        if active_job is not None:
            return SummaryReadOut(
                summary=None,
                action_required=SummaryAction.NONE,
                active_job_id=active_job.id,
            )
        generated = await _current_summary(session, record_id, AiSummaryStatus.GENERATED)
        if generated is not None:
            return SummaryReadOut(
                summary=_summary_out(generated),
                action_required=SummaryAction.NONE,
            )
        confirmed = await _current_summary(session, record_id, AiSummaryStatus.CONFIRMED)
        if confirmed is not None:
            return SummaryReadOut(
                summary=_summary_out(confirmed),
                action_required=SummaryAction.NONE,
            )
        if record.course_id is None:
            return SummaryReadOut(
                summary=None,
                action_required=SummaryAction.NONE,
                blocked_reason=SummaryBlockedReason.COURSE_REQUIRED,
            )
        course = await session.get(Course, record.course_id)
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
    async def adjust(
        session: AsyncSession,
        data_dir: Path,
        record_id: str,
        body: SummaryAdjustRequest,
    ) -> SubmittedSummaryJob:
        provider, consent_current = await _provider_state(data_dir)
        if provider is None or not provider.api_key:
            raise HTTPException(status_code=409, detail="请先配置 LLM Provider")
        if not consent_current:
            raise HTTPException(status_code=409, detail="请先同意发送 Transcript")
        async with session.begin():
            record = await _get_record(session, record_id)
            if record.status != RecordStatus.SUMMARY_READY:
                raise HTTPException(status_code=409, detail="当前状态不能调整总结")
            active = await _active_summary_job(session, record_id)
            if active is not None:
                raise HTTPException(status_code=409, detail="已有进行中的总结任务")
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
            current = await _current_summary(session, record_id, AiSummaryStatus.GENERATED)
            if current is None:
                raise HTTPException(status_code=409, detail="没有可调整的总结")
            if current.id != str(body.summary_id):
                raise HTTPException(status_code=409, detail="总结已是旧版本，请刷新后重试")
            failed_jobs = list(
                (
                    await session.scalars(
                        select(ProcessingJob)
                        .where(
                            ProcessingJob.record_id == record_id,
                            ProcessingJob.job_type == ProcessingJobType.SUMMARY,
                            ProcessingJob.status == ProcessingJobStatus.FAILED,
                        )
                        .order_by(ProcessingJob.created_at.desc())
                    )
                ).all()
            )
            for failed in failed_jobs:
                input_data = cast(dict[str, object], json.loads(failed.input_json))
                if input_data.get("base_summary_id") == current.id:
                    input_data["feedback"] = body.feedback
                    _requeue_failed(
                        failed, input_json=json.dumps(input_data, separators=(",", ":"))
                    )
                    return SubmittedSummaryJob(failed.id, False)
            now = utcnow()
            job = _new_summary_job(
                record_id,
                input_json=json.dumps(
                    {
                        "transcript_source_version": transcript.source_version,
                        "provider_fingerprint": llm_provider_fingerprint(provider),
                        "base_summary_id": current.id,
                        "feedback": body.feedback,
                    },
                    separators=(",", ":"),
                ),
                now=now,
            )
            session.add(job)
            await session.flush()
            return SubmittedSummaryJob(job.id, True)

    @staticmethod
    async def confirm(
        session: AsyncSession,
        record_id: str,
        body: SummaryConfirmRequest,
    ) -> SummaryConfirmOut:
        async with session.begin():
            record = await _get_record(session, record_id)
            summary = await session.get(AiSummary, str(body.summary_id))
            if summary is None or summary.record_id != record_id or summary.deleted_at is not None:
                raise HTTPException(status_code=404, detail="总结不存在")
            if summary.status == AiSummaryStatus.CONFIRMED:
                return SummaryConfirmOut(
                    summary=_summary_out(summary),
                    record_status=record.status,
                )
            if summary.status != AiSummaryStatus.GENERATED:
                raise HTTPException(status_code=409, detail="总结已是旧版本，不能确认")
            if record.status != RecordStatus.SUMMARY_READY:
                raise HTTPException(status_code=409, detail="当前状态不能确认总结")
            if record.course_id is None:
                raise HTTPException(status_code=409, detail="学习记录缺少课程归属，不能确认")
            now = utcnow()
            summary.status = AiSummaryStatus.CONFIRMED
            summary.confirmed_at = now
            summary.updated_at = now
            record.status = RecordStatus.COMPLETED
            record.summary_confirmed_at = now
            record.updated_at = now
            session.add(
                LearningEvent(
                    id=str(uuid4()),
                    course_id=record.course_id,
                    record_id=record_id,
                    concept_id=None,
                    event_type="SUMMARY_CONFIRMED",
                    source_type="AI_SUMMARY",
                    source_id=summary.id,
                    result=None,
                    score=None,
                    difficulty=None,
                    duration_ms=None,
                    metadata_json=json.dumps(
                        {"summary_version_no": summary.version_no},
                        separators=(",", ":"),
                    ),
                    idempotency_key=f"summary-confirmed:{summary.id}",
                    schema_version=1,
                    occurred_at=now,
                    created_at=now,
                )
            )
            return SummaryConfirmOut(
                summary=_summary_out(summary),
                record_status=record.status,
            )

    @staticmethod
    async def list_versions(
        session: AsyncSession,
        record_id: str,
    ) -> list[SummaryOut]:
        await _get_record(session, record_id)
        summaries = list(
            (
                await session.scalars(
                    select(AiSummary)
                    .where(
                        AiSummary.record_id == record_id,
                        AiSummary.deleted_at.is_(None),
                    )
                    .order_by(AiSummary.version_no.desc())
                )
            ).all()
        )
        return [_summary_out(summary) for summary in summaries]

    @staticmethod
    async def get_version(
        session: AsyncSession,
        record_id: str,
        summary_id: str,
    ) -> SummaryOut:
        await _get_record(session, record_id)
        summary = (
            await session.scalars(
                select(AiSummary).where(
                    AiSummary.id == summary_id,
                    AiSummary.record_id == record_id,
                    AiSummary.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        if summary is None:
            raise HTTPException(status_code=404, detail="总结不存在")
        return _summary_out(summary)

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
    async def enqueue_if_eligible_best_effort(
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
        record_id: str,
        *,
        log_event: str,
        error_code: str,
    ) -> str | None:
        # 供本地事务已提交的调用方使用：Provider、同意或入队异常都不回滚本地事实。
        try:
            submitted = await SummaryService.enqueue_if_eligible(
                session_factory, data_dir, record_id
            )
            return submitted.job_id if submitted is not None else None
        except Exception:
            logger.error(log_event, error_code=error_code, record_id=record_id)
            return None

    @staticmethod
    async def _enqueue(
        session: AsyncSession,
        record_id: str,
        provider: LlmProviderConfig,
        *,
        allow_retry: bool,
    ) -> SubmittedSummaryJob:
        record = await _get_record(session, record_id)
        active = await _active_summary_job(session, record_id)
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
                _requeue_failed(failed)
                record.status = RecordStatus.SUMMARY_PENDING
                record.updated_at = utcnow()
                return SubmittedSummaryJob(failed.id, False)
        if record.status != RecordStatus.SUMMARY_PENDING:
            raise HTTPException(status_code=409, detail="当前状态不能生成总结")
        now = utcnow()
        job = _new_summary_job(
            record_id,
            input_json=json.dumps(
                {
                    "transcript_source_version": transcript.source_version,
                    "provider_fingerprint": llm_provider_fingerprint(provider),
                },
                separators=(",", ":"),
            ),
            now=now,
        )
        session.add(job)
        await session.flush()
        return SubmittedSummaryJob(job.id, True)


def _requeue_failed(job: ProcessingJob, *, input_json: str | None = None) -> None:
    if input_json is not None:
        job.input_json = input_json
    job.status = ProcessingJobStatus.PENDING
    job.progress = 0
    job.attempts = 0
    job.next_run_at = None
    job.result_json = None
    job.error_code = None
    job.error_message = None
    job.started_at = None
    job.finished_at = None
    job.updated_at = utcnow()


def _new_summary_job(record_id: str, *, input_json: str, now: datetime) -> ProcessingJob:
    return ProcessingJob(
        id=str(uuid4()),
        record_id=record_id,
        job_type=ProcessingJobType.SUMMARY,
        status=ProcessingJobStatus.PENDING,
        progress=0,
        attempts=0,
        max_attempts=1,
        next_run_at=None,
        waiting_reason=None,
        input_json=input_json,
        result_json=None,
        error_code=None,
        error_message=None,
        started_at=None,
        finished_at=None,
        created_at=now,
        updated_at=now,
    )
