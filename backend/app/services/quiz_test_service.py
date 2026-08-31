import json
from typing import cast
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import Course
from app.models.document import Quiz, QuizTest, QuizTestItem
from app.models.record import Record
from app.schemas.course import CourseStatus
from app.schemas.quiz import QuizGenerationStatus, QuizQuestionType
from app.schemas.quiz_test import (
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
        rows = (
            await session.execute(
                select(QuizTestItem, Quiz)
                .join(Quiz, Quiz.id == QuizTestItem.quiz_id)
                .where(
                    QuizTestItem.test_id == test_id,
                    QuizTestItem.deleted_at.is_(None),
                )
                .order_by(QuizTestItem.sequence_no)
            )
        ).all()
        items = [
            QuizTestItemOut(
                id=item.id,
                quiz_id=item.quiz_id,
                sequence_no=item.sequence_no,
                question_type=QuizQuestionType(quiz.question_type),
                stem=quiz.stem,
                options=cast(list[str], json.loads(quiz.options_json)),
                difficulty=quiz.difficulty,
                user_answer=cast(
                    int | str | list[int] | list[str] | None,
                    _decode_json(item.user_answer_json),
                ),
                result=QuizTestItemResult(item.result) if item.result is not None else None,
                score=item.score,
                answered_at=item.answered_at,
            )
            for item, quiz in rows
        ]
        return QuizTestDetailOut(
            **_summary_out(
                test,
                len(items),
                sum(item.answered_at is not None for item in items),
            ).model_dump(),
            items=items,
        )


class QuizTestBlocked(Exception):
    def __init__(self, detail: str, blocked_reason: QuizTestBlockedReason) -> None:
        super().__init__(detail)
        self.detail = detail
        self.blocked_reason = blocked_reason
