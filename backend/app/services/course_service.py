import json
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.base import utcnow
from app.models.course import Course
from app.schemas.course import (
    CourseCreate,
    CourseType,
    CourseUpdate,
    EducationStage,
    LearningContext,
)


class CourseService:
    @staticmethod
    async def create(session: AsyncSession, payload: CourseCreate) -> Course:
        course = Course(**payload.model_dump(mode="json"))
        async with session.begin():
            session.add(course)
            await session.flush()
        return course

    @staticmethod
    async def get(session: AsyncSession, course_id: str) -> Course | None:
        statement = select(Course).where(
            Course.id == course_id,
            Course.deleted_at.is_(None),
        )
        return (await session.scalars(statement)).one_or_none()

    @staticmethod
    async def update(
        session: AsyncSession,
        course_id: str,
        payload: CourseUpdate,
    ) -> Course | None:
        async with session.begin():
            course = await CourseService.get(session, course_id)
            if course is None:
                return None
            changes = payload.model_dump(exclude_unset=True)
            # 显式 null 的 name / learning_context 表示"未修改"，与可清空字段区分。
            if changes.get("name") is None:
                changes.pop("name", None)
            if changes.get("learning_context") is None:
                changes.pop("learning_context", None)
            if "hot_words" in changes:
                changes["hot_words"] = json.dumps(
                    changes["hot_words"] or [],
                    ensure_ascii=False,
                )
            if changes:
                final_context = changes.get("learning_context", course.learning_context)
                if final_context == LearningContext.SCHOOL:
                    final_stage = changes.get("education_stage", course.education_stage)
                    if final_stage is None:
                        raise HTTPException(status_code=422, detail="学业场景必须选择教育阶段")
                    changes["education_stage"] = final_stage
                    changes["depth"] = None
                else:
                    final_depth = changes.get("depth", course.depth)
                    if final_depth is None:
                        raise HTTPException(
                            status_code=422, detail="职业或兴趣场景必须选择学习深度"
                        )
                    changes["depth"] = final_depth
                    changes["education_stage"] = None
                for field, value in changes.items():
                    setattr(course, field, value)
                course.updated_at = utcnow()
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
        if q:
            statement = statement.where(Course.name.contains(q, autoescape=True, escape="\\"))
        if education_stage is not None:
            statement = statement.where(Course.education_stage == education_stage.value)
        if course_type is not None:
            statement = statement.where(Course.course_type == course_type.value)
        statement = statement.order_by(Course.updated_at.desc())
        return list((await session.scalars(statement)).all())

    @staticmethod
    async def soft_delete(session: AsyncSession, course_id: str) -> bool:
        async with session.begin():
            course = await CourseService.get(session, course_id)
            if course is None:
                return False
            deleted_at = utcnow()
            course.deleted_at = deleted_at
            course.updated_at = deleted_at
            await session.flush()
        return True

    @staticmethod
    async def purge_expired(
        session_factory: async_sessionmaker[AsyncSession],
        *,
        now: datetime | None = None,
    ) -> None:
        cutoff = (now or utcnow()) - timedelta(days=30)
        async with session_factory() as session, session.begin():
            await session.execute(
                delete(Course).where(
                    Course.deleted_at.is_not(None),
                    Course.deleted_at < cutoff,
                )
            )
