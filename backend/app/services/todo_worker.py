"""Todo 生成执行体描述（任务循环骨架见 job_runner.py，ADR-0012）。"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.llm import StructuredGenerationError, TodoModel, call_todo_model
from app.models.base import utcnow
from app.models.course import Course
from app.models.document import AiSummary, ProcessingJob, TodoItem
from app.models.record import Record
from app.schemas.document import ProcessingJobStatus, ProcessingJobType
from app.schemas.summary import SummaryContent
from app.schemas.todo import TodoBatch, TodoGenerationStatus, TodoSource, TodoStatus
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

PROMPT_VERSION = "todo_v1"


@dataclass(frozen=True)
class _ClaimedTodoJob(ClaimedJob):
    summary_id: str
    summary: SummaryContent
    course: Course
    provider: LlmProviderConfig


def build_todo_prompt(claimed: _ClaimedTodoJob) -> str:
    sections = "\n".join(
        f"{section.heading}：" + "；".join(section.points) for section in claimed.summary.sections
    )
    return (
        "请根据以下课程上下文和已确认总结生成中文 Todo 建议。"
        "严格返回指定结构，不添加结构外字段。\n"
        f"学习场景：{claimed.course.learning_context}\n"
        f"教育阶段：{claimed.course.education_stage or '未设置'}\n"
        f"内容深度：{claimed.course.depth or '未设置'}\n"
        "已确认总结：\n"
        f"主题：{claimed.summary.topic}\n"
        f"摘要：{claimed.summary.abstract}\n{sections}\n"
        "生成 3 至 8 条具体、可执行且只基于总结内容的待办建议。"
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
                ProcessingJob.job_type == ProcessingJobType.TODO_GENERATION,
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
) -> ClaimCheck[_ClaimedTodoJob]:
    current_provider = cast(LlmProviderConfig, provider)  # preflight 通过时必非 None
    record = await session.get(Record, record_id)
    input_data = cast(dict[str, object], json.loads(job.input_json))
    summary_id = input_data.get("generated_from_summary_id")
    summary = await session.get(AiSummary, summary_id) if isinstance(summary_id, str) else None
    course = await session.get(Course, record.course_id) if record and record.course_id else None
    if not summary_source_is_current(
        record, course, summary, record_id=record_id
    ) or input_data.get("provider_fingerprint") != llm_provider_fingerprint(current_provider):
        return CancelClaim(PREREQUISITE_CHANGED)
    current_summary = cast(AiSummary, summary)
    return Ready(
        _ClaimedTodoJob(
            job_id=job.id,
            record_id=record_id,
            summary_id=current_summary.id,
            summary=summary_content(current_summary),
            course=cast(Course, course),
            provider=current_provider,
        )
    )


async def execute(
    ctx: _ClaimedTodoJob,
    session_factory: async_sessionmaker[AsyncSession],
    model: TodoModel,
) -> TodoBatch:
    result = await call_todo_model(
        session_factory=session_factory,
        todo_model=model,
        provider=ctx.provider,
        prompt=build_todo_prompt(ctx),
        prompt_version=PROMPT_VERSION,
    )
    return result.content


async def writeback(
    ctx: _ClaimedTodoJob,
    content: TodoBatch,
    session_factory: async_sessionmaker[AsyncSession],
) -> bool:
    now = utcnow()
    async with session_factory() as session, session.begin():
        job = await session.get(ProcessingJob, ctx.job_id)
        record = await session.get(Record, ctx.record_id)
        summary = await session.get(AiSummary, ctx.summary_id)
        course = (
            await session.get(Course, record.course_id) if record and record.course_id else None
        )
        if job is None or job.status != ProcessingJobStatus.RUNNING:
            return False
        if not summary_source_is_current(record, course, summary, record_id=ctx.record_id):
            job.status = ProcessingJobStatus.CANCELLED
            job.result_json = json.dumps({"reason": PREREQUISITE_CHANGED})
            job.finished_at = now
            job.updated_at = now
            return False
        max_order = await session.scalar(
            select(func.max(TodoItem.sort_order)).where(TodoItem.record_id == ctx.record_id)
        )
        start = (max_order if max_order is not None else -1) + 1
        for offset, candidate in enumerate(content.items):
            session.add(
                TodoItem(
                    id=str(uuid4()),
                    record_id=ctx.record_id,
                    batch_id=ctx.job_id,
                    content=candidate.content,
                    status=TodoStatus.TODO,
                    source=TodoSource.AI,
                    generated_from_summary_id=ctx.summary_id,
                    generation_status=TodoGenerationStatus.DRAFT,
                    sort_order=start + offset,
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
                "todo_count": len(content.items),
            },
            separators=(",", ":"),
        )
        job.error_code = None
        job.error_message = None
        job.finished_at = now
        job.updated_at = now
    return True


def failure_code(ctx: _ClaimedTodoJob, exc: Exception) -> str | None:
    if isinstance(exc, StructuredGenerationError):
        return exc.code
    return "INTERNAL_ERROR"


async def apply_failure(
    ctx: _ClaimedTodoJob,
    session: AsyncSession,
    job: ProcessingJob,
    record: Record | None,
    error_code: str,
    now: datetime,
) -> bool:
    del ctx, record, session  # todo 域失败不触碰记录状态
    mark_failed(job, code=error_code, message="Todo 生成失败，请重试", now=now)
    return True


def todo_spec(
    session_factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
    model: TodoModel,
    record_notifier: RecordInvalidationNotifier,
) -> WorkerSpec[LlmProviderConfig, _ClaimedTodoJob, TodoBatch]:
    async def recover() -> None:
        await recover_running_to_failed(
            session_factory,
            record_notifier,
            ProcessingJobType.TODO_GENERATION,
            "Todo 生成被意外中断",
        )

    def classify(_exc: Exception) -> LoopFailure:
        return LoopFailure(event="todo_worker_unexpected_failure")

    return WorkerSpec(
        name="todo_worker",
        job_type=ProcessingJobType.TODO_GENERATION,
        interrupted_error_message="Todo 生成被意外中断",
        poll_interval=0.25,
        find_candidate=find_candidate,
        validate_claim=validate_claim,
        execute=lambda ctx: execute(ctx, session_factory, model),
        writeback=lambda ctx, content: writeback(ctx, content, session_factory),
        failure_code=failure_code,
        apply_failure=apply_failure,
        recover_interrupted=recover,
        classify_loop_error=classify,
        preflight=lambda: preflight(data_dir),
    )
