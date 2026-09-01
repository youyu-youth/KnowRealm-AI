from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.course.models import Course
from app.modules.record.models import Record
from app.modules.record.schemas import RecordStatus
from app.schemas.today import TodaySummaryTodoOut


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
