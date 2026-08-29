"""知识点生成执行体描述（任务循环骨架见 job_runner.py，ADR-0012）。"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from sqlalchemy import select
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
from app.schemas.document import ProcessingJobStatus, ProcessingJobType
from app.schemas.knowledge_point import (
    KnowledgePointGenerationStatus,
    KnowledgePointInputMode,
)
from app.schemas.summary import SummaryContent
from app.services.job_runner import (
    CancelClaim,
    ClaimCheck,
    ClaimedJob,
    LoopFailure,
    Ready,
    WorkerSpec,
    mark_failed,
    recover_running_to_failed,
)
from app.services.local_config import (
    LlmProviderConfig,
    llm_consent,
    llm_provider_fingerprint,
    load_llm_provider,
)
from app.services.record_invalidation import RecordInvalidationNotifier
from app.services.summary_derivation import (
    PREREQUISITE_CHANGED,
    summary_content,
    summary_source_is_current,
)

PROMPT_VERSION = "kp_v1"


@dataclass(frozen=True)
class _ClaimedKnowledgePointJob(ClaimedJob):
    summary_id: str
    source_version: int
    input_mode: KnowledgePointInputMode
    transcript: str | None
    summary: SummaryContent
    course: Course
    provider: LlmProviderConfig


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
    return summary_source_is_current(record, course, summary, record_id=record_id) and bool(
        transcript is not None and transcript.source_version == source_version
    )


async def preflight(data_dir: Path) -> LlmProviderConfig | None:
    provider = await asyncio.to_thread(load_llm_provider, data_dir)
    consent_at, consent_current = await asyncio.to_thread(llm_consent, data_dir)
    if provider is None or not provider.api_key or not consent_current or consent_at is None:
        return None
    return provider


async def find_candidate(session: AsyncSession, now: datetime) -> ProcessingJob | None:
    return (
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


async def validate_claim(
    session: AsyncSession,
    job: ProcessingJob,
    record_id: str,
    provider: LlmProviderConfig | None,
) -> ClaimCheck[_ClaimedKnowledgePointJob]:
    current_provider = cast(LlmProviderConfig, provider)  # preflight 通过时必非 None
    record = await session.get(Record, record_id)
    input_data = cast(dict[str, object], json.loads(job.input_json))
    summary_id = input_data.get("generated_from_summary_id")
    source_version = input_data.get("transcript_source_version")
    raw_input_mode = input_data.get("input_mode")
    summary = await session.get(AiSummary, summary_id) if isinstance(summary_id, str) else None
    transcript = (
        await session.scalars(
            select(Transcript).where(
                Transcript.record_id == record_id,
                Transcript.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    course = await session.get(Course, record.course_id) if record and record.course_id else None
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
            record_id=record_id,
            source_version=source_version,
        )
        or input_mode is None
        or input_data.get("provider_fingerprint") != llm_provider_fingerprint(current_provider)
    ):
        return CancelClaim(PREREQUISITE_CHANGED)
    current_summary = cast(AiSummary, summary)
    return Ready(
        _ClaimedKnowledgePointJob(
            job_id=job.id,
            record_id=record_id,
            summary_id=current_summary.id,
            source_version=source_version,
            input_mode=input_mode,
            transcript=(
                cast(Transcript, transcript).content
                if input_mode == KnowledgePointInputMode.FULL_TRANSCRIPT
                else None
            ),
            summary=summary_content(current_summary),
            course=cast(Course, course),
            provider=current_provider,
        )
    )


async def execute(
    ctx: _ClaimedKnowledgePointJob,
    session_factory: async_sessionmaker[AsyncSession],
    model: KnowledgePointModel,
) -> KnowledgePointCallResult:
    return await call_knowledge_point_model(
        session_factory=session_factory,
        knowledge_point_model=model,
        provider=ctx.provider,
        prompt=build_knowledge_point_prompt(ctx),
        prompt_version=PROMPT_VERSION,
    )


async def writeback(
    ctx: _ClaimedKnowledgePointJob,
    call_result: KnowledgePointCallResult,
    session_factory: async_sessionmaker[AsyncSession],
) -> bool:
    now = utcnow()
    async with session_factory() as session, session.begin():
        job = await session.get(ProcessingJob, ctx.job_id)
        record = await session.get(Record, ctx.record_id)
        summary = await session.get(AiSummary, ctx.summary_id)
        transcript = (
            await session.scalars(
                select(Transcript).where(
                    Transcript.record_id == ctx.record_id,
                    Transcript.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        course = (
            await session.get(Course, record.course_id) if record and record.course_id else None
        )
        if job is None or job.status != ProcessingJobStatus.RUNNING:
            return False
        if not _source_is_current(
            record,
            course,
            summary,
            transcript,
            record_id=ctx.record_id,
            source_version=ctx.source_version,
        ):
            job.status = ProcessingJobStatus.CANCELLED
            job.result_json = json.dumps({"reason": PREREQUISITE_CHANGED})
            job.finished_at = now
            job.updated_at = now
            return False
        for candidate in call_result.content.items:
            session.add(
                KnowledgePoint(
                    id=str(uuid4()),
                    record_id=ctx.record_id,
                    batch_id=ctx.job_id,
                    name=candidate.name,
                    detail=candidate.detail,
                    tags=json.dumps(candidate.tags, ensure_ascii=False, separators=(",", ":")),
                    importance=candidate.importance,
                    generated_from_summary_id=ctx.summary_id,
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
                "model": ctx.provider.model,
                "prompt_version": PROMPT_VERSION,
                "candidate_count": len(call_result.content.items),
                "input_mode": ctx.input_mode,
            },
            separators=(",", ":"),
        )
        job.error_code = None
        job.error_message = None
        job.finished_at = now
        job.updated_at = now
    return True


def failure_code(ctx: _ClaimedKnowledgePointJob, exc: Exception) -> str | None:
    if isinstance(exc, StructuredGenerationError):
        return exc.code
    return "INTERNAL_ERROR"


async def apply_failure(
    session: AsyncSession,
    job: ProcessingJob,
    record: Record | None,
    error_code: str,
    now: datetime,
) -> bool:
    del record, session  # 知识点域失败不触碰记录状态
    mark_failed(job, code=error_code, message="知识点生成失败，请检查 Provider 后重试", now=now)
    return True


def knowledge_point_spec(
    session_factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
    model: KnowledgePointModel,
    record_notifier: RecordInvalidationNotifier,
) -> WorkerSpec[LlmProviderConfig, _ClaimedKnowledgePointJob, KnowledgePointCallResult]:
    async def recover() -> None:
        await recover_running_to_failed(
            session_factory,
            record_notifier,
            ProcessingJobType.KNOWLEDGE_EXTRACTION,
            "知识点生成被意外中断",
        )

    def classify(_exc: Exception) -> LoopFailure:
        return LoopFailure(event="knowledge_point_worker_unexpected_failure")

    return WorkerSpec(
        name="knowledge_point_worker",
        job_type=ProcessingJobType.KNOWLEDGE_EXTRACTION,
        interrupted_error_message="知识点生成被意外中断",
        poll_interval=0.25,
        find_candidate=find_candidate,
        validate_claim=validate_claim,
        execute=lambda ctx: execute(ctx, session_factory, model),
        writeback=lambda ctx, result: writeback(ctx, result, session_factory),
        failure_code=failure_code,
        apply_failure=apply_failure,
        recover_interrupted=recover,
        classify_loop_error=classify,
        preflight=lambda: preflight(data_dir),
    )
