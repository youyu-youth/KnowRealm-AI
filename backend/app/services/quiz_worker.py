import asyncio
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import uuid4

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
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
from app.schemas.course import CourseStatus
from app.schemas.document import AiSummaryStatus, ProcessingJobStatus, ProcessingJobType
from app.schemas.quiz import (
    QuizBatch,
    QuizGenerationStatus,
    QuizQuestionType,
)
from app.schemas.summary import SummaryContent
from app.services.local_config import (
    LlmProviderConfig,
    llm_consent,
    llm_provider_fingerprint,
    load_llm_provider,
)
from app.services.record_invalidation import RecordInvalidationNotifier

PROMPT_VERSION = "quiz_v1"

_QUESTION_TYPE_LABELS = {
    QuizQuestionType.MULTIPLE_CHOICE: "选择题",
    QuizQuestionType.TRUE_FALSE: "判断题",
    QuizQuestionType.SHORT_ANSWER: "简答题",
}


@dataclass(frozen=True)
class _ClaimedQuizJob:
    job_id: str
    record_id: str
    summary_id: str
    question_types: tuple[QuizQuestionType, ...]
    total_count: int
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


def _source_is_current(
    record: Record | None,
    course: Course | None,
    summary: AiSummary | None,
    *,
    record_id: str,
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
    )


class QuizWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
        model: QuizModel,
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
                            ProcessingJob.job_type == ProcessingJobType.QUIZ_GENERATION,
                            ProcessingJob.status == ProcessingJobStatus.RUNNING,
                        )
                    )
                ).all()
            )
            for job in jobs:
                job.status = ProcessingJobStatus.FAILED
                job.error_code = "WORKER_INTERRUPTED"
                job.error_message = "习题生成被意外中断"
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
                    "quiz_worker_unexpected_failure",
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
            call_result = await call_quiz_model(
                session_factory=self._session_factory,
                quiz_model=self._model,
                provider=claimed.provider,
                prompt=build_quiz_prompt(claimed),
                prompt_version=PROMPT_VERSION,
            )
            validate_quiz_composition(
                call_result.content,
                question_types=claimed.question_types,
                total_count=claimed.total_count,
            )
        except StructuredGenerationError as exc:
            await self._fail(claimed, exc.code)
        except Exception:
            await self._fail(claimed, "INTERNAL_ERROR")
        else:
            await self._publish(claimed, call_result.content)
        return True

    async def _claim_one(self) -> _ClaimedQuizJob | None:
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
                        ProcessingJob.job_type == ProcessingJobType.QUIZ_GENERATION,
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
            raw_total_count = input_data.get("total_count")
            summary = (
                await session.get(AiSummary, summary_id) if isinstance(summary_id, str) else None
            )
            course = (
                await session.get(Course, record.course_id) if record and record.course_id else None
            )
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
                or not _source_is_current(
                    record,
                    course,
                    summary,
                    record_id=job.record_id,
                )
                or input_data.get("provider_fingerprint") != llm_provider_fingerprint(provider)
            ):
                job.status = ProcessingJobStatus.CANCELLED
                job.result_json = json.dumps({"reason": "PREREQUISITE_CHANGED"})
                job.finished_at = now
                job.updated_at = now
                return None
            current_summary = cast(AiSummary, summary)
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
            return _ClaimedQuizJob(
                job_id=job.id,
                record_id=job.record_id,
                summary_id=current_summary.id,
                question_types=question_types,
                total_count=raw_total_count,
                summary=_summary_content(current_summary),
                course=current_course,
                provider=provider,
            )

    async def _publish(self, claimed: _ClaimedQuizJob, content: QuizBatch) -> None:
        now = utcnow()
        async with self._session_factory() as session, session.begin():
            job = await session.get(ProcessingJob, claimed.job_id)
            record = await session.get(Record, claimed.record_id)
            summary = await session.get(AiSummary, claimed.summary_id)
            course = (
                await session.get(Course, record.course_id) if record and record.course_id else None
            )
            if job is None or job.status != ProcessingJobStatus.RUNNING:
                return
            if not _source_is_current(
                record,
                course,
                summary,
                record_id=claimed.record_id,
            ):
                job.status = ProcessingJobStatus.CANCELLED
                job.result_json = json.dumps({"reason": "PREREQUISITE_CHANGED"})
                job.finished_at = now
                job.updated_at = now
                return
            for candidate in content.items:
                session.add(
                    Quiz(
                        id=str(uuid4()),
                        record_id=claimed.record_id,
                        batch_id=claimed.job_id,
                        generated_from_summary_id=claimed.summary_id,
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
                    "model": claimed.provider.model,
                    "prompt_version": PROMPT_VERSION,
                    "question_count": len(content.items),
                    "question_types": {
                        item.value: type_counts.get(item, 0) for item in claimed.question_types
                    },
                },
                separators=(",", ":"),
            )
            job.error_code = None
            job.error_message = None
            job.finished_at = now
            job.updated_at = now
        await self._record_notifier.notify(claimed.record_id)

    async def _fail(self, claimed: _ClaimedQuizJob, error_code: str) -> None:
        now = utcnow()
        async with self._session_factory() as session, session.begin():
            job = await session.get(ProcessingJob, claimed.job_id)
            if job is None or job.status != ProcessingJobStatus.RUNNING:
                return
            job.status = ProcessingJobStatus.FAILED
            job.error_code = error_code
            job.error_message = "习题生成失败，请重试"
            job.finished_at = now
            job.updated_at = now
        await self._record_notifier.notify(claimed.record_id)
