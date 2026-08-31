import json
from datetime import datetime
from typing import cast
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import and_, func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utcnow
from app.models.course import Course
from app.models.document import LearningEvent, Quiz, QuizTest, QuizTestItem
from app.models.record import Record
from app.schemas.course import CourseStatus
from app.schemas.quiz import (
    QuizDifficulty,
    QuizGenerationStatus,
    QuizLearningEventSourceType,
    QuizLearningEventType,
    QuizQuestionType,
)
from app.schemas.quiz_test import (
    QuizTestAnswerRequest,
    QuizTestBlockedReason,
    QuizTestCreateOut,
    QuizTestCreateRequest,
    QuizTestDetailOut,
    QuizTestItemOut,
    QuizTestItemResult,
    QuizTestListOut,
    QuizTestMode,
    QuizTestStatus,
    QuizTestSummaryOut,
)


def _decode_json(value: str | None) -> object | None:
    return json.loads(value) if value is not None else None


def _summary_out(test: QuizTest, total_count: int, answered_count: int) -> QuizTestSummaryOut:
    return QuizTestSummaryOut(
        id=test.id,
        course_id=test.course_id,
        record_id=None,
        mode=QuizTestMode(test.mode),
        status=QuizTestStatus(test.status),
        score=test.score,
        total_count=total_count,
        answered_count=answered_count,
        started_at=test.started_at,
        completed_at=test.completed_at,
        created_at=test.created_at,
        updated_at=test.updated_at,
    )


async def _course(session: AsyncSession, course_id: str) -> Course:
    course = (
        await session.scalars(
            select(Course).where(Course.id == course_id, Course.deleted_at.is_(None))
        )
    ).one_or_none()
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在或已删除")
    return course


class QuizTestService:
    @staticmethod
    async def create(
        session: AsyncSession,
        course_id: str,
        body: QuizTestCreateRequest,
    ) -> QuizTestCreateOut:
        async with session.begin():
            course = await _course(session, course_id)
            if course.status != CourseStatus.ACTIVE:
                raise QuizTestBlocked(
                    "已归档课程不能开始模拟测试",
                    QuizTestBlockedReason.COURSE_ARCHIVED,
                )
            quizzes = list(
                (
                    await session.scalars(
                        select(Quiz)
                        .join(Record, Record.id == Quiz.record_id)
                        .where(
                            Record.course_id == course_id,
                            Record.deleted_at.is_(None),
                            Quiz.deleted_at.is_(None),
                            Quiz.generation_status == QuizGenerationStatus.ACTIVE,
                            Quiz.question_type.in_(body.question_types),
                        )
                        .order_by(func.random())
                        .limit(body.total_count)
                    )
                ).all()
            )
            if not quizzes:
                raise HTTPException(status_code=409, detail="课程题库暂无可用习题")

            test = QuizTest(
                id=str(uuid4()),
                course_id=course_id,
                record_id=None,
                mode=QuizTestMode.MOCK,
                status=QuizTestStatus.IN_PROGRESS,
            )
            session.add(test)
            await session.flush()
            session.add_all(
                QuizTestItem(
                    id=str(uuid4()),
                    test_id=test.id,
                    quiz_id=quiz.id,
                    sequence_no=sequence_no,
                )
                for sequence_no, quiz in enumerate(quizzes, 1)
            )
            await session.flush()
            summary = _summary_out(test, len(quizzes), 0)

        return QuizTestCreateOut(
            test=summary,
            requested_count=body.total_count,
            selected_count=len(quizzes),
            shortage=len(quizzes) < body.total_count,
        )

    @staticmethod
    async def list_for_course(session: AsyncSession, course_id: str) -> QuizTestListOut:
        course = await _course(session, course_id)
        if course.status != CourseStatus.ACTIVE:
            return QuizTestListOut(items=[], blocked_reason=QuizTestBlockedReason.COURSE_ARCHIVED)
        available_quiz = await session.scalar(
            select(Quiz.id)
            .join(Record, Record.id == Quiz.record_id)
            .where(
                Record.course_id == course_id,
                Record.deleted_at.is_(None),
                Quiz.deleted_at.is_(None),
                Quiz.generation_status == QuizGenerationStatus.ACTIVE,
            )
            .limit(1)
        )
        rows = (
            await session.execute(
                select(
                    QuizTest,
                    func.count(QuizTestItem.id),
                    func.count(QuizTestItem.answered_at),
                )
                .outerjoin(
                    QuizTestItem,
                    and_(
                        QuizTestItem.test_id == QuizTest.id,
                        QuizTestItem.deleted_at.is_(None),
                    ),
                )
                .where(QuizTest.course_id == course_id, QuizTest.deleted_at.is_(None))
                .group_by(QuizTest.id)
                .order_by(QuizTest.created_at.desc())
            )
        ).all()
        return QuizTestListOut(
            items=[
                _summary_out(test, cast(int, total), cast(int, answered))
                for test, total, answered in rows
            ],
            blocked_reason=(
                QuizTestBlockedReason.NO_AVAILABLE_QUIZZES if available_quiz is None else None
            ),
        )

    @staticmethod
    async def get(session: AsyncSession, test_id: str) -> QuizTestDetailOut | None:
        row = (
            await session.execute(
                select(QuizTest, Course.status)
                .join(Course, Course.id == QuizTest.course_id)
                .where(
                    QuizTest.id == test_id,
                    QuizTest.deleted_at.is_(None),
                    Course.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        if row is None:
            return None
        test, course_status = row
        if course_status != CourseStatus.ACTIVE:
            raise QuizTestBlocked(
                "已归档课程不能查看模拟测试",
                QuizTestBlockedReason.COURSE_ARCHIVED,
            )
        return await _detail_out(session, test)

    @staticmethod
    async def answer_item(
        session: AsyncSession,
        test_id: str,
        body: QuizTestAnswerRequest,
    ) -> QuizTestDetailOut:
        async with session.begin():
            test = await _test(session, test_id)
            await _ensure_course_active(session, test, "已归档课程的模拟测试不能再作答")
            if test.status != QuizTestStatus.IN_PROGRESS:
                raise HTTPException(status_code=409, detail="该测试已交卷或已放弃，不能再作答")
            item = (
                await session.scalars(
                    select(QuizTestItem).where(
                        QuizTestItem.id == body.item_id,
                        QuizTestItem.test_id == test_id,
                        QuizTestItem.deleted_at.is_(None),
                    )
                )
            ).one_or_none()
            if item is None:
                raise HTTPException(status_code=404, detail="试卷题目不存在")
            quiz = await _item_quiz(session, item)
            if item.answered_at is None:
                await _grade_and_record(session, test, item, quiz, body.answer)
            return await _detail_out(session, test)

    @staticmethod
    async def abandon(session: AsyncSession, test_id: str) -> QuizTestSummaryOut:
        async with session.begin():
            test = await _test(session, test_id)
            await _ensure_course_active(session, test, "已归档课程的模拟测试不能再放弃")
            if test.status != QuizTestStatus.IN_PROGRESS:
                raise HTTPException(status_code=409, detail="只有进行中的测试可以放弃")
            now = utcnow()
            test.status = QuizTestStatus.ABANDONED
            test.updated_at = now
            await session.flush()
            total, answered = await _item_counts(session, test_id)
            return _summary_out(test, total, answered)


class QuizTestBlocked(Exception):
    def __init__(self, detail: str, blocked_reason: QuizTestBlockedReason) -> None:
        super().__init__(detail)
        self.detail = detail
        self.blocked_reason = blocked_reason


async def _test(session: AsyncSession, test_id: str) -> QuizTest:
    test = (
        await session.scalars(
            select(QuizTest).where(QuizTest.id == test_id, QuizTest.deleted_at.is_(None))
        )
    ).one_or_none()
    if test is None:
        raise HTTPException(status_code=404, detail="模拟测试不存在")
    return test


async def _ensure_course_active(
    session: AsyncSession,
    test: QuizTest,
    detail: str,
) -> None:
    """归档课程护栏：作答/放弃与读卷面同样拦在 ACTIVE 之外。"""
    status = await session.scalar(select(Course.status).where(Course.id == test.course_id))
    if status != CourseStatus.ACTIVE:
        raise HTTPException(status_code=409, detail=detail)


async def _item_quiz(session: AsyncSession, item: QuizTestItem) -> Quiz:
    quiz = await session.get(Quiz, item.quiz_id)
    if quiz is None or quiz.deleted_at is not None:
        raise HTTPException(status_code=404, detail="试卷题目不存在")
    return quiz


async def _item_counts(session: AsyncSession, test_id: str) -> tuple[int, int]:
    row = (
        await session.execute(
            select(func.count(QuizTestItem.id), func.count(QuizTestItem.answered_at)).where(
                QuizTestItem.test_id == test_id,
                QuizTestItem.deleted_at.is_(None),
            )
        )
    ).one()
    return cast(int, row[0]), cast(int, row[1])


async def _detail_out(session: AsyncSession, test: QuizTest) -> QuizTestDetailOut:
    rows = (
        await session.execute(
            select(QuizTestItem, Quiz)
            .join(Quiz, Quiz.id == QuizTestItem.quiz_id)
            .where(
                QuizTestItem.test_id == test.id,
                QuizTestItem.deleted_at.is_(None),
            )
            .order_by(QuizTestItem.sequence_no)
        )
    ).all()
    items = [_item_out(item, quiz) for item, quiz in rows]
    summary = _summary_out(test, len(items), sum(item.answered_at is not None for item in items))
    return QuizTestDetailOut(**summary.model_dump(), items=items)


def _item_out(item: QuizTestItem, quiz: Quiz) -> QuizTestItemOut:
    return QuizTestItemOut(
        id=item.id,
        quiz_id=item.quiz_id,
        sequence_no=item.sequence_no,
        question_type=QuizQuestionType(quiz.question_type),
        stem=quiz.stem,
        options=cast(list[str], json.loads(quiz.options_json)),
        difficulty=QuizDifficulty(quiz.difficulty),
        user_answer=cast(
            int | str | list[int] | list[str] | None,
            _decode_json(item.user_answer_json),
        ),
        result=QuizTestItemResult(item.result) if item.result is not None else None,
        score=item.score,
        answered_at=item.answered_at,
    )


def _grade_objective(
    quiz: Quiz,
    answer: object,
) -> tuple[QuizTestItemResult, float, int | list[int] | list[str]]:
    """客观题判分：多选全对才得分；填空逐空判分，部分空对=PARTIAL 按空比例计分。

    返回值第三项为规范化后的落库作答（填空逐空去首尾空白）。
    """
    question_type = QuizQuestionType(quiz.question_type)
    options = cast(list[str], json.loads(quiz.options_json))
    correct = cast(object, json.loads(quiz.correct_answer_json))
    if question_type in (QuizQuestionType.MULTIPLE_CHOICE, QuizQuestionType.TRUE_FALSE):
        if not isinstance(answer, int) or not isinstance(correct, int):
            raise HTTPException(status_code=409, detail="该题需要提交一个选项")
        if answer >= len(options):
            raise HTTPException(status_code=400, detail="所选答案下标超出选项范围")
        result = QuizTestItemResult.CORRECT if answer == correct else QuizTestItemResult.WRONG
        return result, 1.0 if result is QuizTestItemResult.CORRECT else 0.0, answer
    if question_type is QuizQuestionType.MULTIPLE_SELECT:
        selected = cast("list[object]", answer if isinstance(answer, list) else [])
        expected = cast("list[object]", correct if isinstance(correct, list) else [])
        if (
            not all(isinstance(value, int) for value in selected)
            or not expected
            or not all(isinstance(value, int) for value in expected)
        ):
            raise HTTPException(status_code=409, detail="该题需要提交选项组合")
        chosen = sorted(cast(list[int], selected))
        wanted = sorted(cast(list[int], expected))
        if any(value >= len(options) for value in chosen):
            raise HTTPException(status_code=400, detail="所选答案下标超出选项范围")
        result = QuizTestItemResult.CORRECT if chosen == wanted else QuizTestItemResult.WRONG
        return result, 1.0 if result is QuizTestItemResult.CORRECT else 0.0, chosen
    filled = cast("list[object]", answer if isinstance(answer, list) else [])
    expected_blanks = cast("list[object]", correct if isinstance(correct, list) else [])
    if (
        not all(isinstance(value, str) for value in filled)
        or not expected_blanks
        or not all(isinstance(value, list) for value in expected_blanks)
    ):
        raise HTTPException(status_code=409, detail="该题需要提交逐空答案")
    stripped = [value.strip() for value in cast(list[str], filled)]
    accepted = [cast(list[str], blank) for blank in expected_blanks]
    if len(stripped) != len(accepted):
        raise HTTPException(status_code=400, detail="填空题作答数量与空位不一致")
    hit = sum(1 for index, value in enumerate(stripped) if value in accepted[index])
    score = hit / len(accepted)
    if hit == len(accepted):
        result = QuizTestItemResult.CORRECT
    elif hit:
        result = QuizTestItemResult.PARTIAL
    else:
        result = QuizTestItemResult.WRONG
    return result, score, stripped


def _test_answer_event(
    test: QuizTest,
    item: QuizTestItem,
    quiz: Quiz,
    result: QuizTestItemResult,
    score: float,
    now: datetime,
) -> LearningEvent:
    return LearningEvent(
        id=str(uuid4()),
        course_id=test.course_id,
        record_id=None,
        concept_id=None,
        event_type=QuizLearningEventType.ANSWERED,
        source_type=QuizLearningEventSourceType.QUESTION,
        source_id=quiz.id,
        result=result.value,
        score=score,
        difficulty=quiz.difficulty,
        duration_ms=None,
        metadata_json=json.dumps(
            {
                "test_id": test.id,
                "question_type": quiz.question_type,
                "sequence_no": item.sequence_no,
            },
            separators=(",", ":"),
        ),
        idempotency_key=f"quiz-answered:test:{item.id}",
        schema_version=1,
        occurred_at=now,
        created_at=now,
    )


async def _grade_and_record(
    session: AsyncSession,
    test: QuizTest,
    item: QuizTestItem,
    quiz: Quiz,
    answer: int | str | list[int] | list[str],
) -> None:
    question_type = QuizQuestionType(quiz.question_type)
    result: QuizTestItemResult | None
    score: float | None
    stored: int | str | list[int] | list[str] = answer
    if question_type is QuizQuestionType.SHORT_ANSWER:
        if not isinstance(answer, str):
            raise HTTPException(status_code=409, detail="该题需要提交文本作答")
        result = None
        score = None
    else:
        result, score, stored = _grade_objective(quiz, cast(object, answer))
    now = utcnow()
    updated = await session.execute(
        update(QuizTestItem)
        .where(
            QuizTestItem.id == item.id,
            QuizTestItem.answered_at.is_(None),
        )
        .values(
            user_answer_json=json.dumps(stored, ensure_ascii=False, separators=(",", ":")),
            result=result.value if result is not None else None,
            score=score,
            answered_at=now,
            updated_at=now,
        )
    )
    if not isinstance(updated, CursorResult) or updated.rowcount != 1:
        # 并发重复提交：已答状态由胜者事务落定，本事务按幂等返回当前事实。
        await session.refresh(item)
        return
    if result is not None:
        session.add(_test_answer_event(test, item, quiz, result, cast(float, score), now))
    await session.flush()
