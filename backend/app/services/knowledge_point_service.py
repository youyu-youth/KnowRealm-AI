import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utcnow
from app.models.course import Course
from app.models.document import AiSummary, KnowledgePoint, ProcessingJob, Transcript
from app.models.record import Record
from app.schemas.document import AiSummaryStatus, ProcessingJobStatus, ProcessingJobType
from app.schemas.knowledge_point import (
    KnowledgePointAction,
    KnowledgePointBlockedReason,
    KnowledgePointGenerationStatus,
    KnowledgePointInputMode,
    KnowledgePointOut,
    KnowledgePointReadOut,
)
from app.services.local_config import (
    LlmProviderConfig,
    llm_consent,
    llm_provider_fingerprint,
    load_llm_provider,
)

TRANSCRIPT_LIMIT = 30_000


@dataclass(frozen=True)
class SubmittedKnowledgePointJob:
    job_id: str
    created: bool


def _knowledge_point_out(item: KnowledgePoint) -> KnowledgePointOut:
    raw_tags = cast(object, json.loads(item.tags))
    tag_items = cast(list[object], raw_tags) if isinstance(raw_tags, list) else []
    tags = [value for value in tag_items if isinstance(value, str)]
    return KnowledgePointOut(
        id=item.id,
        record_id=item.record_id,
        batch_id=item.batch_id,
        name=item.name,
        detail=item.detail,
        tags=tags,
        importance=int(item.importance),
        generated_from_summary_id=item.generated_from_summary_id,
        generation_status=KnowledgePointGenerationStatus(item.generation_status),
        created_at=item.created_at,
        updated_at=item.updated_at,
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


async def _confirmed_summary(session: AsyncSession, record_id: str) -> AiSummary | None:
    return (
        await session.scalars(
            select(AiSummary)
            .where(
                AiSummary.record_id == record_id,
                AiSummary.status == AiSummaryStatus.CONFIRMED,
                AiSummary.deleted_at.is_(None),
            )
            .order_by(AiSummary.version_no.desc())
            .limit(1)
        )
    ).one_or_none()


async def _active_job(session: AsyncSession, record_id: str) -> ProcessingJob | None:
    return (
        await session.scalars(
            select(ProcessingJob)
            .where(
                ProcessingJob.record_id == record_id,
                ProcessingJob.job_type == ProcessingJobType.KNOWLEDGE_EXTRACTION,
                ProcessingJob.status.in_(
                    (ProcessingJobStatus.PENDING, ProcessingJobStatus.RUNNING)
                ),
            )
            .order_by(ProcessingJob.created_at.desc())
            .limit(1)
        )
    ).one_or_none()


async def _failed_job(session: AsyncSession, record_id: str) -> ProcessingJob | None:
    return (
        await session.scalars(
            select(ProcessingJob)
            .where(
                ProcessingJob.record_id == record_id,
                ProcessingJob.job_type == ProcessingJobType.KNOWLEDGE_EXTRACTION,
                ProcessingJob.status == ProcessingJobStatus.FAILED,
            )
            .order_by(ProcessingJob.created_at.desc())
            .limit(1)
        )
    ).one_or_none()


async def _visible_items(session: AsyncSession, record_id: str) -> list[KnowledgePoint]:
    return list(
        (
            await session.scalars(
                select(KnowledgePoint)
                .where(
                    KnowledgePoint.record_id == record_id,
                    KnowledgePoint.deleted_at.is_(None),
                    KnowledgePoint.generation_status.in_(
                        (
                            KnowledgePointGenerationStatus.DRAFT,
                            KnowledgePointGenerationStatus.ACTIVE,
                        )
                    ),
                )
                .order_by(KnowledgePoint.importance.desc(), KnowledgePoint.created_at)
            )
        ).all()
    )


def _job_input_mode(job: ProcessingJob) -> KnowledgePointInputMode | None:
    raw = cast(dict[str, object], json.loads(job.input_json))
    value = raw.get("input_mode")
    return KnowledgePointInputMode(value) if isinstance(value, str) else None


class KnowledgePointService:
    @staticmethod
    async def read(
        session: AsyncSession,
        data_dir: Path,
        record_id: str,
    ) -> KnowledgePointReadOut:
        record = await _get_record(session, record_id)
        items = await _visible_items(session, record_id)
        output = [_knowledge_point_out(item) for item in items]
        active = await _active_job(session, record_id)
        if active is not None:
            return KnowledgePointReadOut(
                items=output,
                action_required=KnowledgePointAction.NONE,
                active_job_id=active.id,
                input_mode=_job_input_mode(active),
            )

        course = await session.get(Course, record.course_id) if record.course_id else None
        if course is None or course.deleted_at is not None or course.status != "ACTIVE":
            return KnowledgePointReadOut(
                items=output,
                action_required=KnowledgePointAction.NONE,
                blocked_reason=KnowledgePointBlockedReason.COURSE_ARCHIVED,
            )
        summary = await _confirmed_summary(session, record_id)
        if summary is None:
            return KnowledgePointReadOut(
                items=output,
                action_required=KnowledgePointAction.NONE,
                blocked_reason=KnowledgePointBlockedReason.SUMMARY_NOT_CONFIRMED,
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
            return KnowledgePointReadOut(
                items=output,
                action_required=KnowledgePointAction.NONE,
                blocked_reason=KnowledgePointBlockedReason.TRANSCRIPT_NOT_READY,
            )
        draft = next(
            (
                item
                for item in items
                if item.generation_status == KnowledgePointGenerationStatus.DRAFT
            ),
            None,
        )
        if draft is not None and draft.batch_id is not None:
            job = await session.get(ProcessingJob, draft.batch_id)
            return KnowledgePointReadOut(
                items=output,
                action_required=KnowledgePointAction.CONFIRM,
                input_mode=_job_input_mode(job) if job is not None else None,
            )
        provider, consent_current = await _provider_state(data_dir)
        if provider is None or not provider.api_key:
            return KnowledgePointReadOut(
                items=output,
                action_required=KnowledgePointAction.NONE,
                blocked_reason=KnowledgePointBlockedReason.PROVIDER_NOT_CONFIGURED,
            )
        if not consent_current:
            return KnowledgePointReadOut(
                items=output,
                action_required=KnowledgePointAction.NONE,
                blocked_reason=KnowledgePointBlockedReason.CONSENT_REQUIRED,
            )
        failed = await _failed_job(session, record_id)
        return KnowledgePointReadOut(
            items=output,
            action_required=(
                KnowledgePointAction.RETRY if failed is not None else KnowledgePointAction.GENERATE
            ),
        )

    @staticmethod
    async def submit(
        session: AsyncSession,
        data_dir: Path,
        record_id: str,
    ) -> SubmittedKnowledgePointJob:
        provider, consent_current = await _provider_state(data_dir)
        if provider is None or not provider.api_key:
            raise HTTPException(status_code=409, detail="请先配置 LLM Provider")
        if not consent_current:
            raise HTTPException(status_code=409, detail="请先同意外部 AI 处理")
        try:
            async with session.begin():
                record = await _get_record(session, record_id)
                course = await session.get(Course, record.course_id) if record.course_id else None
                if course is None or course.deleted_at is not None or course.status != "ACTIVE":
                    raise HTTPException(status_code=409, detail="归档课程不能生成知识点")
                summary = await _confirmed_summary(session, record_id)
                if summary is None:
                    raise HTTPException(status_code=409, detail="请先确认当前总结")
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
                if await _active_job(session, record_id) is not None:
                    raise HTTPException(status_code=409, detail="已有进行中的知识点生成任务")
                if any(
                    item.generation_status == KnowledgePointGenerationStatus.DRAFT
                    for item in await _visible_items(session, record_id)
                ):
                    raise HTTPException(status_code=409, detail="已有待确认的知识点候选")

                input_json = _job_input_json(provider, summary, transcript)
                failed = await _failed_job(session, record_id)
                if failed is not None:
                    previous = cast(dict[str, object], json.loads(failed.input_json))
                    if previous.get("generated_from_summary_id") == summary.id:
                        _requeue_failed(failed, input_json)
                        return SubmittedKnowledgePointJob(failed.id, False)

                now = utcnow()
                job = _new_job(record_id, input_json=input_json, now=now)
                session.add(job)
                await session.flush()
                return SubmittedKnowledgePointJob(job.id, True)
        except IntegrityError:
            raise HTTPException(
                status_code=409,
                detail="已有进行中的知识点生成任务",
            ) from None


def _job_input_json(
    provider: LlmProviderConfig,
    summary: AiSummary,
    transcript: Transcript,
) -> str:
    input_mode = (
        KnowledgePointInputMode.SUMMARY_ONLY
        if len(transcript.content) > TRANSCRIPT_LIMIT
        else KnowledgePointInputMode.FULL_TRANSCRIPT
    )
    return json.dumps(
        {
            "provider_fingerprint": llm_provider_fingerprint(provider),
            "generated_from_summary_id": summary.id,
            "transcript_source_version": transcript.source_version,
            "input_mode": input_mode,
        },
        separators=(",", ":"),
    )


def _requeue_failed(job: ProcessingJob, input_json: str) -> None:
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


def _new_job(record_id: str, *, input_json: str, now: datetime) -> ProcessingJob:
    return ProcessingJob(
        id=str(uuid4()),
        record_id=record_id,
        job_type=ProcessingJobType.KNOWLEDGE_EXTRACTION,
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
