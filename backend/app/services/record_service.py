from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utcnow
from app.models.record import Record
from app.services.course_service import CourseService


class RecordService:
    @staticmethod
    async def get(session: AsyncSession, record_id: str) -> Record | None:
        statement = select(Record).where(
            Record.id == record_id,
            Record.deleted_at.is_(None),
        )
        record = (await session.scalars(statement)).one_or_none()
        if record is None:
            return None
        if (
            record.course_id is not None
            and await CourseService.get(session, record.course_id) is None
        ):
            return None
        return record

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

    @staticmethod
    async def soft_delete(session: AsyncSession, record_id: str) -> bool:
        async with session.begin():
            record = await RecordService.get(session, record_id)
            if record is None:
                return False
            deleted_at = utcnow()
            record.deleted_at = deleted_at
            record.updated_at = deleted_at
            await session.flush()
        return True
