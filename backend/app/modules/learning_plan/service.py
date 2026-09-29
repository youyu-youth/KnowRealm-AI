"""学习目标与学习计划领域 Service（工单 01/02）：目标 CRUD 与计划确认 / 查询。

事务内核心（*_core）由 HTTP 路由与 Agent 操作应用器共用，调用方拥有事务
边界（先例：CourseService）；课程软删后目标与计划随空间查询不可见（查询期
JOIN 过滤，不写级联），恢复课程即恢复——与 Record 同模式。
"""

import json
from datetime import UTC, date
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.course.models import Course
from app.modules.course.service import CourseService
from app.modules.learning_plan.models import LearningGoal, LearningPlan, LearningPlanItem
from app.modules.learning_plan.schemas import (
    GoalCreateCore,
    GoalStatus,
    GoalUpdate,
    PlanConfirmCore,
    PlanItemOut,
    PlanOut,
    PlanStatus,
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


class PlanService:
    """学习计划领域 Service（工单 02）：确认落库与只读查询。

    草案生成在 generation.PlanGenerationService（零业务写）；本服务只在
    用户经确认卡确认后写 learning_plans / learning_plan_items（同一目标
    同时至多一个 ACTIVE 版本，部分唯一索引兜底并发）。
    """

    @staticmethod
    async def require_no_active(session: AsyncSession, goal_id: str) -> None:
        """同目标单 ACTIVE 计划校验（唯一入口）：应用层稳定错误码 + 索引兜底。"""
        existing = await session.scalar(
            select(LearningPlan.id).where(
                LearningPlan.goal_id == goal_id,
                LearningPlan.status == PlanStatus.ACTIVE.value,
            )
        )
        if existing is not None:
            raise CodedHTTPException(
                code="PLAN_ACTIVE_EXISTS",
                status_code=409,
                detail="该目标已有进行中的学习计划；调整或重生成随后续版本提供",
            )

    @staticmethod
    async def confirm_core(
        session: AsyncSession, goal: LearningGoal, payload: PlanConfirmCore
    ) -> LearningPlan:
        """确认落库事务内核心：新版本号 + 计划头 + 逐项写入（调用方事务内）。

        版本号 = 该目标现有最大版本 + 1（工单 02 首次确认恒为 1；重生成
        SUPERSEDED 旧版随工单 03 启用）；effective_from = 落库日（UTC）。
        项 reason 经 reason_json 持久化；priority 按阶段顺序全局递增。
        """
        await PlanService.require_no_active(session, goal.id)
        next_version = 1 + (
            await session.scalar(
                select(func.max(LearningPlan.plan_version)).where(LearningPlan.goal_id == goal.id)
            )
            or 0
        )
        plan = LearningPlan(
            goal_id=goal.id,
            plan_version=next_version,
            status=PlanStatus.ACTIVE.value,
            effective_from=utcnow().astimezone(UTC).date().isoformat(),
        )
        session.add(plan)
        await session.flush()
        now = utcnow()
        priority = 0
        for phase in payload.phases:
            for item in phase.items:
                session.add(
                    LearningPlanItem(
                        plan_id=plan.id,
                        action_type=item.action_type.value,
                        content=item.content,
                        record_id=item.record_id,
                        concept_id=item.concept_id,
                        phase_title=phase.title,
                        priority=priority,
                        estimated_minutes=item.estimated_minutes,
                        scheduled_date=item.scheduled_date.isoformat(),
                        status="PENDING",
                        user_locked=False,
                        reason_json=json.dumps({"reason": item.reason}, ensure_ascii=False),
                        created_at=now,
                        updated_at=now,
                    )
                )
                priority += 1
        await session.flush()
        return plan

    @staticmethod
    async def get_active_for_goal(session: AsyncSession, goal_id: str) -> LearningPlan | None:
        """目标的 ACTIVE 计划（无则 None；目标不可达经 GoalService.get 前置）。"""
        return await session.scalar(
            select(LearningPlan)
            .where(
                LearningPlan.goal_id == goal_id,
                LearningPlan.status == PlanStatus.ACTIVE.value,
            )
            .order_by(LearningPlan.plan_version.desc())
        )

    @staticmethod
    async def list_items(session: AsyncSession, plan_id: str) -> list[LearningPlanItem]:
        """计划项按 priority 升序（阶段分组由消费方按 phase_title 聚合）。"""
        return list(
            (
                await session.scalars(
                    select(LearningPlanItem)
                    .where(LearningPlanItem.plan_id == plan_id)
                    .order_by(LearningPlanItem.priority)
                )
            ).all()
        )

    @staticmethod
    def plan_out(plan: LearningPlan, items: list[LearningPlanItem], *, course_id: str) -> PlanOut:
        """计划 + 项 → 只读投影（reason_json 解析失败降级 None，不炸查询）。"""
        return PlanOut(
            id=plan.id,
            goal_id=plan.goal_id,
            course_id=course_id,
            plan_version=plan.plan_version,
            status=PlanStatus(plan.status),
            effective_from=date.fromisoformat(plan.effective_from),
            effective_to=(
                date.fromisoformat(plan.effective_to) if plan.effective_to is not None else None
            ),
            items=[
                PlanItemOut(
                    id=item.id,
                    action_type=item.action_type,  # type: ignore[arg-type]
                    content=item.content,
                    record_id=item.record_id,
                    concept_id=item.concept_id,
                    phase_title=item.phase_title,
                    priority=item.priority,
                    estimated_minutes=item.estimated_minutes,
                    scheduled_date=date.fromisoformat(item.scheduled_date),
                    status=item.status,
                    user_locked=item.user_locked,
                    reason=_reason_of(item.reason_json),
                )
                for item in items
            ],
        )


def _reason_of(reason_json: str | None) -> str | None:
    """reason_json → reason 字段（形状漂移时 None，与提案载荷防御性解析同口径）。"""
    if reason_json is None:
        return None
    try:
        value: object = json.loads(reason_json)
    except ValueError:
        return None
    if isinstance(value, dict):
        data = cast("dict[str, object]", value)
        reason = data.get("reason")
        return reason if isinstance(reason, str) else None
    return None
