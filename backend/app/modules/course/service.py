import json

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.capture.models import RecordingSession
from app.modules.capture.schemas import RecordingSessionState
from app.modules.course.models import Course
from app.modules.course.schemas import (
    CourseCreate,
    CourseType,
    CourseUpdate,
    EducationStage,
    LearningContext,
)
from app.modules.jobs.lifecycle import cancel_nonterminal_jobs
from app.modules.jobs.models import ProcessingJob
from app.modules.record.models import Record
from app.modules.search.service import SearchService
from app.shared.errors import CodedHTTPException


class CourseService:
    @staticmethod
    async def create(session: AsyncSession, payload: CourseCreate) -> Course:
        course = Course(**payload.model_dump(mode="json"))
        async with session.begin():
            session.add(course)
            await session.flush()
            await SearchService.upsert_course_index(session, course.id)
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
                        raise CodedHTTPException(
                            code="COURSE_EDUCATION_STAGE_REQUIRED",
                            status_code=422,
                            detail="学业场景必须选择教育阶段",
                        )
                    changes["education_stage"] = final_stage
                    changes["depth"] = None
                else:
                    final_depth = changes.get("depth", course.depth)
                    if final_depth is None:
                        raise CodedHTTPException(
                            code="COURSE_LEARNING_DEPTH_REQUIRED",
                            status_code=422,
                            detail="职业或兴趣场景必须选择学习深度",
                        )
                    changes["depth"] = final_depth
                    changes["education_stage"] = None
                for field, value in changes.items():
                    setattr(course, field, value)
                course.updated_at = utcnow()
            await session.flush()
            await SearchService.upsert_course_index(session, course_id)
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
            record_ids = select(Record.id).where(
                Record.course_id == course_id,
                Record.deleted_at.is_(None),
            )
            await cancel_nonterminal_jobs(
                session,
                record_filter=ProcessingJob.record_id.in_(record_ids),
                now=deleted_at,
            )
            await session.execute(
                update(RecordingSession)
                .where(
                    RecordingSession.course_id == course_id,
                    RecordingSession.state != RecordingSessionState.DONE,
                )
                .values(course_id=None, updated_at=deleted_at)
            )
            await session.execute(
                update(Record)
                .where(
                    Record.course_id == course_id,
                    Record.deleted_at.is_(None),
                )
                .values(deleted_at=deleted_at, updated_at=deleted_at)
            )
            course.deleted_at = deleted_at
            course.updated_at = deleted_at
            await session.flush()
        return True
