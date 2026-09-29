"""学习目标领域 Service（工单 01）：创建 / 编辑 / 完成 / 归档与查询。

事务内核心（*_core）由 HTTP 路由与 Agent 操作应用器共用，调用方拥有事务
边界（先例：CourseService）；课程软删后目标查询不可见（查询期 JOIN 过滤，
不写级联），恢复课程即恢复——与 Record 同模式。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.course.models import Course
from app.modules.course.service import CourseService
from app.modules.learning_plan.models import LearningGoal
from app.modules.learning_plan.schemas import (
    GoalCreateCore,
    GoalStatus,
    GoalUpdate,
)
from app.shared.errors import CodedHTTPException


def _require_active(goal: LearningGoal) -> None:
    """编辑与状态变更只对进行中目标开放（完成 / 归档均为终态）。"""
    if goal.status != GoalStatus.ACTIVE.value:
        raise CodedHTTPException(
            code="GOAL_NOT_ACTIVE",
            status_code=409,
            detail="目标已完结或归档，只有进行中的目标可以修改",
        )


class GoalService:
    @staticmethod
    async def require_no_active(session: AsyncSession, course_id: str) -> None:
        """单空间单 ACTIVE 校验（唯一入口，创建核心与 Agent 提交期检查共用）。

        应用层先给出可转述的稳定错误码（提示先完成或归档旧目标），部分唯一
        索引兜底并发写入。
        """
        existing = await session.scalar(
            select(LearningGoal.id).where(
                LearningGoal.course_id == course_id,
                LearningGoal.status == GoalStatus.ACTIVE.value,
            )
        )
        if existing is not None:
            raise CodedHTTPException(
                code="GOAL_ACTIVE_EXISTS",
                status_code=409,
                detail="该知识空间已有进行中的学习目标，请先完成或归档旧目标",
            )

    @staticmethod
    async def create_core(
        session: AsyncSession, course: Course, payload: GoalCreateCore
    ) -> LearningGoal:
        """目标创建事务内核心：单空间单 ACTIVE 校验＋scope 确认不变量。

        AI_INFERRED 未确认在 GoalCreateCore schema 校验即拒绝（不进本方法）。
        """
        await GoalService.require_no_active(session, course.id)
        goal = LearningGoal(
            course_id=course.id,
            **payload.model_dump(mode="json"),
        )
        session.add(goal)
        await session.flush()
        return goal

    @staticmethod
    async def create(
        session: AsyncSession, course_id: str, payload: GoalCreateCore
    ) -> LearningGoal | None:
        """HTTP 创建入口（None = 课程不存在或已删除）。"""
        async with session.begin():
            course = await CourseService.get(session, course_id)
            if course is None:
                return None
            return await GoalService.create_core(session, course, payload)

    @staticmethod
    async def get(session: AsyncSession, goal_id: str) -> LearningGoal | None:
        """按 id 取目标；课程软删后不可见（None，恢复课程即恢复）。"""
        statement = (
            select(LearningGoal)
            .join(Course, Course.id == LearningGoal.course_id)
            .where(LearningGoal.id == goal_id, Course.deleted_at.is_(None))
        )
        return (await session.scalars(statement)).one_or_none()

    @staticmethod
    async def list_for_course(session: AsyncSession, course_id: str) -> list[LearningGoal] | None:
        """课程全部目标（进行中在前，其余按更新时间倒序）；None = 课程不可见。"""
        course = await CourseService.get(session, course_id)
        if course is None:
            return None
        statement = (
            select(LearningGoal)
            .where(LearningGoal.course_id == course_id)
            .order_by(
                LearningGoal.status != GoalStatus.ACTIVE.value,
                LearningGoal.updated_at.desc(),
            )
        )
        return list((await session.scalars(statement)).all())

    @staticmethod
    async def update_core(
        session: AsyncSession, goal: LearningGoal, payload: GoalUpdate
    ) -> LearningGoal:
        """目标编辑事务内核心（期限 / 每日投入 / 标题 / 目标分数）：仅 ACTIVE。

        HTTP PATCH 的显式 null 表示清空可空字段（期限 / 投入 / 分数）；标题为
        必填不可清空。所有变更统一维护 updated_at（快照纪律不变量）。
        """
        _require_active(goal)
        # mode="json"：date 等类型按存储形态（ISO 字符串）落 String 列。
        changes = payload.model_dump(exclude_unset=True, mode="json")
        if changes.get("title") is None:
            changes.pop("title", None)
        if changes:
            for field, value in changes.items():
                setattr(goal, field, value)
            goal.updated_at = utcnow()
        await session.flush()
        return goal

    @staticmethod
    async def set_status_core(
        session: AsyncSession, goal: LearningGoal, status: GoalStatus
    ) -> LearningGoal:
        """完成 / 归档事务内核心：仅 ACTIVE 可流转（终态单向，无恢复入口）。"""
        _require_active(goal)
        goal.status = status.value
        goal.updated_at = utcnow()
        await session.flush()
        return goal

    @staticmethod
    async def update(
        session: AsyncSession,
        goal_id: str,
        payload: GoalUpdate,
        *,
        expected_course_id: str | None = None,
    ) -> LearningGoal | None:
        """HTTP 编辑入口（None = 目标不存在 / 课程已软删 / 嵌套路径课程不匹配）。

        expected_course_id 是嵌套路由的路径归属校验：路径课程与目标实际归属
        不一致时按不可见处理（404），Agent 路径按 goal_id 直达不传。
        """
        async with session.begin():
            goal = await GoalService.get(session, goal_id)
            if goal is None or (
                expected_course_id is not None and goal.course_id != expected_course_id
            ):
                return None
            return await GoalService.update_core(session, goal, payload)

    @staticmethod
    async def set_status(
        session: AsyncSession,
        goal_id: str,
        status: GoalStatus,
        *,
        expected_course_id: str | None = None,
    ) -> LearningGoal | None:
        """HTTP 完成 / 归档入口（None 语义同 update：不存在 / 软删 / 归属不匹配）。"""
        async with session.begin():
            goal = await GoalService.get(session, goal_id)
            if goal is None or (
                expected_course_id is not None and goal.course_id != expected_course_id
            ):
                return None
            return await GoalService.set_status_core(session, goal, status)
