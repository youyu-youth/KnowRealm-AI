import asyncio
import json
from collections.abc import Callable, Collection

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
from app.modules.learning.service import MasteryService
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
    async def soft_delete_core(
        session: AsyncSession, course: Course
    ) -> "tuple[set[str], int]":
        """课程软删事务内核心（工单 04 收拢，不得自行 begin）：级联软删记录＋
        取消非终态任务＋录音会话脱钩；返回（受影响 Concept 集合, 被级联软删的
        记录条数）——概念由调用方触发 Mastery 重算，计数进回执投影。删除纪律
        沿用 Record 链。"""
        affected_concepts = {
            concept_id
            for concept_id in (
                await session.scalars(
                    select(LearningEvent.concept_id).where(
                        LearningEvent.course_id == course.id,
                        LearningEvent.concept_id.is_not(None),
                    )
                )
            ).all()
            if concept_id is not None
        }
        deleted_at = utcnow()
        record_ids = list(
            (
                await session.scalars(
                    select(Record.id).where(
                        Record.course_id == course.id,
                        Record.deleted_at.is_(None),
                    )
                )
            ).all()
        )
        await cancel_nonterminal_jobs(
            session,
            record_filter=ProcessingJob.record_id.in_(record_ids),
            now=deleted_at,
        )
        await session.execute(
            update(RecordingSession)
            .where(
                RecordingSession.course_id == course.id,
                RecordingSession.state != RecordingSessionState.DONE,
            )
            .values(course_id=None, updated_at=deleted_at)
        )
        await session.execute(
            update(Record)
            .where(
                Record.course_id == course.id,
                Record.deleted_at.is_(None),
            )
            .values(deleted_at=deleted_at, updated_at=deleted_at)
        )
        course.deleted_at = deleted_at
        course.updated_at = deleted_at
        await session.flush()
        return affected_concepts, len(record_ids)

    @staticmethod
    async def apply_soft_delete(
        session: AsyncSession,
        course: Course,
        *,
        schedule_retry: Callable[[Collection[str]], None] | None = None,
    ) -> "tuple[int, list[asyncio.Task[None]]]":
        """课程删除领域应用函数（工单 04，spec 决策 15）：调用方拥有事务边界，
        HTTP 路由与 Agent 应用器共用——级联软删（soft_delete_core）＋掌握度
        重算＋consumer 重试一体编排；重算经 after_commit 挂钩在事务提交后执行
        （回滚不触发；失败交 stale 哨兵启动恢复或 schedule_retry 进程内自愈）。

        返回（被级联软删的记录条数, 重算任务容器）：需要同步等待重算完成的
        调用方（HTTP 删除路由的既有语义）在事务提交后 await 容器元素，Agent
        确认路径忽略容器由后台执行。
        """
        affected_concepts, record_count = await CourseService.soft_delete_core(session, course)
        recompute_tasks = MasteryService.schedule_recompute_after_commit(
            session, affected_concepts, schedule_retry=schedule_retry
        )
        return record_count, recompute_tasks

    @staticmethod
    async def soft_delete(
        session: AsyncSession,
        course_id: str,
        *,
        schedule_retry: Callable[[Collection[str]], None] | None = None,
    ) -> bool:
        """课程软删 HTTP 入口（False = 课程不存在）：删除与重算编排一体
        （apply_soft_delete，工单 04 收拢——重算不再留在路由层）；既有路由
        语义保持同步等待重算完成后再返回。"""
        recompute_tasks: list[asyncio.Task[None]] = []
        async with session.begin():
            course = await CourseService.get(session, course_id)
            if course is None:
                return False
            _, recompute_tasks = await CourseService.apply_soft_delete(
                session, course, schedule_retry=schedule_retry
            )
        # 删除事务已提交（挂钩已把重算任务填入容器），同步等待完成。
        if recompute_tasks:
            await recompute_tasks[0]
        return True
