from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.course import Course
from app.schemas.course import CourseCreate, CourseType, EducationStage


class CourseService:
    @staticmethod
    async def create(session: AsyncSession, payload: CourseCreate) -> Course:
        course = Course(**payload.model_dump(mode="json"))
        async with session.begin():
            session.add(course)
            await session.flush()
        return course

    @staticmethod
    async def list(
        session: AsyncSession,
        q: str | None = None,
        education_stage: EducationStage | None = None,
        course_type: CourseType | None = None,
    ) -> list[Course]:
        statement = select(Course).where(Course.deleted_at.is_(None))
        if query := q.strip() if q else "":
            statement = statement.where(
                Course.name.contains(query, autoescape=True, escape="\\")
            )
        if education_stage is not None:
            statement = statement.where(Course.education_stage == education_stage.value)
        if course_type is not None:
            statement = statement.where(Course.course_type == course_type.value)
        statement = statement.order_by(Course.updated_at.desc())
        return list((await session.scalars(statement)).all())
