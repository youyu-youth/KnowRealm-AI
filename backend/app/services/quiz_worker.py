"""习题生成执行体描述（任务循环骨架见 job_runner.py，ADR-0012）。"""

import asyncio
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.llm import (
    QuizModel,
    StructuredGenerationError,
    call_quiz_model,
)
from app.models.base import utcnow
from app.models.course import Course
from app.models.document import AiSummary, ProcessingJob, Quiz
from app.models.record import Record
from app.schemas.document import ProcessingJobStatus, ProcessingJobType
from app.schemas.quiz import (
    QuizBatch,
    QuizGenerationStatus,
    QuizQuestionType,
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

PROMPT_VERSION = "quiz_v1"

_QUESTION_TYPE_LABELS = {
    QuizQuestionType.MULTIPLE_CHOICE: "选择题",
    QuizQuestionType.TRUE_FALSE: "判断题",
    QuizQuestionType.SHORT_ANSWER: "简答题",
}


@dataclass(frozen=True)
class _ClaimedQuizJob(ClaimedJob):
    summary_id: str
    question_types: tuple[QuizQuestionType, ...]
    total_count: int
    summary: SummaryContent
    course: Course
    provider: LlmProviderConfig


def build_quiz_prompt(claimed: _ClaimedQuizJob) -> str:
    sections = "\n".join(
        f"{section.heading}：" + "；".join(section.points) for section in claimed.summary.sections
    )
    type_names = "、".join(_QUESTION_TYPE_LABELS[item] for item in claimed.question_types)
    return (
        "请根据以下课程上下文和已确认总结出中文练习题。"
        "严格返回指定结构，不添加结构外字段。\n"
        f"学习场景：{claimed.course.learning_context}\n"
        f"教育阶段：{claimed.course.education_stage or '未设置'}\n"
        f"内容深度：{claimed.course.depth or '未设置'}\n"
        "已确认总结：\n"
        f"主题：{claimed.summary.topic}\n"
        f"摘要：{claimed.summary.abstract}\n"
        f"{sections}\n"
        "出题要求：\n"
        f"- 恰好出 {claimed.total_count} 题，题型限定：{type_names}，每种所选题型至少 1 道，"
        "各题型数量构成由你按内容决定\n"
        "- 选择题为单选题：options 为 3 至 5 个选项文本，"
        "correct_answer 为正确选项的下标（从 0 开始）\n"
        '- 判断题：options 固定为 ["对", "错"]，correct_answer 为 0（对）或 1（错）\n'
        "- 简答题：options 为空数组，correct_answer 为参考答案文本\n"
        "- 每题给出 difficulty（EASY / MEDIUM / HARD）与 explanation 解析\n"
        "- 题目与解析只能基于已确认总结的内容，不得引入总结之外的知识"
    )


def validate_quiz_composition(
    batch: QuizBatch,
    *,
    question_types: tuple[QuizQuestionType, ...],
    total_count: int,
) -> None:
    """批次级校验依赖请求参数，在 Schema 之外执行；违规按 LLM_OUTPUT_INVALID 失败。"""
    if len(batch.items) != total_count:
        raise StructuredGenerationError("LLM_OUTPUT_INVALID")
    counts = Counter(QuizQuestionType(item.question_type) for item in batch.items)
    # 总数严格按档位；所选题型各 ≥1 且不混入未选题型（用户勾选须被如实兑现）。
    if set(counts) - set(question_types) or any(counts.get(item, 0) < 1 for item in question_types):
        raise StructuredGenerationError("LLM_OUTPUT_INVALID")


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
                ProcessingJob.job_type == ProcessingJobType.QUIZ_GENERATION,
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
) -> ClaimCheck[_ClaimedQuizJob]:
    current_provider = cast(LlmProviderConfig, provider)  # preflight 通过时必非 None
    record = await session.get(Record, record_id)
    input_data = cast(dict[str, object], json.loads(job.input_json))
    summary_id = input_data.get("generated_from_summary_id")
    raw_total_count = input_data.get("total_count")
    summary = await session.get(AiSummary, summary_id) if isinstance(summary_id, str) else None
    course = await session.get(Course, record.course_id) if record and record.course_id else None
    try:
        question_types = tuple(
            QuizQuestionType(value)
            for value in cast(list[object], input_data.get("question_types"))
        )
    except ValueError:
        question_types = ()
    if (
        not question_types
        or not isinstance(raw_total_count, int)
        or not summary_source_is_current(record, course, summary, record_id=record_id)
        or input_data.get("provider_fingerprint") != llm_provider_fingerprint(current_provider)
    ):
        return CancelClaim(PREREQUISITE_CHANGED)
    current_summary = cast(AiSummary, summary)
    return Ready(
        _ClaimedQuizJob(
            job_id=job.id,
            record_id=record_id,
            summary_id=current_summary.id,
            question_types=question_types,
            total_count=raw_total_count,
            summary=summary_content(current_summary),
            course=cast(Course, course),
            provider=current_provider,
        )
    )


async def execute(
    ctx: _ClaimedQuizJob,
    session_factory: async_sessionmaker[AsyncSession],
    model: QuizModel,
) -> QuizBatch:
    call_result = await call_quiz_model(
        session_factory=session_factory,
        quiz_model=model,
        provider=ctx.provider,
        prompt=build_quiz_prompt(ctx),
        prompt_version=PROMPT_VERSION,
    )
    validate_quiz_composition(
        call_result.content,
        question_types=ctx.question_types,
        total_count=ctx.total_count,
    )
    return call_result.content


async def writeback(
    ctx: _ClaimedQuizJob,
    content: QuizBatch,
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
        for candidate in content.items:
            session.add(
                Quiz(
                    id=str(uuid4()),
                    record_id=ctx.record_id,
                    batch_id=ctx.job_id,
                    generated_from_summary_id=ctx.summary_id,
                    generation_status=QuizGenerationStatus.DRAFT,
                    question_type=candidate.question_type,
                    stem=candidate.stem,
                    options_json=json.dumps(
                        candidate.options, ensure_ascii=False, separators=(",", ":")
                    ),
                    correct_answer_json=json.dumps(
                        candidate.correct_answer, ensure_ascii=False, separators=(",", ":")
                    ),
                    explanation=candidate.explanation,
                    difficulty=candidate.difficulty,
                    user_answer_json=None,
                    answer_result=None,
                    answered_at=None,
                    created_at=now,
                    updated_at=now,
                    deleted_at=None,
                )
            )
        type_counts = Counter(item.question_type for item in content.items)
        job.status = ProcessingJobStatus.SUCCEEDED
        job.progress = 1
        job.result_json = json.dumps(
            {
                "model": ctx.provider.model,
                "prompt_version": PROMPT_VERSION,
                "question_count": len(content.items),
                "question_types": {
                    item.value: type_counts.get(item, 0) for item in ctx.question_types
                },
            },
            separators=(",", ":"),
        )
        job.error_code = None
        job.error_message = None
        job.finished_at = now
        job.updated_at = now
    return True


def failure_code(ctx: _ClaimedQuizJob, exc: Exception) -> str | None:
    if isinstance(exc, StructuredGenerationError):
        return exc.code
    return "INTERNAL_ERROR"


async def apply_failure(
    ctx: _ClaimedQuizJob,
    session: AsyncSession,
    job: ProcessingJob,
    record: Record | None,
    error_code: str,
    now: datetime,
) -> bool:
    del ctx, record, session  # quiz 域失败不触碰记录状态
    mark_failed(job, code=error_code, message="习题生成失败，请重试", now=now)
    return True


def quiz_spec(
    session_factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
    model: QuizModel,
    record_notifier: RecordInvalidationNotifier,
) -> WorkerSpec[LlmProviderConfig, _ClaimedQuizJob, QuizBatch]:
    async def recover() -> None:
        await recover_running_to_failed(
            session_factory,
            record_notifier,
            ProcessingJobType.QUIZ_GENERATION,
            "习题生成被意外中断",
        )

    def classify(_exc: Exception) -> LoopFailure:
        return LoopFailure(event="quiz_worker_unexpected_failure")

    return WorkerSpec(
        name="quiz_worker",
        job_type=ProcessingJobType.QUIZ_GENERATION,
        interrupted_error_message="习题生成被意外中断",
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
