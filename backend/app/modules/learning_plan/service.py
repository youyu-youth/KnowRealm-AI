"""学习目标与学习计划领域 Service（工单 01/02）：目标 CRUD 与计划确认 / 查询。

事务内核心（*_core）由 HTTP 路由与 Agent 操作应用器共用，调用方拥有事务
边界（先例：CourseService）；课程软删后目标与计划随空间查询不可见（查询期
JOIN 过滤，不写级联），恢复课程即恢复——与 Record 同模式。
"""

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.course.models import Course
from app.modules.course.service import CourseService
from app.modules.learning_plan.audit import record_manual_audit
from app.modules.learning_plan.models import LearningGoal, LearningPlan, LearningPlanItem
from app.modules.learning_plan.schemas import (
    GoalCreateCore,
    GoalStatus,
    GoalUpdate,
    PlanConfirmCore,
    PlanConfirmItem,
    PlanItemOut,
    PlanItemStatus,
    PlanItemUpdate,
    PlanOut,
    PlanRegenerateCore,
    PlanStatus,
    PlanVersionOut,
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


def _add_plan_item(
    session: AsyncSession,
    *,
    plan_id: str,
    phase_title: str,
    priority: int,
    item: PlanConfirmItem,
    user_locked: bool,
    now: datetime,
) -> None:
    """计划项写入共用（确认与重生成，调用方事务内）：状态恒 PENDING 起新。

    PlanRegenerateItem 是 PlanConfirmItem 子类——重生成锁定项的安排字段照
    载荷原样（工具从旧版本行复制），状态与完成时间归零（进度事实留在
    SUPERSEDED 版本只读保留）。"""
    session.add(
        LearningPlanItem(
            plan_id=plan_id,
            action_type=item.action_type.value,
            content=item.content,
            record_id=item.record_id,
            concept_id=item.concept_id,
            phase_title=phase_title,
            priority=priority,
            estimated_minutes=item.estimated_minutes,
            scheduled_date=item.scheduled_date.isoformat(),
            status=PlanItemStatus.PENDING.value,
            user_locked=user_locked,
            reason_json=json.dumps({"reason": item.reason}, ensure_ascii=False),
            created_at=now,
            updated_at=now,
        )
    )


class PlanService:
    """学习计划领域 Service（工单 02/03）：确认落库、只读查询与重生成。

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
    async def _next_version(session: AsyncSession, goal_id: str, now: datetime) -> LearningPlan:
        """新 ACTIVE 版本头（版本号 = 现有最大版本 + 1，调用方事务内 flush）。"""
        next_version = 1 + (
            await session.scalar(
                select(func.max(LearningPlan.plan_version)).where(LearningPlan.goal_id == goal_id)
            )
            or 0
        )
        plan = LearningPlan(
            goal_id=goal_id,
            plan_version=next_version,
            status=PlanStatus.ACTIVE.value,
            effective_from=now.astimezone(UTC).date().isoformat(),
        )
        session.add(plan)
        return plan

    @staticmethod
    async def confirm_core(
        session: AsyncSession, goal: LearningGoal, payload: PlanConfirmCore
    ) -> LearningPlan:
        """确认落库事务内核心：新版本号 + 计划头 + 逐项写入（调用方事务内）。

        版本号 = 该目标现有最大版本 + 1（首次确认恒为 1；重生成换代由
        regenerate_core 负责）；effective_from = 落库日（UTC）。
        项 reason 经 reason_json 持久化；priority 按阶段顺序全局递增。
        """
        await PlanService.require_no_active(session, goal.id)
        plan = await PlanService._next_version(session, goal.id, utcnow())
        await session.flush()
        now = utcnow()
        priority = 0
        for phase in payload.phases:
            for item in phase.items:
                _add_plan_item(
                    session,
                    plan_id=plan.id,
                    phase_title=phase.title,
                    priority=priority,
                    item=item,
                    user_locked=False,
                    now=now,
                )
                priority += 1
        await session.flush()
        return plan

    @staticmethod
    async def regenerate_core(
        session: AsyncSession, goal: LearningGoal, payload: PlanRegenerateCore
    ) -> LearningPlan:
        """重生成事务内核心（工单 03，spec 用户故事 15~16，调用方事务内）：
        当前 ACTIVE 版本 SUPERSEDED（effective_to = 换代日，进度记录随旧版
        只读保留）→ 新版本落库；user_locked 项原样带入（安排字段照载荷、
        状态归 PENDING——旧版本已完成 / 跳过的事实不结转到新执行周期）。"""
        old = await PlanService.get_active_for_goal(session, goal.id)
        now = utcnow()
        today = now.astimezone(UTC).date().isoformat()
        if old is not None:
            old.status = PlanStatus.SUPERSEDED.value
            old.effective_to = today
            old.updated_at = now
            await session.flush()
        plan = await PlanService._next_version(session, goal.id, now)
        await session.flush()
        priority = 0
        for phase in payload.phases:
            for item in phase.items:
                _add_plan_item(
                    session,
                    plan_id=plan.id,
                    phase_title=phase.title,
                    priority=priority,
                    item=item,
                    user_locked=item.user_locked,
                    now=now,
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
    async def get_with_goal(
        session: AsyncSession, plan_id: str, *, expected_course_id: str | None = None
    ) -> tuple[LearningPlan, LearningGoal] | None:
        """计划 + 归属目标查询（None = 不存在 / 课程软删 / 归属不匹配）。

        expected_course_id 是嵌套路由的路径归属校验（goal.update 先例）：路径
        课程与计划实际归属不一致时按不可见处理（404）。
        """
        statement = (
            select(LearningPlan, LearningGoal)
            .join(LearningGoal, LearningGoal.id == LearningPlan.goal_id)
            .join(Course, Course.id == LearningGoal.course_id)
            .where(LearningPlan.id == plan_id, Course.deleted_at.is_(None))
        )
        if expected_course_id is not None:
            statement = statement.where(LearningGoal.course_id == expected_course_id)
        row = (await session.execute(statement)).one_or_none()
        return None if row is None else (row[0], row[1])

    @staticmethod
    async def list_versions_for_goal(
        session: AsyncSession, goal_id: str
    ) -> list[tuple[LearningPlan, int]]:
        """目标全部版本（新版本在前）＋逐版本项数（历史版本只读查询）。"""
        rows = (
            await session.execute(
                select(LearningPlan, func.count(LearningPlanItem.id))
                .outerjoin(LearningPlanItem, LearningPlanItem.plan_id == LearningPlan.id)
                .where(LearningPlan.goal_id == goal_id)
                .group_by(LearningPlan.id)
                .order_by(LearningPlan.plan_version.desc())
            )
        ).all()
        return [(plan, int(count)) for plan, count in rows]

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
            items=[item_out(item) for item in items],
        )

    @staticmethod
    def version_out(plan: LearningPlan, *, course_id: str, item_count: int) -> PlanVersionOut:
        """版本摘要投影（历史版本列表）。"""
        return PlanVersionOut(
            id=plan.id,
            goal_id=plan.goal_id,
            course_id=course_id,
            plan_version=plan.plan_version,
            status=PlanStatus(plan.status),
            effective_from=date.fromisoformat(plan.effective_from),
            effective_to=(
                date.fromisoformat(plan.effective_to) if plan.effective_to is not None else None
            ),
            item_count=item_count,
        )


class PlanItemService:
    """计划项级 Service（工单 03）：就地编辑、完成与跳过——仅当前生效版本
    （历史版本只读），用户手动编辑过的项置 user_locked（重生成原样保留）。
    完成不产 learning_event、不动 Concept Mastery（spec「完成语义边界」）。
    """

    @staticmethod
    async def get_for_plan(
        session: AsyncSession, plan_id: str, item_id: str
    ) -> LearningPlanItem | None:
        return await session.scalar(
            select(LearningPlanItem).where(
                LearningPlanItem.id == item_id,
                LearningPlanItem.plan_id == plan_id,
            )
        )

    @staticmethod
    def require_active_plan(plan: LearningPlan) -> None:
        """编辑 / 完成 / 跳过只对 ACTIVE 版本开放（SUPERSEDED / COMPLETED 只读）。"""
        if plan.status != PlanStatus.ACTIVE.value:
            raise CodedHTTPException(
                code="PLAN_VERSION_NOT_ACTIVE",
                status_code=409,
                detail="只有当前生效版本的计划项可以修改，历史版本只读",
            )

    @staticmethod
    async def _require_item_plan_active(session: AsyncSession, item: LearningPlanItem) -> None:
        """项级核心共用的版本前置（goal.update 先例：核心自执法，调用方免查）。"""
        plan = await session.get(LearningPlan, item.plan_id)
        assert plan is not None  # FK 保证行存在
        PlanItemService.require_active_plan(plan)

    @staticmethod
    async def update_core(
        session: AsyncSession, item: LearningPlanItem, payload: PlanItemUpdate
    ) -> LearningPlanItem:
        """就地编辑事务内核心（日期 / 时长 / 内容）：用户手动编辑即置
        user_locked（spec 用户故事 15，重生成原样保留不被 AI 重排）。

        显式 null 字段忽略（三个字段均非空语义，直调 API 的 null 载荷不落
        NOT NULL 列炸 500；Agent 路径工具面已滤 None，同口径兜底）。"""
        await PlanItemService._require_item_plan_active(session, item)
        changes = {
            key: value
            for key, value in payload.model_dump(exclude_unset=True, mode="json").items()
            if value is not None
        }
        if changes:
            for field, value in changes.items():
                setattr(item, field, value)
            item.user_locked = True
            item.updated_at = utcnow()
        await session.flush()
        return item

    @staticmethod
    async def _load_active_item_in_course(
        session: AsyncSession,
        *,
        course_id: str,
        plan_id: str,
        item_id: str,
    ) -> LearningPlanItem:
        """页面直改入口共用的装载链：归属（课程软删 / 路径错配 404）→
        ACTIVE 版本（历史版本只读 409）→ 项存在（404）。"""
        found = await PlanService.get_with_goal(session, plan_id, expected_course_id=course_id)
        if found is None:
            raise CodedHTTPException(
                code="PLAN_NOT_FOUND",
                status_code=404,
                detail="学习计划不存在或所属课程已删除",
            )
        plan, _goal = found
        PlanItemService.require_active_plan(plan)
        item = await PlanItemService.get_for_plan(session, plan.id, item_id)
        if item is None:
            raise CodedHTTPException(
                code="PLAN_ITEM_NOT_FOUND", status_code=404, detail="计划项不存在"
            )
        return item

    @staticmethod
    async def _apply_manual_change(
        session: AsyncSession,
        *,
        course_id: str,
        plan_id: str,
        item_id: str,
        action: str,
        audit_payload: dict[str, object],
        apply: Callable[[LearningPlanItem], Awaitable[None]],
    ) -> PlanItemOut:
        """页面直改共用执行（调用方开事务）：装载链 → 领域核心 → USER_MANUAL
        审计行（spec「每次改动落 Operation 审计」），投影事务内构造。"""
        item = await PlanItemService._load_active_item_in_course(
            session, course_id=course_id, plan_id=plan_id, item_id=item_id
        )
        await apply(item)
        projection = item_out(item)
        await record_manual_audit(
            session,
            action=action,
            target=("plan_item", item.id),
            payload={"item_id": item.id, **audit_payload},
            result=projection.model_dump(mode="json"),
        )
        return projection

    @staticmethod
    async def update(
        session: AsyncSession,
        *,
        course_id: str,
        plan_id: str,
        item_id: str,
        payload: PlanItemUpdate,
    ) -> PlanItemOut:
        """HTTP 页面入口：就地编辑（即时生效 + user_locked + USER_MANUAL 审计）。"""
        changes = {
            key: value
            for key, value in payload.model_dump(exclude_unset=True, mode="json").items()
            if value is not None
        }

        async def apply(item: LearningPlanItem) -> None:
            await PlanItemService.update_core(session, item, payload)

        async with session.begin():
            return await PlanItemService._apply_manual_change(
                session,
                course_id=course_id,
                plan_id=plan_id,
                item_id=item_id,
                action="update_plan_item",
                audit_payload={"changes": changes},
                apply=apply,
            )

    @staticmethod
    async def complete(
        session: AsyncSession, *, course_id: str, plan_id: str, item_id: str
    ) -> PlanItemOut:
        """HTTP 页面入口：勾选完成（DONE + completed_at + USER_MANUAL 审计）。"""

        async def apply(item: LearningPlanItem) -> None:
            await PlanItemService.complete_core(session, item)

        async with session.begin():
            return await PlanItemService._apply_manual_change(
                session,
                course_id=course_id,
                plan_id=plan_id,
                item_id=item_id,
                action="complete_plan_item",
                audit_payload={},
                apply=apply,
            )

    @staticmethod
    async def skip(
        session: AsyncSession, *, course_id: str, plan_id: str, item_id: str
    ) -> PlanItemOut:
        """HTTP 页面入口：跳过（SKIPPED + USER_MANUAL 审计）。"""

        async def apply(item: LearningPlanItem) -> None:
            await PlanItemService.skip_core(session, item)

        async with session.begin():
            return await PlanItemService._apply_manual_change(
                session,
                course_id=course_id,
                plan_id=plan_id,
                item_id=item_id,
                action="skip_plan_item",
                audit_payload={},
                apply=apply,
            )

    @staticmethod
    async def complete_core(session: AsyncSession, item: LearningPlanItem) -> LearningPlanItem:
        """完成事务内核心：DONE + 完成时间戳（学习时长统计口径；重复完成
        保留首次时间戳，跳过后完成补写时间戳）。"""
        await PlanItemService._require_item_plan_active(session, item)
        item.status = PlanItemStatus.DONE.value
        if item.completed_at is None:
            item.completed_at = utcnow()
        item.updated_at = utcnow()
        await session.flush()
        return item

    @staticmethod
    async def skip_core(session: AsyncSession, item: LearningPlanItem) -> LearningPlanItem:
        """跳过事务内核心：SKIPPED，清完成时间戳（跳过不进学习时长统计）。"""
        await PlanItemService._require_item_plan_active(session, item)
        item.status = PlanItemStatus.SKIPPED.value
        item.completed_at = None
        item.updated_at = utcnow()
        await session.flush()
        return item


def item_out(item: LearningPlanItem) -> PlanItemOut:
    """计划项 → 投影（单项路由响应与 plan_out 共用；reason 解析失败降级 None）。"""
    return PlanItemOut(
        id=item.id,
        action_type=item.action_type,  # type: ignore[arg-type]
        content=item.content,
        record_id=item.record_id,
        concept_id=item.concept_id,
        phase_title=item.phase_title,
        priority=item.priority,
        estimated_minutes=item.estimated_minutes,
        scheduled_date=date.fromisoformat(item.scheduled_date),
        status=item.status,  # type: ignore[arg-type]
        user_locked=item.user_locked,
        completed_at=item.completed_at,
        reason=reason_of(item.reason_json),
    )


def reason_of(reason_json: str | None) -> str | None:
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
