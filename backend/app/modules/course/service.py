import json

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.capture.models import RecordingSession
from app.modules.capture.schemas import RecordingSessionState
from app.modules.course.models import Course
from app.modules.course.schemas import (
    CourseCreate,
    CourseStatus,
    CourseType,
    CourseUpdate,
    EducationStage,
    LearningContext,
)
from app.modules.jobs.lifecycle import cancel_nonterminal_jobs
from app.modules.jobs.models import ProcessingJob
from app.modules.record.models import LearningEvent, Record
from app.modules.search.service import SearchService
from app.shared.errors import CodedHTTPException


class CourseService:
    @staticmethod
    async def create_core(session: AsyncSession, payload: CourseCreate) -> Course:
        """课程创建事务内核心（工单 02）：不自行开事务，由调用方拥有事务边界。

        HTTP 路由（CourseService.create）与提案应用器（agent/operations）共用
        同一核心：业务写入与搜索索引同事务原子提交，校验逻辑零双份漂移。
        """
        course = Course(**payload.model_dump(mode="json"))
        session.add(course)
        await session.flush()
        await SearchService.upsert_course_index(session, course.id)
        return course

    @staticmethod
    async def create(session: AsyncSession, payload: CourseCreate) -> Course:
        async with session.begin():
            return await CourseService.create_core(session, payload)

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
            await CourseService.update_core(session, course, payload)
        return course

    @staticmethod
    async def update_core(
        session: AsyncSession, course: Course, payload: CourseUpdate
    ) -> Course:
        """课程更新事务内核心（工单 03）：调用方拥有事务边界，HTTP 路由与
        Agent 应用器共用同一校验链（场景 / 阶段或深度条件校验同源）。

        显式 null 的 name / learning_context 表示"未修改"，与可清空字段区分；
        所有变更统一维护 updated_at（快照纪律显式不变量，spec 决策 12）。
        """
        changes = payload.model_dump(exclude_unset=True)
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
        await SearchService.upsert_course_index(session, course.id)
        return course

    @staticmethod
    async def set_status_core(
        session: AsyncSession, course: Course, *, archived: bool
    ) -> Course:
        """课程归档 / 恢复事务内核心（工单 03，历史推迟决策收口）：状态翻转
        ＋updated_at 维护。既有 ARCHIVED 三道读取闸门（summary / KP / quiz /
        todo 校验）零改动——归档只写状态，不级联不删数据；幂等守卫同 library
        条目口径（重复归档 / 重复恢复 409 稳定错误码）。"""
        if archived and course.status == CourseStatus.ARCHIVED:
            raise CodedHTTPException(
                code="COURSE_ALREADY_ARCHIVED",
                status_code=409,
                detail="课程已归档",
            )
        if not archived and course.status == CourseStatus.ACTIVE:
            raise CodedHTTPException(
                code="COURSE_ALREADY_ACTIVE",
                status_code=409,
                detail="课程未归档",
            )
        course.status = CourseStatus.ARCHIVED.value if archived else CourseStatus.ACTIVE.value
        course.updated_at = utcnow()
        await session.flush()
        return course

    @staticmethod
    async def set_status(
        session: AsyncSession, course_id: str, *, archived: bool
    ) -> Course | None:
        """课程归档 / 恢复 HTTP 入口（None = 课程不存在或已删除）。"""
        async with session.begin():
            course = await CourseService.get(session, course_id)
            if course is None:
                return None
            await CourseService.set_status_core(session, course, archived=archived)
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
    async def soft_delete(session: AsyncSession, course_id: str) -> set[str] | None:
        """软删除课程及其 Record，并返回受影响的 Concept 集合（None = 课程不存在）。

        删除纪律沿用 Record 链；受影响概念由调用方触发 Mastery 全量重算。
        """
        async with session.begin():
            course = await CourseService.get(session, course_id)
            if course is None:
                return None
            affected_concepts = {
                concept_id
                for concept_id in (
                    await session.scalars(
                        select(LearningEvent.concept_id).where(
                            LearningEvent.course_id == course_id,
                            LearningEvent.concept_id.is_not(None),
                        )
                    )
                ).all()
                if concept_id is not None
            }
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
        return affected_concepts
