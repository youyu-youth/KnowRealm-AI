import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import uuid4

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.llm import (
    KnowledgePointCallResult,
    KnowledgePointModel,
    StructuredGenerationError,
    call_knowledge_point_model,
)
from app.models.base import utcnow
from app.models.course import Course
from app.models.document import AiSummary, KnowledgePoint, ProcessingJob, Transcript
from app.models.record import Record
from app.schemas.course import CourseStatus
from app.schemas.document import AiSummaryStatus, ProcessingJobStatus, ProcessingJobType
from app.schemas.knowledge_point import (
    KnowledgePointGenerationStatus,
    KnowledgePointInputMode,
)
from app.schemas.summary import SummaryContent
from app.services.local_config import (
    LlmProviderConfig,
    llm_consent,
    llm_provider_fingerprint,
    load_llm_provider,
)
from app.services.record_invalidation import RecordInvalidationNotifier

PROMPT_VERSION = "kp_v1"


@dataclass(frozen=True)
class _ClaimedKnowledgePointJob:
    job_id: str
    record_id: str
    summary_id: str
    source_version: int
    input_mode: KnowledgePointInputMode
    transcript: str | None
    summary: SummaryContent
    course: Course
    provider: LlmProviderConfig


def _summary_content(summary: AiSummary) -> SummaryContent:
    payload = cast(dict[str, object], json.loads(summary.summary_json))
    return SummaryContent.model_validate(
        {
            "topic": summary.topic,
            "abstract": summary.abstract,
            "sections": payload.get("sections"),
        }
    )


def build_knowledge_point_prompt(claimed: _ClaimedKnowledgePointJob) -> str:
    sections = "\n".join(
        f"{section.heading}：" + "；".join(section.points) for section in claimed.summary.sections
    )
    transcript = (
        f"\nTranscript：\n{claimed.transcript}"
        if claimed.input_mode == KnowledgePointInputMode.FULL_TRANSCRIPT
        else ""
    )
    return (
        "请从以下课程上下文和已确认总结中提取中文知识点候选。"
        "候选数量按内容密度决定，严格返回指定结构，不添加结构外字段。\n"
        f"学习场景：{claimed.course.learning_context}\n"
        f"教育阶段：{claimed.course.education_stage or '未设置'}\n"
        f"内容深度：{claimed.course.depth or '未设置'}\n"
        "已确认总结：\n"
        f"主题：{claimed.summary.topic}\n"
        f"摘要：{claimed.summary.abstract}\n"
        f"{sections}"
        f"{transcript}"
    )


def _source_is_current(
    record: Record | None,
    course: Course | None,
    summary: AiSummary | None,
    transcript: Transcript | None,
    *,
    record_id: str,
    source_version: int,
) -> bool:
    return bool(
        record is not None
        and record.deleted_at is None
        and course is not None
        and course.deleted_at is None
        and course.status == CourseStatus.ACTIVE
        and summary is not None
        and summary.record_id == record_id
        and summary.deleted_at is None
        and summary.status == AiSummaryStatus.CONFIRMED
        and transcript is not None
        and transcript.source_version == source_version
    )


class KnowledgePointWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
        model: KnowledgePointModel,
        record_notifier: RecordInvalidationNotifier,
    ) -> None:
        self._session_factory = session_factory
        self._data_dir = data_dir
        self._model = model
        self._record_notifier = record_notifier
        self._stopped = asyncio.Event()

    def stop(self) -> None:
        self._stopped.set()

    async def recover_interrupted(self) -> None:
        now = utcnow()
        record_ids: list[str] = []
        async with self._session_factory() as session, session.begin():
            jobs = list(
                (
                    await session.scalars(
                        select(ProcessingJob).where(
                            ProcessingJob.job_type == ProcessingJobType.KNOWLEDGE_EXTRACTION,
                            ProcessingJob.status == ProcessingJobStatus.RUNNING,
                        )
                    )
                ).all()
            )
            for job in jobs:
                job.status = ProcessingJobStatus.FAILED
                job.error_code = "WORKER_INTERRUPTED"
                job.error_message = "知识点生成被意外中断"
                job.finished_at = now
                job.updated_at = now
                if job.record_id is not None:
                    record_ids.append(job.record_id)
        for record_id in record_ids:
            await self._record_notifier.notify(record_id)

    async def run(self) -> None:
        while not self._stopped.is_set():
            try:
                if await self._process_one():
                    continue
            except Exception:
                logger.error(
                    "knowledge_point_worker_unexpected_failure",
                    error_code="INTERNAL_ERROR",
                )
                await self.recover_interrupted()
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=0.25)
            except TimeoutError:
                pass

    async def _process_one(self) -> bool:
        claimed = await self._claim_one()
        if claimed is None:
            return False
        await self._record_notifier.notify(claimed.record_id)
        try:
            call_result = await call_knowledge_point_model(
                session_factory=self._session_factory,
                knowledge_point_model=self._model,
                provider=claimed.provider,
                prompt=build_knowledge_point_prompt(claimed),
                prompt_version=PROMPT_VERSION,
            )
        except StructuredGenerationError as exc:
            await self._fail(claimed, exc.code)
        except Exception:
            await self._fail(claimed, "INTERNAL_ERROR")
        else:
            await self._publish(claimed, call_result)
        return True

    async def _claim_one(self) -> _ClaimedKnowledgePointJob | None:
        provider = await asyncio.to_thread(load_llm_provider, self._data_dir)
        consent_at, consent_current = await asyncio.to_thread(llm_consent, self._data_dir)
        if provider is None or not provider.api_key or not consent_current or consent_at is None:
            return None
        now = utcnow()
        async with self._session_factory() as session, session.begin():
            job = (
                await session.scalars(
                    select(ProcessingJob)
                    .join(Record, ProcessingJob.record_id == Record.id)
                    .where(
                        ProcessingJob.job_type == ProcessingJobType.KNOWLEDGE_EXTRACTION,
                        ProcessingJob.status == ProcessingJobStatus.PENDING,
                        Record.deleted_at.is_(None),
                    )
                    .order_by(ProcessingJob.created_at)
                    .limit(1)
                )
            ).one_or_none()
            if job is None or job.record_id is None:
                return None
            record = await session.get(Record, job.record_id)
            input_data = cast(dict[str, object], json.loads(job.input_json))
            summary_id = input_data.get("generated_from_summary_id")
            source_version = input_data.get("transcript_source_version")
            raw_input_mode = input_data.get("input_mode")
            summary = (
                await session.get(AiSummary, summary_id) if isinstance(summary_id, str) else None
            )
            transcript = (
                await session.scalars(
                    select(Transcript).where(
                        Transcript.record_id == job.record_id,
                        Transcript.deleted_at.is_(None),
                    )
                )
            ).one_or_none()
            course = (
                await session.get(Course, record.course_id) if record and record.course_id else None
            )
            try:
                input_mode = KnowledgePointInputMode(raw_input_mode)
            except ValueError:
                input_mode = None
            if (
                not isinstance(source_version, int)
                or not _source_is_current(
                    record,
                    course,
                    summary,
                    transcript,
                    record_id=job.record_id,
                    source_version=source_version,
                )
                or input_mode is None
                or input_data.get("provider_fingerprint") != llm_provider_fingerprint(provider)
            ):
                job.status = ProcessingJobStatus.CANCELLED
                job.result_json = json.dumps({"reason": "PREREQUISITE_CHANGED"})
                job.finished_at = now
                job.updated_at = now
                return None
            current_summary = cast(AiSummary, summary)
            current_transcript = cast(Transcript, transcript)
            current_course = cast(Course, course)
            claimed = cast(
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
            if claimed.rowcount != 1:
                return None
            return _ClaimedKnowledgePointJob(
                job_id=job.id,
                record_id=job.record_id,
                summary_id=current_summary.id,
                source_version=source_version,
                input_mode=input_mode,
                transcript=(
                    current_transcript.content
                    if input_mode == KnowledgePointInputMode.FULL_TRANSCRIPT
                    else None
                ),
                summary=_summary_content(current_summary),
                course=current_course,
                provider=provider,
            )

    async def _publish(
        self,
        claimed: _ClaimedKnowledgePointJob,
        call_result: KnowledgePointCallResult,
    ) -> None:
        now = utcnow()
        async with self._session_factory() as session, session.begin():
            job = await session.get(ProcessingJob, claimed.job_id)
            record = await session.get(Record, claimed.record_id)
            summary = await session.get(AiSummary, claimed.summary_id)
            transcript = (
                await session.scalars(
                    select(Transcript).where(
                        Transcript.record_id == claimed.record_id,
                        Transcript.deleted_at.is_(None),
                    )
                )
            ).one_or_none()
            course = (
                await session.get(Course, record.course_id) if record and record.course_id else None
            )
            if job is None or job.status != ProcessingJobStatus.RUNNING:
                return
            if not _source_is_current(
                record,
                course,
                summary,
                transcript,
                record_id=claimed.record_id,
                source_version=claimed.source_version,
            ):
                job.status = ProcessingJobStatus.CANCELLED
                job.result_json = json.dumps({"reason": "PREREQUISITE_CHANGED"})
                job.finished_at = now
                job.updated_at = now
                return
            for candidate in call_result.content.items:
                session.add(
                    KnowledgePoint(
                        id=str(uuid4()),
                        record_id=claimed.record_id,
                        batch_id=claimed.job_id,
                        name=candidate.name,
                        detail=candidate.detail,
                        tags=json.dumps(candidate.tags, ensure_ascii=False, separators=(",", ":")),
                        importance=candidate.importance,
                        generated_from_summary_id=claimed.summary_id,
                        generation_status=KnowledgePointGenerationStatus.DRAFT,
                        source_anchor_id=None,
                        created_at=now,
                        updated_at=now,
                        deleted_at=None,
                    )
                )
            job.status = ProcessingJobStatus.SUCCEEDED
            job.progress = 1
            job.result_json = json.dumps(
                {
                    "model": claimed.provider.model,
                    "prompt_version": PROMPT_VERSION,
                    "candidate_count": len(call_result.content.items),
                    "input_mode": claimed.input_mode,
                },
                separators=(",", ":"),
            )
            job.error_code = None
            job.error_message = None
            job.finished_at = now
            job.updated_at = now
        await self._record_notifier.notify(claimed.record_id)

    async def _fail(self, claimed: _ClaimedKnowledgePointJob, error_code: str) -> None:
        now = utcnow()
        async with self._session_factory() as session, session.begin():
            job = await session.get(ProcessingJob, claimed.job_id)
            if job is None or job.status != ProcessingJobStatus.RUNNING:
                return
            job.status = ProcessingJobStatus.FAILED
            job.error_code = error_code
            job.error_message = "知识点生成失败，请检查 Provider 后重试"
            job.finished_at = now
            job.updated_at = now
        await self._record_notifier.notify(claimed.record_id)
