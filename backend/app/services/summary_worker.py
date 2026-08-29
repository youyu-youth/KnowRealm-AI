"""总结生成执行体描述（任务循环骨架见 job_runner.py，ADR-0012）。"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from langchain_core.runnables.config import RunnableConfig
from langgraph.graph.state import CompiledStateGraph  # pyright: ignore[reportMissingTypeStubs]
from langgraph.types import Command  # pyright: ignore[reportMissingTypeStubs]
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.llm import (
    SummaryCallResult,
    SummaryGenerationError,
    SummaryModel,
    call_summary_model,
)
from app.agents.summary import (
    REVIEW_DECISION_ADJUST,
    SummaryRuntime,
    SummaryState,
)
from app.models.base import utcnow
from app.models.course import Course
from app.models.document import AiSummary, ProcessingJob, Transcript
from app.models.record import Record
from app.schemas.document import AiSummaryStatus, ProcessingJobStatus, ProcessingJobType
from app.schemas.record import RecordStatus
from app.schemas.summary import SummaryContent
from app.services.job_runner import (
    CancelClaim,
    ClaimCheck,
    ClaimedJob,
    LoopFailure,
    Ready,
    RunnerContext,
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
from app.services.summary_derivation import PREREQUISITE_CHANGED, summary_content

PROMPT_VERSION = "summary-v1"
ADJUST_PROMPT_VERSION = "summary-adjust-v1"


@dataclass(frozen=True)
class _ClaimedSummary(ClaimedJob):
    source_version: int
    transcript: str
    course: Course
    provider: LlmProviderConfig
    prompt_version: str
    base_summary_id: str | None = None
    previous: SummaryContent | None = None
    feedback: str | None = None


def build_summary_prompt(
    *,
    transcript: str,
    learning_context: str,
    education_stage: str | None,
    depth: str | None,
) -> str:
    return (
        "请根据以下 Transcript 生成中文学习总结。严格返回指定结构，不添加结构外字段。\n"
        f"学习场景：{learning_context}\n"
        f"教育阶段：{education_stage or '未设置'}\n"
        f"内容深度：{depth or '未设置'}\n"
        "Transcript：\n"
        f"{transcript}"
    )


def build_adjust_prompt(
    *,
    transcript: str,
    learning_context: str,
    education_stage: str | None,
    depth: str | None,
    previous: SummaryContent,
    feedback: str,
) -> str:
    sections = "\n".join(
        f"{section.heading}：" + "；".join(section.points) for section in previous.sections
    )
    return (
        "请根据以下 Transcript、上一版总结与用户反馈，生成修订后的中文学习总结。"
        "严格返回指定结构，不添加结构外字段。\n"
        f"学习场景：{learning_context}\n"
        f"教育阶段：{education_stage or '未设置'}\n"
        f"内容深度：{depth or '未设置'}\n"
        "上一版总结：\n"
        f"主题：{previous.topic}\n"
        f"摘要：{previous.abstract}\n"
        f"{sections}\n"
        "用户反馈：\n"
        f"{feedback}\n"
        "Transcript：\n"
        f"{transcript}"
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
                ProcessingJob.job_type == ProcessingJobType.SUMMARY,
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
) -> ClaimCheck[_ClaimedSummary]:
    current_provider = cast(LlmProviderConfig, provider)  # preflight 通过时必非 None
    record = await session.get(Record, record_id)
    transcript = (
        await session.scalars(
            select(Transcript).where(
                Transcript.record_id == record_id,
                Transcript.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    course = await session.get(Course, record.course_id) if record and record.course_id else None
    input_data = cast(dict[str, object], json.loads(job.input_json))
    source_version = input_data.get("transcript_source_version")
    expected_fingerprint = input_data.get("provider_fingerprint")
    base_summary_id = input_data.get("base_summary_id")
    feedback = input_data.get("feedback")
    is_adjust = isinstance(base_summary_id, str) and bool(base_summary_id)
    base_summary: AiSummary | None = None
    if is_adjust:
        base_summary = await session.get(AiSummary, cast(str, base_summary_id))
    if (
        record is None
        or transcript is None
        or course is None
        or course.deleted_at is not None
        or course.status != "ACTIVE"
        or not isinstance(source_version, int)
        or transcript.source_version != source_version
        or expected_fingerprint != llm_provider_fingerprint(current_provider)
        or record.status
        != (RecordStatus.SUMMARY_READY if is_adjust else RecordStatus.SUMMARY_PENDING)
        or (
            is_adjust
            and not (
                isinstance(feedback, str)
                and bool(feedback.strip())
                and base_summary is not None
                and base_summary.record_id == record_id
                and base_summary.deleted_at is None
                and base_summary.status == AiSummaryStatus.GENERATED
            )
        )
    ):
        return CancelClaim(PREREQUISITE_CHANGED)
    previous = summary_content(base_summary) if base_summary is not None else None
    return Ready(
        _ClaimedSummary(
            job_id=job.id,
            record_id=record_id,
            source_version=source_version,
            transcript=transcript.content,
            course=course,
            provider=current_provider,
            prompt_version=ADJUST_PROMPT_VERSION if is_adjust else PROMPT_VERSION,
            base_summary_id=cast(str, base_summary_id) if is_adjust else None,
            previous=previous,
            feedback=cast(str, feedback) if is_adjust else None,
        )
    )


async def on_preempted(
    session: AsyncSession,
    job: ProcessingJob,
    ctx: _ClaimedSummary,
    now: datetime,
) -> _ClaimedSummary:
    del job  # 抢占后仅翻记录状态；job 变更已由抢占原语落库
    record = await session.get(Record, ctx.record_id)
    if record is not None:
        record.status = RecordStatus.SUMMARY_PROCESSING
        record.updated_at = now
    return ctx


async def execute(
    ctx: _ClaimedSummary,
    _runtime: RunnerContext,
    session_factory: async_sessionmaker[AsyncSession],
    graph: CompiledStateGraph[SummaryState, SummaryRuntime, SummaryState, SummaryState],
    summary_model: SummaryModel,
) -> tuple[SummaryContent, SummaryCallResult]:
    call_result: SummaryCallResult | None = None

    async def generate() -> SummaryContent:
        nonlocal call_result
        if ctx.previous is not None:
            prompt: str = build_adjust_prompt(
                transcript=ctx.transcript,
                learning_context=ctx.course.learning_context,
                education_stage=ctx.course.education_stage,
                depth=ctx.course.depth,
                previous=ctx.previous,
                feedback=ctx.feedback or "",
            )
        else:
            prompt = build_summary_prompt(
                transcript=ctx.transcript,
                learning_context=ctx.course.learning_context,
                education_stage=ctx.course.education_stage,
                depth=ctx.course.depth,
            )
        call_result = await call_summary_model(
            session_factory=session_factory,
            summary_model=summary_model,
            provider=ctx.provider,
            prompt=prompt,
            graph_name="summary",
            graph_node="generate",
            prompt_version=ctx.prompt_version,
        )
        return call_result.content

    result = await _invoke_graph(ctx, generate, graph)
    summary = SummaryContent.model_validate(result.get("summary"))
    if call_result is None:
        raise SummaryGenerationError("INTERNAL_ERROR")
    return summary, call_result


async def _invoke_graph(
    claimed: _ClaimedSummary,
    generate: "Callable[[], Awaitable[SummaryContent]]",
    graph: CompiledStateGraph[SummaryState, SummaryRuntime, SummaryState, SummaryState],
) -> SummaryState:
    config = RunnableConfig(
        configurable={"thread_id": f"summary-{claimed.record_id}-source-{claimed.source_version}"}
    )
    context = SummaryRuntime(generate=generate)
    state_input: SummaryState = {
        "record_id": claimed.record_id,
        "source_version": claimed.source_version,
    }
    if claimed.base_summary_id is None:
        return cast(
            SummaryState,
            await graph.ainvoke(  # pyright: ignore[reportUnknownMemberType]
                state_input,
                config,
                context=context,
            ),
        )
    snapshot = await graph.aget_state(config)
    if any(task.interrupts for task in snapshot.tasks):
        return cast(
            SummaryState,
            await graph.ainvoke(  # pyright: ignore[reportUnknownMemberType, reportArgumentType]
                Command(resume=REVIEW_DECISION_ADJUST),
                config,
                context=context,
            ),
        )
    return cast(
        SummaryState,
        await graph.ainvoke(  # pyright: ignore[reportUnknownMemberType]
            state_input,
            config,
            context=context,
        ),
    )


async def writeback(
    ctx: _ClaimedSummary,
    result: tuple[SummaryContent, SummaryCallResult],
    session_factory: async_sessionmaker[AsyncSession],
) -> bool:
    summary, call_result = result
    now = utcnow()
    async with session_factory() as session, session.begin():
        job = await session.get(ProcessingJob, ctx.job_id)
        record = await session.get(Record, ctx.record_id)
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
        if (
            record is None
            or record.deleted_at is not None
            or transcript is None
            or transcript.source_version != ctx.source_version
            or course is None
            or course.deleted_at is not None
            or course.status != "ACTIVE"
        ):
            # Transcript 或课程已变化：总结链整体作废，回到等待重新生成
            return await _cancel_stale(
                session, job, record, now, next_status=RecordStatus.SUMMARY_PENDING
            )
        base_summary: AiSummary | None = None
        if ctx.base_summary_id is not None:
            base_summary = await session.get(AiSummary, ctx.base_summary_id)
            if (
                base_summary is None
                or base_summary.deleted_at is not None
                or base_summary.status != AiSummaryStatus.GENERATED
            ):
                # 上一版不再可调整但 Transcript 未变：回滚到调整前的待确认状态
                return await _cancel_stale(
                    session, job, record, now, next_status=RecordStatus.SUMMARY_READY
                )
        latest_version = await session.scalar(
            select(func.coalesce(func.max(AiSummary.version_no), 0)).where(
                AiSummary.record_id == ctx.record_id
            )
        )
        version_no = cast(int, latest_version) + 1
        summary_id = str(uuid4())
        session.add(
            AiSummary(
                id=summary_id,
                record_id=ctx.record_id,
                version_no=version_no,
                transcript_source_version=ctx.source_version,
                topic=summary.topic,
                abstract=summary.abstract,
                summary_json=json.dumps(
                    {"sections": [section.model_dump() for section in summary.sections]},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                status=AiSummaryStatus.GENERATED,
                model=ctx.provider.model,
                prompt_version=ctx.prompt_version,
                token_usage_json=json.dumps(
                    call_result.token_usage,
                    separators=(",", ":"),
                ),
                latency_ms=call_result.latency_ms,
                user_feedback=ctx.feedback,
                confirmed_at=None,
                created_at=now,
                updated_at=now,
                deleted_at=None,
            )
        )
        if base_summary is not None:
            base_summary.status = AiSummaryStatus.SUPERSEDED
            base_summary.updated_at = now
        job.status = ProcessingJobStatus.SUCCEEDED
        job.progress = 1
        job.result_json = json.dumps({"summary_id": summary_id})
        job.error_code = None
        job.error_message = None
        job.finished_at = now
        job.updated_at = now
        record.status = RecordStatus.SUMMARY_READY
        record.updated_at = now
    return True


async def _cancel_stale(
    session: AsyncSession,
    job: ProcessingJob,
    record: Record | None,
    now: datetime,
    *,
    next_status: RecordStatus,
) -> bool:
    job.status = ProcessingJobStatus.CANCELLED
    job.result_json = json.dumps({"reason": "STALE_TRANSCRIPT"})
    job.finished_at = now
    job.updated_at = now
    if record is not None and record.deleted_at is None:
        record.status = next_status
        record.updated_at = now
    await session.flush()
    return False


def failure_code(ctx: _ClaimedSummary, exc: Exception) -> str | None:
    if isinstance(exc, SummaryGenerationError):
        return exc.code
    return "INTERNAL_ERROR"


async def apply_failure(
    ctx: _ClaimedSummary,
    session: AsyncSession,
    job: ProcessingJob,
    record: Record | None,
    error_code: str,
    now: datetime,
) -> bool:
    del session
    if record is None:
        return False
    mark_failed(
        job,
        code=error_code,
        message=(
            "总结调整失败，上一版仍可确认"
            if ctx.base_summary_id is not None
            else "总结生成失败，请检查 Provider 后重试"
        ),
        now=now,
    )
    if ctx.base_summary_id is not None:
        record.status = RecordStatus.SUMMARY_READY
    else:
        record.status = RecordStatus.FAILED
    record.updated_at = now
    return True


async def _flip_record_after_interrupt(
    session: AsyncSession, job: ProcessingJob, now: datetime
) -> None:
    if job.record_id is None:
        return
    record = await session.get(Record, job.record_id)
    if record is None or record.deleted_at is not None:
        return
    input_data = cast(dict[str, object], json.loads(job.input_json))
    if isinstance(input_data.get("base_summary_id"), str):
        record.status = RecordStatus.SUMMARY_READY
    else:
        record.status = RecordStatus.FAILED
    record.updated_at = now


def summary_spec(
    session_factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
    graph: CompiledStateGraph[SummaryState, SummaryRuntime, SummaryState, SummaryState],
    summary_model: SummaryModel,
    record_notifier: RecordInvalidationNotifier,
) -> WorkerSpec[LlmProviderConfig, _ClaimedSummary, tuple[SummaryContent, SummaryCallResult]]:
    async def recover() -> None:
        await recover_running_to_failed(
            session_factory,
            record_notifier,
            ProcessingJobType.SUMMARY,
            "总结生成被意外中断",
            on_job_recovered=_flip_record_after_interrupt,
        )

    def classify(_exc: Exception) -> LoopFailure:
        return LoopFailure(event="summary_worker_unexpected_failure")

    return WorkerSpec(
        name="summary_worker",
        job_type=ProcessingJobType.SUMMARY,
        interrupted_error_message="总结生成被意外中断",
        poll_interval=0.25,
        find_candidate=find_candidate,
        validate_claim=validate_claim,
        on_preempted=on_preempted,
        execute=lambda ctx, runtime: execute(ctx, runtime, session_factory, graph, summary_model),
        writeback=lambda ctx, result: writeback(ctx, result, session_factory),
        failure_code=failure_code,
        apply_failure=apply_failure,
        recover_interrupted=recover,
        classify_loop_error=classify,
        preflight=lambda: preflight(data_dir),
    )
