import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models.document import AiSummary, Quiz
from app.modules.course.models import Course
from app.modules.course.schemas import CourseStatus
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.schemas import ProcessingJobStatus, ProcessingJobType
from app.modules.record.models import LearningEvent, Record
from app.modules.settings import (
    LlmProviderConfig,
    llm_consent,
    llm_provider_fingerprint,
    load_llm_provider,
)
from app.schemas.document import AiSummaryStatus
from app.schemas.quiz import (
    QuizAction,
    QuizAnswerResult,
    QuizBlockedReason,
    QuizDifficulty,
    QuizGenerateRequest,
    QuizGenerationStatus,
    QuizLearningEventSourceType,
    QuizLearningEventType,
    QuizObjectiveAnswerRequest,
    QuizOut,
    QuizQuestionType,
    QuizReadOut,
    QuizSelfAssessmentRequest,
    QuizShortAnswerRequest,
)


def _quiz_out(item: Quiz) -> QuizOut:
    user_answer: int | str | list[int] | list[str] | None = None
    if item.user_answer_json is not None:
        raw_answer = cast(object, json.loads(item.user_answer_json))
        if isinstance(raw_answer, (int, str)):
            user_answer = raw_answer
        elif isinstance(raw_answer, list):
            values = cast(list[object], raw_answer)
            if all(isinstance(value, int) for value in values):
                user_answer = cast(list[int], values)
            elif all(isinstance(value, str) for value in values):
                user_answer = cast(list[str], values)
    answer_visible = (
        item.generation_status == QuizGenerationStatus.DRAFT or item.answered_at is not None
    )
    return QuizOut(
        id=item.id,
        record_id=item.record_id,
        batch_id=item.batch_id,
        generated_from_summary_id=item.generated_from_summary_id,
        generation_status=QuizGenerationStatus(item.generation_status),
        question_type=QuizQuestionType(item.question_type),
        stem=item.stem,
        options=cast(list[str], json.loads(item.options_json)),
        correct_answer=(
            cast(int | str | list[int] | list[list[str]], json.loads(item.correct_answer_json))
            if answer_visible
            else None
        ),
        explanation=item.explanation if answer_visible else None,
        difficulty=QuizDifficulty(item.difficulty),
        user_answer=user_answer,
        answer_result=QuizAnswerResult(item.answer_result) if item.answer_result else None,
        answered_at=item.answered_at,
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


async def _superseded_summary_exists(session: AsyncSession, record_id: str) -> bool:
    return (
        await session.scalars(
            select(AiSummary.id)
            .where(
                AiSummary.record_id == record_id,
                AiSummary.status == AiSummaryStatus.SUPERSEDED,
                AiSummary.deleted_at.is_(None),
            )
            .limit(1)
        )
    ).first() is not None


async def _active_job(session: AsyncSession, record_id: str) -> ProcessingJob | None:
    return (
        await session.scalars(
            select(ProcessingJob)
            .where(
                ProcessingJob.record_id == record_id,
                ProcessingJob.job_type == ProcessingJobType.QUIZ_GENERATION,
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
                ProcessingJob.job_type == ProcessingJobType.QUIZ_GENERATION,
                ProcessingJob.status == ProcessingJobStatus.FAILED,
            )
            .order_by(ProcessingJob.created_at.desc())
            .limit(1)
        )
    ).one_or_none()


async def _visible_items(
    session: AsyncSession,
    record_id: str,
    *,
    include_superseded: bool = False,
) -> list[Quiz]:
    statuses = (
        (
            QuizGenerationStatus.DRAFT,
            QuizGenerationStatus.ACTIVE,
            QuizGenerationStatus.SUPERSEDED,
        )
        if include_superseded
        else (QuizGenerationStatus.DRAFT, QuizGenerationStatus.ACTIVE)
    )
    return list(
        (
            await session.scalars(
                select(Quiz)
                .where(
                    Quiz.record_id == record_id,
                    Quiz.deleted_at.is_(None),
                    Quiz.generation_status.in_(statuses),
                )
                .order_by(Quiz.created_at)
            )
        ).all()
    )


async def _answerable_quiz(session: AsyncSession, record_id: str, quiz_id: str) -> Quiz:
    quiz = (
        await session.scalars(
            select(Quiz).where(
                Quiz.id == quiz_id,
                Quiz.record_id == record_id,
                Quiz.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    if quiz is None:
        raise HTTPException(status_code=404, detail="习题不存在或已删除")
    if quiz.generation_status != QuizGenerationStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="只有已采用批次的题可以作答")
    return quiz


def _answer_event(
    record: Record,
    quiz: Quiz,
    result: QuizAnswerResult,
    now: datetime,
) -> LearningEvent:
    return LearningEvent(
        id=str(uuid4()),
        course_id=record.course_id,
        record_id=record.id,
        concept_id=None,
        event_type=QuizLearningEventType.ANSWERED,
        source_type=QuizLearningEventSourceType.QUESTION,
        source_id=quiz.id,
        result=result,
        score=None,
        difficulty=quiz.difficulty,
        duration_ms=None,
        metadata_json=json.dumps(
            {
                "batch_id": quiz.batch_id,
                "question_type": quiz.question_type,
                "generated_from_summary_id": quiz.generated_from_summary_id,
            },
            separators=(",", ":"),
        ),
        idempotency_key=f"quiz-answered:{quiz.id}",
        schema_version=1,
        occurred_at=now,
        created_at=now,
    )


class QuizService:
    @staticmethod
    async def read(
        session: AsyncSession,
        data_dir: Path,
        record_id: str,
        *,
        include_superseded: bool = False,
    ) -> QuizReadOut:
        record = await _get_record(session, record_id)
        items = await _visible_items(
            session,
            record_id,
            include_superseded=include_superseded,
        )
        output = [_quiz_out(item) for item in items]
        active = await _active_job(session, record_id)
        if active is not None:
            return QuizReadOut(
                items=output,
                action_required=QuizAction.NONE,
                active_job_id=active.id,
            )

        course = await session.get(Course, record.course_id) if record.course_id else None
        if course is None or course.deleted_at is not None or course.status != CourseStatus.ACTIVE:
            return QuizReadOut(
                items=output,
                action_required=QuizAction.NONE,
                blocked_reason=QuizBlockedReason.COURSE_ARCHIVED,
            )
        summary = await _confirmed_summary(session, record_id)
        if summary is None:
            blocked = (
                QuizBlockedReason.SUMMARY_SUPERSEDED
                if await _superseded_summary_exists(session, record_id)
                else QuizBlockedReason.SUMMARY_NOT_CONFIRMED
            )
            return QuizReadOut(
                items=output,
                action_required=QuizAction.NONE,
                blocked_reason=blocked,
            )
        draft = next(
            (item for item in items if item.generation_status == QuizGenerationStatus.DRAFT),
            None,
        )
        if draft is not None and draft.batch_id is not None:
            if draft.generated_from_summary_id != summary.id:
                # 候选绑定的总结已被换代（转写编辑后确认了新总结），候选基于旧内容，
                # 读端点直接给出换代原因，引导丢弃后基于新总结重新生成。
                return QuizReadOut(
                    items=output,
                    action_required=QuizAction.NONE,
                    blocked_reason=QuizBlockedReason.SUMMARY_SUPERSEDED,
                )
            return QuizReadOut(
                items=output,
                action_required=QuizAction.ADOPT,
            )
        provider, consent_current = await _provider_state(data_dir)
        if provider is None or not provider.api_key:
            return QuizReadOut(
                items=output,
                action_required=QuizAction.NONE,
                blocked_reason=QuizBlockedReason.PROVIDER_NOT_CONFIGURED,
            )
        if not consent_current:
            return QuizReadOut(
                items=output,
                action_required=QuizAction.NONE,
                blocked_reason=QuizBlockedReason.CONSENT_REQUIRED,
            )
        failed = await _failed_job(session, record_id)
        return QuizReadOut(
            items=output,
            action_required=(QuizAction.RETRY if failed is not None else QuizAction.GENERATE),
        )

    @staticmethod
    async def submit(
        session: AsyncSession,
        data_dir: Path,
        record_id: str,
        body: QuizGenerateRequest,
    ) -> str:
        provider, consent_current = await _provider_state(data_dir)
        if provider is None or not provider.api_key:
            raise HTTPException(status_code=409, detail="请先配置 LLM Provider")
        if not consent_current:
            raise HTTPException(status_code=409, detail="请先同意外部 AI 处理")
        try:
            async with session.begin():
                record = await _get_record(session, record_id)
                course = await session.get(Course, record.course_id) if record.course_id else None
                if (
                    course is None
                    or course.deleted_at is not None
                    or course.status != CourseStatus.ACTIVE
                ):
                    raise HTTPException(status_code=409, detail="归档课程不能生成习题")
                summary = await _confirmed_summary(session, record_id)
                if summary is None:
                    raise HTTPException(status_code=409, detail="请先确认当前总结")
                if await _active_job(session, record_id) is not None:
                    raise HTTPException(status_code=409, detail="已有进行中的习题生成任务")
                if any(
                    item.generation_status == QuizGenerationStatus.DRAFT
                    for item in await _visible_items(session, record_id)
                ):
                    raise HTTPException(status_code=409, detail="已有待审阅的习题候选")

                input_json = _job_input_json(provider, summary, body)
                failed = await _failed_job(session, record_id)
                if failed is not None:
                    previous = cast(dict[str, object], json.loads(failed.input_json))
                    if previous.get("generated_from_summary_id") == summary.id:
                        _requeue_failed(failed, input_json)
                        return failed.id

                now = utcnow()
                job = _new_job(record_id, input_json=input_json, now=now)
                session.add(job)
                await session.flush()
                return job.id
        except IntegrityError:
            raise HTTPException(
                status_code=409,
                detail="已有进行中的习题生成任务",
            ) from None

    @staticmethod
    async def discard(
        session: AsyncSession,
        data_dir: Path,
        record_id: str,
        batch_id: str,
    ) -> QuizReadOut:
        async with session.begin():
            await _get_record(session, record_id)
            rows = await _batch_rows(session, record_id, batch_id, QuizGenerationStatus.DRAFT)
            if not rows:
                adopted = await _batch_rows(
                    session, record_id, batch_id, QuizGenerationStatus.ACTIVE
                )
                if adopted:
                    raise HTTPException(status_code=409, detail="批次已采用，不能丢弃")
                raise HTTPException(status_code=404, detail="习题批次不存在")
            now = utcnow()
            for row in rows:
                row.deleted_at = now
                row.updated_at = now
        return await QuizService.read(session, data_dir, record_id)

    @staticmethod
    async def adopt(
        session: AsyncSession,
        data_dir: Path,
        record_id: str,
        batch_id: str,
    ) -> QuizReadOut:
        try:
            async with session.begin():
                record = await _get_record(session, record_id)
                draft_rows = await _batch_rows(
                    session,
                    record_id,
                    batch_id,
                    QuizGenerationStatus.DRAFT,
                )
                if not draft_rows:
                    if await _batch_rows(
                        session,
                        record_id,
                        batch_id,
                        QuizGenerationStatus.ACTIVE,
                    ):
                        return await QuizService.read(session, data_dir, record_id)
                    if await _batch_rows(
                        session,
                        record_id,
                        batch_id,
                        QuizGenerationStatus.SUPERSEDED,
                    ):
                        raise HTTPException(status_code=409, detail="习题批次已被新批次替代")
                    raise HTTPException(status_code=404, detail="习题批次不存在")

                summary_id = draft_rows[0].generated_from_summary_id
                summary = await session.get(AiSummary, summary_id) if summary_id else None
                if (
                    summary is None
                    or summary.deleted_at is not None
                    or summary.status != AiSummaryStatus.CONFIRMED
                ):
                    raise QuizAdoptionBlocked(
                        QuizBlockedReason.SUMMARY_SUPERSEDED,
                        "总结已换代，请丢弃当前候选后重新生成",
                    )
                course = await session.get(Course, record.course_id) if record.course_id else None
                if (
                    course is None
                    or course.deleted_at is not None
                    or course.status != CourseStatus.ACTIVE
                ):
                    raise QuizAdoptionBlocked(
                        QuizBlockedReason.COURSE_ARCHIVED,
                        "课程已归档，不能采用习题候选",
                    )

                now = utcnow()
                await session.execute(
                    update(Quiz)
                    .where(
                        Quiz.record_id == record_id,
                        Quiz.batch_id != batch_id,
                        Quiz.generation_status == QuizGenerationStatus.ACTIVE,
                        Quiz.deleted_at.is_(None),
                    )
                    .values(
                        generation_status=QuizGenerationStatus.SUPERSEDED,
                        updated_at=now,
                    )
                )
                await session.execute(
                    update(Quiz)
                    .where(
                        Quiz.record_id == record_id,
                        Quiz.batch_id == batch_id,
                        Quiz.generation_status == QuizGenerationStatus.DRAFT,
                        Quiz.deleted_at.is_(None),
                    )
                    .values(
                        generation_status=QuizGenerationStatus.ACTIVE,
                        updated_at=now,
                    )
                )
        except IntegrityError:
            # 同一批并发采用时，数据库约束胜出的一方已提交；返回当前事实。
            if not await _batch_rows(
                session,
                record_id,
                batch_id,
                QuizGenerationStatus.ACTIVE,
            ):
                raise
        return await QuizService.read(session, data_dir, record_id)

    @staticmethod
    async def answer_objective(
        session: AsyncSession,
        record_id: str,
        quiz_id: str,
        body: QuizObjectiveAnswerRequest,
    ) -> tuple[QuizOut, bool]:
        async with session.begin():
            record = await _get_record(session, record_id)
            quiz = await _answerable_quiz(session, record_id, quiz_id)
            if quiz.question_type not in (
                QuizQuestionType.MULTIPLE_CHOICE,
                QuizQuestionType.MULTIPLE_SELECT,
                QuizQuestionType.TRUE_FALSE,
                QuizQuestionType.FILL_BLANK,
            ):
                raise HTTPException(status_code=409, detail="该题不是客观题")
            options = cast(list[str], json.loads(quiz.options_json))
            answer = body.answer
            correct_answer = cast(object, json.loads(quiz.correct_answer_json))
            if quiz.question_type in (
                QuizQuestionType.MULTIPLE_CHOICE,
                QuizQuestionType.TRUE_FALSE,
            ):
                if not isinstance(answer, int) or not isinstance(correct_answer, int):
                    raise HTTPException(status_code=409, detail="该题需要提交一个选项")
                if answer >= len(options):
                    raise HTTPException(status_code=400, detail="所选答案下标超出选项范围")
                answer_result = (
                    QuizAnswerResult.CORRECT if answer == correct_answer else QuizAnswerResult.WRONG
                )
            elif quiz.question_type == QuizQuestionType.MULTIPLE_SELECT:
                correct_values = (
                    cast(list[object], correct_answer) if isinstance(correct_answer, list) else []
                )
                if (
                    not isinstance(answer, list)
                    or not all(isinstance(value, int) for value in answer)
                    or not correct_values
                    or not all(isinstance(value, int) for value in correct_values)
                ):
                    raise HTTPException(status_code=409, detail="该题需要提交选项组合")
                selected = cast(list[int], answer)
                expected = cast(list[int], correct_values)
                if any(value >= len(options) for value in selected):
                    raise HTTPException(status_code=400, detail="所选答案下标超出选项范围")
                answer = sorted(selected)
                answer_result = (
                    QuizAnswerResult.CORRECT
                    if answer == sorted(expected)
                    else QuizAnswerResult.WRONG
                )
            else:
                correct_values = (
                    cast(list[object], correct_answer) if isinstance(correct_answer, list) else []
                )
                if (
                    not isinstance(answer, list)
                    or not all(isinstance(value, str) for value in answer)
                    or not correct_values
                    or not all(isinstance(value, list) for value in correct_values)
                ):
                    raise HTTPException(status_code=409, detail="该题需要提交逐空答案")
                filled = cast(list[str], answer)
                expected_blanks = cast(list[list[str]], correct_values)
                if len(filled) != len(expected_blanks):
                    raise HTTPException(status_code=400, detail="填空题作答数量与空位不一致")
                answer = [value.strip() for value in filled]
                answer_result = (
                    QuizAnswerResult.CORRECT
                    if all(value in expected_blanks[index] for index, value in enumerate(answer))
                    else QuizAnswerResult.WRONG
                )
            if quiz.answered_at is not None:
                return _quiz_out(quiz), False
            if record.course_id is None:
                raise HTTPException(status_code=409, detail="学习记录缺少课程归属，不能作答")

            now = utcnow()
            updated = await session.execute(
                update(Quiz)
                .where(
                    Quiz.id == quiz_id,
                    Quiz.generation_status == QuizGenerationStatus.ACTIVE,
                    Quiz.answered_at.is_(None),
                )
                .values(
                    user_answer_json=json.dumps(answer, ensure_ascii=False, separators=(",", ":")),
                    answer_result=answer_result,
                    answered_at=now,
                    updated_at=now,
                )
            )
            if not isinstance(updated, CursorResult) or updated.rowcount != 1:
                await session.refresh(quiz)
                if quiz.generation_status != QuizGenerationStatus.ACTIVE:
                    raise HTTPException(status_code=409, detail="只有已采用批次的题可以作答")
                return _quiz_out(quiz), False

            session.add(_answer_event(record, quiz, answer_result, now))
            await session.flush()
            return _quiz_out(quiz), True

    @staticmethod
    async def answer_short(
        session: AsyncSession,
        record_id: str,
        quiz_id: str,
        body: QuizShortAnswerRequest,
    ) -> tuple[QuizOut, bool]:
        async with session.begin():
            await _get_record(session, record_id)
            quiz = await _answerable_quiz(session, record_id, quiz_id)
            if quiz.question_type != QuizQuestionType.SHORT_ANSWER:
                raise HTTPException(status_code=409, detail="该题不是简答题")
            if quiz.answered_at is not None:
                return _quiz_out(quiz), False

            now = utcnow()
            updated = await session.execute(
                update(Quiz)
                .where(
                    Quiz.id == quiz_id,
                    Quiz.generation_status == QuizGenerationStatus.ACTIVE,
                    Quiz.answered_at.is_(None),
                )
                .values(
                    user_answer_json=json.dumps(body.answer, ensure_ascii=False),
                    answered_at=now,
                    updated_at=now,
                )
            )
            if not isinstance(updated, CursorResult) or updated.rowcount != 1:
                await session.refresh(quiz)
                if quiz.generation_status != QuizGenerationStatus.ACTIVE:
                    raise HTTPException(status_code=409, detail="只有已采用批次的题可以作答")
                return _quiz_out(quiz), False

            await session.refresh(quiz)
            return _quiz_out(quiz), True

    @staticmethod
    async def self_assess_short(
        session: AsyncSession,
        record_id: str,
        quiz_id: str,
        body: QuizSelfAssessmentRequest,
    ) -> tuple[QuizOut, bool]:
        async with session.begin():
            record = await _get_record(session, record_id)
            quiz = await _answerable_quiz(session, record_id, quiz_id)
            if quiz.question_type != QuizQuestionType.SHORT_ANSWER:
                raise HTTPException(status_code=409, detail="该题不是简答题")
            if quiz.answered_at is None:
                raise HTTPException(status_code=409, detail="请先提交简答作答")
            if quiz.answer_result is not None:
                return _quiz_out(quiz), False
            if record.course_id is None:
                raise HTTPException(status_code=409, detail="学习记录缺少课程归属，不能作答")

            now = utcnow()
            updated = await session.execute(
                update(Quiz)
                .where(
                    Quiz.id == quiz_id,
                    Quiz.generation_status == QuizGenerationStatus.ACTIVE,
                    Quiz.answered_at.is_not(None),
                    Quiz.answer_result.is_(None),
                )
                .values(answer_result=body.result, updated_at=now)
            )
            if not isinstance(updated, CursorResult) or updated.rowcount != 1:
                await session.refresh(quiz)
                if quiz.generation_status != QuizGenerationStatus.ACTIVE:
                    raise HTTPException(status_code=409, detail="只有已采用批次的题可以作答")
                return _quiz_out(quiz), False

            session.add(_answer_event(record, quiz, body.result, now))
            await session.flush()
            await session.refresh(quiz)
            return _quiz_out(quiz), True


class QuizAdoptionBlocked(Exception):
    def __init__(self, blocked_reason: QuizBlockedReason, detail: str) -> None:
        super().__init__(detail)
        self.blocked_reason = blocked_reason
        self.detail = detail


async def _batch_rows(
    session: AsyncSession,
    record_id: str,
    batch_id: str,
    status: QuizGenerationStatus,
) -> list[Quiz]:
    return list(
        (
            await session.scalars(
                select(Quiz)
                .where(
                    Quiz.record_id == record_id,
                    Quiz.batch_id == batch_id,
                    Quiz.generation_status == status,
                    Quiz.deleted_at.is_(None),
                )
                .order_by(Quiz.created_at)
            )
        ).all()
    )


def _job_input_json(
    provider: LlmProviderConfig,
    summary: AiSummary,
    body: QuizGenerateRequest,
) -> str:
    return json.dumps(
        {
            "provider_fingerprint": llm_provider_fingerprint(provider),
            "generated_from_summary_id": summary.id,
            "question_types": [item.value for item in body.question_types],
            "total_count": body.total_count,
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
        job_type=ProcessingJobType.QUIZ_GENERATION,
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
