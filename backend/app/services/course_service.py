from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import Course
from app.schemas.course import CourseCreate


class CourseService:
    @staticmethod
    async def create(session: AsyncSession, payload: CourseCreate) -> Course:
        course = Course(**payload.model_dump(mode="json"))
        async with session.begin():
            session.add(course)
            await session.flush()
        return course

    @staticmethod
    async def list(session: AsyncSession) -> list[Course]:
        statement = (
            select(Course).where(Course.deleted_at.is_(None)).order_by(Course.updated_at.desc())
        )
        return list((await session.scalars(statement)).all())
