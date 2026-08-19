from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.record import Record
from app.services.course_service import CourseService


class RecordService:
    @staticmethod
    async def list_for_course(
        session: AsyncSession,
        course_id: str,
    ) -> list[Record] | None:
        if await CourseService.get(session, course_id) is None:
            return None
        statement = (
            select(Record)
            .where(
                Record.course_id == course_id,
                Record.deleted_at.is_(None),
            )
            .order_by(Record.created_at.desc())
        )
        return list((await session.scalars(statement)).all())
