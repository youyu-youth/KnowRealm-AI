import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.course.models import Course
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.schemas import ProcessingJobStatus, ProcessingJobType
from app.modules.record.models import Record
from app.modules.record.schemas import RecordStatus
from app.modules.review_material.models import ReviewMaterial
from app.modules.review_material.schemas import (
    ReviewMaterialAction,
    ReviewMaterialAdjustRequest,
    ReviewMaterialBlockedReason,
    ReviewMaterialContent,
    ReviewMaterialOut,
    ReviewMaterialReadOut,
    ReviewMaterialStatus,
)
from app.modules.settings.config import (
    LlmProviderConfig,
    llm_consent,
    llm_provider_fingerprint,
    load_llm_provider,
)
from app.modules.summary.models import AiSummary
from app.modules.summary.schemas import AiSummaryStatus
from app.modules.transcript.models import Transcript


def _material_out(material: ReviewMaterial) -> ReviewMaterialOut:
    items = cast(object, json.loads(material.key_list_json))
    return ReviewMaterialOut(
        id=material.id,
        record_id=material.record_id,
        version_no=material.version_no,
        transcript_source_version=material.transcript_source_version,
        generated_from_summary_id=material.generated_from_summary_id,
        quick_review=material.quick_review,
        key_list=cast(list[str], items) if isinstance(items, list) else [],
        mind_map_markdown=material.mind_map_markdown,
        status=ReviewMaterialStatus(material.status),
        model=material.model,
        prompt_version=material.prompt_version,
        user_feedback=material.user_feedback,
        created_at=material.created_at,
    )


async def _provider_state(data_dir: Path) -> tuple[LlmProviderConfig | None, bool]:
    provider, consent = await asyncio.gather(
        asyncio.to_thread(load_llm_provider, data_dir),
        asyncio.to_thread(llm_consent, data_dir),
    )
    return provider, consent[1]


async def _record(session: AsyncSession, record_id: str) -> Record:
    record = (
        await session.scalars(
            select(Record).where(Record.id == record_id, Record.deleted_at.is_(None))
        )
    ).one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="学习记录不存在或已删除")
    return record


async def _active_job(session: AsyncSession, record_id: str) -> ProcessingJob | None:
    return (
        await session.scalars(
            select(ProcessingJob)
            .where(
                ProcessingJob.record_id == record_id,
                ProcessingJob.job_type == ProcessingJobType.REVIEW_MATERIAL_GENERATION,
                ProcessingJob.status.in_(
                    (ProcessingJobStatus.PENDING, ProcessingJobStatus.RUNNING)
                ),
            )
            .order_by(ProcessingJob.created_at.desc())
            .limit(1)
        )
    ).one_or_none()


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


async def _current_material(session: AsyncSession, record_id: str) -> ReviewMaterial | None:
    return (
        await session.scalars(
            select(ReviewMaterial)
            .where(
                ReviewMaterial.record_id == record_id,
                ReviewMaterial.deleted_at.is_(None),
            )
            .order_by(ReviewMaterial.version_no.desc())
            .limit(1)
        )
    ).one_or_none()


async def _current_transcript(session: AsyncSession, record_id: str) -> Transcript | None:
    return (
        await session.scalars(
            select(Transcript).where(
                Transcript.record_id == record_id,
                Transcript.deleted_at.is_(None),
            )
        )
    ).one_or_none()


def _new_job(record_id: str, input_data: dict[str, object], now: datetime) -> ProcessingJob:
    return ProcessingJob(
        id=str(uuid4()),
        record_id=record_id,
        job_type=ProcessingJobType.REVIEW_MATERIAL_GENERATION,
        status=ProcessingJobStatus.PENDING,
        progress=0,
        attempts=0,
        max_attempts=1,
        next_run_at=None,
        waiting_reason=None,
        input_json=json.dumps(input_data, separators=(",", ":")),
        result_json=None,
        error_code=None,
        error_message=None,
        started_at=None,
        finished_at=None,
        created_at=now,
        updated_at=now,
    )


class ReviewMaterialService:
    @staticmethod
    async def read(
        session: AsyncSession,
        data_dir: Path,
        record_id: str,
    ) -> ReviewMaterialReadOut:
        record = await _record(session, record_id)
        active = await _active_job(session, record_id)
        if active is not None:
            return ReviewMaterialReadOut(
                review_material=None,
                action_required=ReviewMaterialAction.NONE,
                active_job_id=active.id,
            )
        material = await _current_material(session, record_id)
        if material is not None:
            transcript = await _current_transcript(session, record_id)
            return ReviewMaterialReadOut(
                review_material=_material_out(material),
                action_required=ReviewMaterialAction.NONE,
                transcript_stale=(
                    transcript is not None
                    and transcript.source_version > material.transcript_source_version
                ),
            )
        summary = await _confirmed_summary(session, record_id)
        if record.status != RecordStatus.COMPLETED or summary is None:
            return ReviewMaterialReadOut(
                review_material=None,
                action_required=ReviewMaterialAction.NONE,
                blocked_reason=ReviewMaterialBlockedReason.SUMMARY_NOT_CONFIRMED,
            )
        course = await session.get(Course, record.course_id) if record.course_id else None
        if course is None or course.deleted_at is not None or course.status != "ACTIVE":
            return ReviewMaterialReadOut(
                review_material=None,
                action_required=ReviewMaterialAction.NONE,
                blocked_reason=ReviewMaterialBlockedReason.COURSE_ARCHIVED,
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
            return ReviewMaterialReadOut(
                review_material=None,
                action_required=ReviewMaterialAction.NONE,
                blocked_reason=ReviewMaterialBlockedReason.TRANSCRIPT_NOT_READY,
            )
        provider, consent = await _provider_state(data_dir)
        if provider is None or not provider.api_key:
            return ReviewMaterialReadOut(
                review_material=None,
                action_required=ReviewMaterialAction.CONFIGURE_PROVIDER,
            )
        if not consent:
            return ReviewMaterialReadOut(
                review_material=None,
                action_required=ReviewMaterialAction.GRANT_CONSENT,
            )
        failed = (
            await session.scalars(
                select(ProcessingJob)
                .where(
                    ProcessingJob.record_id == record_id,
                    ProcessingJob.job_type == ProcessingJobType.REVIEW_MATERIAL_GENERATION,
                    ProcessingJob.status == ProcessingJobStatus.FAILED,
                )
                .order_by(ProcessingJob.created_at.desc())
                .limit(1)
            )
        ).one_or_none()
        return ReviewMaterialReadOut(
            review_material=None,
            action_required=(
                ReviewMaterialAction.RETRY if failed is not None else ReviewMaterialAction.GENERATE
            ),
        )

    @staticmethod
    async def submit(session: AsyncSession, data_dir: Path, record_id: str) -> str:
        provider, consent = await _provider_state(data_dir)
        try:
            async with session.begin():
                record = await _record(session, record_id)
                if record.status != RecordStatus.COMPLETED:
                    raise HTTPException(status_code=409, detail="请先确认总结")
                active = await _active_job(session, record_id)
                if active is not None:
                    raise HTTPException(status_code=409, detail="已有进行中的复习资料任务")
                if await _current_material(session, record_id) is not None:
                    raise HTTPException(status_code=409, detail="复习资料已生成")
                summary = await _confirmed_summary(session, record_id)
                if summary is None:
                    raise HTTPException(status_code=409, detail="请先确认总结")
                course = await session.get(Course, record.course_id) if record.course_id else None
                if course is None or course.deleted_at is not None or course.status != "ACTIVE":
                    raise HTTPException(status_code=409, detail="归档课程不能生成复习资料")
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
                if provider is None or not provider.api_key:
                    raise HTTPException(status_code=409, detail="请先配置 LLM Provider")
                if not consent:
                    raise HTTPException(status_code=409, detail="请先同意发送学习内容")
                job = _new_job(
                    record_id,
                    {
                        "transcript_source_version": transcript.source_version,
                        "provider_fingerprint": llm_provider_fingerprint(provider),
                        "generated_from_summary_id": summary.id,
                    },
                    utcnow(),
                )
                session.add(job)
                await session.flush()
                return job.id
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="已有进行中的复习资料任务") from exc

    @staticmethod
    async def adjust(
        session: AsyncSession,
        data_dir: Path,
        record_id: str,
        body: ReviewMaterialAdjustRequest,
    ) -> str:
        provider, consent = await _provider_state(data_dir)
        try:
            async with session.begin():
                record = await _record(session, record_id)
                if record.status != RecordStatus.COMPLETED:
                    raise HTTPException(status_code=409, detail="请先确认总结")
                active = await _active_job(session, record_id)
                if active is not None:
                    raise HTTPException(status_code=409, detail="已有进行中的复习资料任务")
                current = await _current_material(session, record_id)
                if current is None:
                    raise HTTPException(status_code=404, detail="复习资料不存在")
                if current.status == ReviewMaterialStatus.SUPERSEDED:
                    raise HTTPException(status_code=409, detail="复习资料已是旧版本，请刷新后重试")
                summary = await _confirmed_summary(session, record_id)
                if summary is None:
                    raise HTTPException(status_code=409, detail="请先确认总结")
                course = await session.get(Course, record.course_id) if record.course_id else None
                if course is None or course.deleted_at is not None or course.status != "ACTIVE":
                    raise HTTPException(status_code=409, detail="归档课程不能生成复习资料")
                transcript = await _current_transcript(session, record_id)
                if transcript is None:
                    raise HTTPException(status_code=409, detail="Transcript 尚未生成")
                if provider is None or not provider.api_key:
                    raise HTTPException(status_code=409, detail="请先配置 LLM Provider")
                if not consent:
                    raise HTTPException(status_code=409, detail="请先同意发送学习内容")
                # 绑定当前转写版本：转写更新后的「重新生成」也走本端点（新版本、旧版退场）
                job = _new_job(
                    record_id,
                    {
                        "transcript_source_version": transcript.source_version,
                        "provider_fingerprint": llm_provider_fingerprint(provider),
                        "generated_from_summary_id": summary.id,
                        "base_material_id": current.id,
                        "feedback": body.feedback,
                    },
                    utcnow(),
                )
                session.add(job)
                await session.flush()
                return job.id
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="已有进行中的复习资料任务") from exc

    @staticmethod
    async def confirm(session: AsyncSession, record_id: str) -> ReviewMaterialOut:
        async with session.begin():
            await _record(session, record_id)
            active = await _active_job(session, record_id)
            if active is not None:
                raise HTTPException(status_code=409, detail="已有进行中的复习资料任务")
            material = await _current_material(session, record_id)
            if material is None:
                raise HTTPException(status_code=404, detail="复习资料不存在")
            if material.status == ReviewMaterialStatus.CONFIRMED:
                return _material_out(material)
            if material.status != ReviewMaterialStatus.GENERATED:
                raise HTTPException(status_code=409, detail="复习资料已是旧版本，不能确认")
            now = utcnow()
            material.status = ReviewMaterialStatus.CONFIRMED
            material.confirmed_at = now
            material.updated_at = now
            return _material_out(material)

    @staticmethod
    async def edit(
        session: AsyncSession,
        record_id: str,
        body: ReviewMaterialContent,
    ) -> ReviewMaterialOut:
        async with session.begin():
            await _record(session, record_id)
            active = await _active_job(session, record_id)
            if active is not None:
                raise HTTPException(status_code=409, detail="已有进行中的复习资料任务")
            material = await _current_material(session, record_id)
            if material is None:
                raise HTTPException(status_code=404, detail="复习资料不存在")
            if material.status == ReviewMaterialStatus.SUPERSEDED:
                raise HTTPException(status_code=409, detail="复习资料已是旧版本，请刷新后重试")
            # 手动编辑就地生效：不换代、不迁移状态，仅刷新内容与 updated_at
            material.quick_review = body.quick_review
            material.key_list_json = json.dumps(
                body.key_list, ensure_ascii=False, separators=(",", ":")
            )
            material.mind_map_markdown = body.mind_map_markdown
            material.updated_at = utcnow()
            return _material_out(material)

    @staticmethod
    async def list_versions(session: AsyncSession, record_id: str) -> list[ReviewMaterialOut]:
        await _record(session, record_id)
        materials = list(
            (
                await session.scalars(
                    select(ReviewMaterial)
                    .where(
                        ReviewMaterial.record_id == record_id,
                        ReviewMaterial.deleted_at.is_(None),
                    )
                    .order_by(ReviewMaterial.version_no.desc())
                )
            ).all()
        )
        return [_material_out(material) for material in materials]
