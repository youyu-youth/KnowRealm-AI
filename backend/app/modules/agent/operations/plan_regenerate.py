"""regenerate_plan 操作注册项（通用 Agent 第三阶段工单 03）。

「目标改了，重新排一份计划」→ regenerate_plan 工具确定性组装换代载荷
（当前版本 user_locked 项原样复制 + LLM 新草案经锁定容量感知排期器铺排，
载荷不经模型转述）→ L2 提案（确认卡预览新版本全貌）→ 用户确认 → 应用器
经 PlanService.regenerate_core：旧版 SUPERSEDED（effective_to = 换代日，
进度记录随旧版只读保留）+ 新版本 ACTIVE（spec 用户故事 15~16）。
"""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.operations.plan_confirm import (
    require_active_goal,
    require_concepts_visible,
    require_records_visible,
)
from app.modules.agent.operations.registry import (
    OperationLevel,
    OperationSpec,
    register_operation,
)
from app.modules.agent.schemas import (
    PlanLockedItemStamp,
    PlanRegeneratePayload,
    PlanRegenerateResult,
    PlanRegenerateStateSnapshot,
)
from app.modules.course.service import CourseService
from app.modules.learning_plan.models import LearningGoal, LearningPlan
from app.modules.learning_plan.service import PlanService
from app.modules.library.schemas import ProposalType
from app.shared.errors import CodedHTTPException

# 工具名（langchain @tool 注册名 = 函数名）：流式分发按名识别本工具的返回。
REGENERATE_PLAN_ACTION = "regenerate_plan"


async def build_plan_regenerate_snapshot(
    session: AsyncSession, goal: LearningGoal, active: LearningPlan
) -> PlanRegenerateStateSnapshot:
    """快照组装（提交重验 / 确认比对 / 工具派生基线三路共用）：目标约束字段 +
    ACTIVE 计划身份 + 锁定项版本戳（按 item_id 排序保证序列化稳定）。"""
    locked = sorted(
        (item for item in await PlanService.list_items(session, active.id) if item.user_locked),
        key=lambda item: item.id,
    )
    course = await CourseService.get(session, goal.course_id)
    return PlanRegenerateStateSnapshot(
        updated_at=goal.updated_at,
        title=goal.title,
        target_date=(
            date.fromisoformat(goal.target_date) if goal.target_date is not None else None
        ),
        daily_minutes=goal.daily_minutes,
        course_name=course.name if course is not None else goal.course_id,
        active_plan_version=active.plan_version,
        active_plan_updated_at=active.updated_at,
        locked_items=[
            PlanLockedItemStamp(item_id=item.id, updated_at=item.updated_at) for item in locked
        ],
    )


async def capture_plan_regenerate_state(
    session: AsyncSession, payload: PlanRegeneratePayload
) -> PlanRegenerateStateSnapshot:
    """状态读取与结构化校验（提交与确认两路共用）：

    - 目标不可达 / 非进行中 → GOAL_NOT_FOUND / GOAL_NOT_ACTIVE；
    - 无生效计划 → PLAN_NOT_FOUND（应走 generate_learning_plan 首次生成）；
    - 草案部分引用越界（record / concept）→ PLAN_DRAFT_INVALID；
    - 快照 = 目标约束字段 + 当前 ACTIVE 计划身份 + 锁定项版本戳（载荷派生后
      目标被改、版本被并发处理或锁定项变化 → 比对失效重新生成）。
    """
    goal = await require_active_goal(session, payload.goal_id)
    active = await PlanService.get_active_for_goal(session, goal.id)
    if active is None:
        raise CodedHTTPException(
            code="PLAN_NOT_FOUND",
            status_code=404,
            detail="该目标还没有生效的学习计划，请先用 generate_learning_plan 生成并确认",
        )
    await require_records_visible(session, goal.course_id, payload)
    await require_concepts_visible(session, goal.course_id, payload)
    return await build_plan_regenerate_snapshot(session, goal, active)


def resolve_plan_regenerate_target(payload: PlanRegeneratePayload) -> tuple[str, str]:
    return "goal", payload.goal_id


async def apply_plan_regenerate(
    session: AsyncSession, payload: PlanRegeneratePayload, _execution_id: str
) -> PlanRegenerateResult:
    """OP_PLAN_REGENERATE 应用器（调用方事务内）：旧版 SUPERSEDED + 新版本
    落库（锁定项原样带入，状态归 PENDING），返回换代事实投影。"""
    goal = await require_active_goal(session, payload.goal_id)
    superseded = await PlanService.get_active_for_goal(session, goal.id)
    plan = await PlanService.regenerate_core(session, goal, payload)
    items = [item for phase in payload.phases for item in phase.items if item.user_locked]
    dates = sorted(item.scheduled_date for phase in payload.phases for item in phase.items)
    return PlanRegenerateResult(
        plan_id=plan.id,
        goal_id=goal.id,
        course_id=goal.course_id,
        plan_version=plan.plan_version,
        superseded_version=superseded.plan_version if superseded is not None else None,
        item_count=len(dates),
        locked_count=len(items),
        first_date=dates[0] if dates else None,
        last_date=dates[-1] if dates else None,
    )


register_operation(
    OperationSpec(
        action=REGENERATE_PLAN_ACTION,
        proposal_type=ProposalType.OP_PLAN_REGENERATE,
        level=OperationLevel.L2,
        payload_schema=PlanRegeneratePayload,
        result_schema=PlanRegenerateResult,
        applier=apply_plan_regenerate,
        capture_state=capture_plan_regenerate_state,
        target_resolver=resolve_plan_regenerate_target,
        undo_reason="重生成是版本换代（旧版本只读保留、可随时查看），不在撤销范围",
    )
)
