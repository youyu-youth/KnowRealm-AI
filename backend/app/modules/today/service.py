from datetime import timedelta
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.chat.models import ChatMessage, ChatSession
from app.modules.chat.schemas import ChatRole
from app.modules.course.models import Course
from app.modules.quiz.models import Quiz
from app.modules.record.models import Record
from app.modules.record.schemas import RecordStatus
from app.modules.summary.models import AiSummary
from app.modules.today.schemas import TodayStatsOut, TodaySummaryTodoOut, TodayTrendPointOut


class TodayService:
    @staticmethod
    async def list_pending_summaries(
        session: AsyncSession,
    ) -> list[TodaySummaryTodoOut]:
        rows = (
            await session.execute(
                select(Record, Course.name)
                .join(Course, Record.course_id == Course.id)
                .where(
                    Record.status == RecordStatus.SUMMARY_READY,
                    Record.deleted_at.is_(None),
                    Course.deleted_at.is_(None),
                )
                .order_by(Record.updated_at.desc())
            )
        ).all()
        return [
            TodaySummaryTodoOut(
                record_id=record.id,
                title=record.title,
                course_id=cast(str, record.course_id),
                course_name=course_name,
                ready_at=record.updated_at,
            )
            for record, course_name in rows
        ]

    @staticmethod
    async def stats(session: AsyncSession) -> TodayStatsOut:
        # 双重软删过滤：record 域指标 JOIN records（删记录/课程即回落，不依赖子表级联），
        # 子表自身 deleted_at 按 data-layer 规则同样过滤。
        total_learning_ms = cast(
            "int",
            await session.scalar(
                select(func.coalesce(func.sum(Record.duration_ms), 0)).where(
                    Record.deleted_at.is_(None)
                )
            ),
        )
        record_count = cast(
            "int",
            await session.scalar(
                select(func.count()).select_from(Record).where(Record.deleted_at.is_(None))
            ),
        )
        course_count = cast(
            "int",
            await session.scalar(
                select(func.count()).select_from(Course).where(Course.deleted_at.is_(None))
            ),
        )
        ai_summary_count = cast(
            "int",
            await session.scalar(
                select(func.count())
                .select_from(AiSummary)
                .join(Record, AiSummary.record_id == Record.id)
                .where(AiSummary.deleted_at.is_(None), Record.deleted_at.is_(None))
            ),
        )
        quiz_generated_count = cast(
            "int",
            await session.scalar(
                select(func.count())
                .select_from(Quiz)
                .join(Record, Quiz.record_id == Record.id)
                .where(Quiz.deleted_at.is_(None), Record.deleted_at.is_(None))
            ),
        )
        quiz_answered_count = cast(
            "int",
            await session.scalar(
                select(func.count())
                .select_from(Quiz)
                .join(Record, Quiz.record_id == Record.id)
                .where(
                    Quiz.deleted_at.is_(None),
                    Quiz.answered_at.is_not(None),
                    Record.deleted_at.is_(None),
                )
            ),
        )
        chat_turn_count = cast(
            "int",
            await session.scalar(
                select(func.count())
                .select_from(ChatMessage)
                .join(ChatSession, ChatMessage.session_id == ChatSession.id)
                .where(ChatMessage.role == ChatRole.USER, ChatSession.deleted_at.is_(None))
            ),
        )
        return TodayStatsOut(
            total_learning_ms=total_learning_ms,
            record_count=record_count,
            course_count=course_count,
            ai_summary_count=ai_summary_count,
            quiz_generated_count=quiz_generated_count,
            quiz_answered_count=quiz_answered_count,
            chat_turn_count=chat_turn_count,
        )

    @staticmethod
    async def stats_trend(
        session: AsyncSession,
        days: int,
    ) -> list[TodayTrendPointOut]:
        # 捕获日 = date(created_at)（UTC 存储）；缺天后端补零，序列连续无空洞。
        today = utcnow().date()
        start = today - timedelta(days=days - 1)
        rows = (
            await session.execute(
                select(
                    func.date(Record.created_at),
                    func.coalesce(func.sum(Record.duration_ms), 0),
                )
                .where(
                    Record.deleted_at.is_(None),
                    func.date(Record.created_at) >= start.isoformat(),
                )
                .group_by(func.date(Record.created_at))
            )
        ).all()
        totals_by_day = {str(day): int(total) for day, total in rows}
        points: list[TodayTrendPointOut] = []
        for offset in range(days):
            day = (start + timedelta(days=offset)).isoformat()
            points.append(TodayTrendPointOut(date=day, total_ms=totals_by_day.get(day, 0)))
        return points
