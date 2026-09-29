"""学习计划域 HTTP 路由：课程嵌套的学习目标（工单 01）与计划端点（工单 03）。

计划端点 = 计划 Tab 的读取面（版本列表 / 版本详情，历史版本只读）与执行面
（项级编辑 / 完成 / 跳过，仅当前生效版本）。页面直改即时生效（spec 用户
故事 14），每次改动经 audit 钩子落 Operation 审计行（trigger=USER_MANUAL）。
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.learning_plan.audit import record_manual_audit
from app.modules.learning_plan.models import LearningGoal, LearningPlan
from app.modules.learning_plan.schemas import (
    GoalCreate,
    GoalCreateCore,
    GoalOut,
    GoalScopeSource,
    GoalStatus,
    GoalUpdate,
    PlanItemOut,
    PlanItemUpdate,
    PlanOut,
    PlanVersionOut,
)
from app.modules.learning_plan.service import (
    GoalService,
    PlanItemService,
    PlanService,
    item_out,
)
from app.shared.deps import get_db, require_launch_token
from app.shared.errors import CodedHTTPException
from app.shared.schemas import ErrorResponse

router = APIRouter(
    prefix="/api/courses",
    tags=["goals"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@router.get("/{course_id}/goals", response_model=list[GoalOut])
async def list_course_goals(
    course_id: str,
    session: AsyncSession = Depends(get_db),
) -> list[GoalOut]:
    goals = await GoalService.list_for_course(session, course_id)
    if goals is None:
        raise CodedHTTPException(
            code="COURSE_NOT_FOUND", status_code=404, detail="课程不存在或已删除"
        )
    return [GoalOut.model_validate(goal) for goal in goals]


@router.post("/{course_id}/goals", response_model=GoalOut, status_code=201)
async def create_course_goal(
    course_id: str,
    payload: GoalCreate,
    session: AsyncSession = Depends(get_db),
) -> GoalOut:
    """页面入口创建目标：恒为用户确认范围（spec：AI 推断范围只经 Agent 确认卡）。"""
    goal = await GoalService.create(
        session,
        course_id,
        GoalCreateCore(
            **payload.model_dump(),
            scope_source=GoalScopeSource.USER_CONFIRMED,
            scope_confirmed=True,
        ),
    )
    if goal is None:
        raise CodedHTTPException(
            code="COURSE_NOT_FOUND", status_code=404, detail="课程不存在或已删除"
        )
    return GoalOut.model_validate(goal)


@router.patch("/{course_id}/goals/{goal_id}", response_model=GoalOut)
async def update_course_goal(
    course_id: str,
    goal_id: str,
    payload: GoalUpdate,
    session: AsyncSession = Depends(get_db),
) -> GoalOut:
    goal = await GoalService.update(session, goal_id, payload, expected_course_id=course_id)
    if goal is None:
        raise CodedHTTPException(code="GOAL_NOT_FOUND", status_code=404, detail="学习目标不存在")
    return GoalOut.model_validate(goal)


@router.post("/{course_id}/goals/{goal_id}/complete", response_model=GoalOut)
async def complete_course_goal(
    course_id: str,
    goal_id: str,
    session: AsyncSession = Depends(get_db),
) -> GoalOut:
    goal = await GoalService.set_status(
        session, goal_id, GoalStatus.COMPLETED, expected_course_id=course_id
    )
    if goal is None:
        raise CodedHTTPException(code="GOAL_NOT_FOUND", status_code=404, detail="学习目标不存在")
    return GoalOut.model_validate(goal)


@router.post("/{course_id}/goals/{goal_id}/archive", response_model=GoalOut)
async def archive_course_goal(
    course_id: str,
    goal_id: str,
    session: AsyncSession = Depends(get_db),
) -> GoalOut:
    goal = await GoalService.set_status(
        session, goal_id, GoalStatus.ARCHIVED, expected_course_id=course_id
    )
    if goal is None:
        raise CodedHTTPException(code="GOAL_NOT_FOUND", status_code=404, detail="学习目标不存在")
    return GoalOut.model_validate(goal)


# ---------------------------------------------------------------------------
# 计划端点（工单 03）：计划 Tab 读取面 + 项级执行面（页面直改，即时生效）。
# ---------------------------------------------------------------------------


def _plan_not_found() -> CodedHTTPException:
    return CodedHTTPException(
        code="PLAN_NOT_FOUND", status_code=404, detail="学习计划不存在或所属课程已删除"
    )


async def _load_plan(
    session: AsyncSession, course_id: str, plan_id: str
) -> tuple[LearningPlan, LearningGoal]:
    found = await PlanService.get_with_goal(session, plan_id, expected_course_id=course_id)
    if found is None:
        raise _plan_not_found()
    return found


@router.get("/{course_id}/plans", response_model=list[PlanVersionOut])
async def list_course_plans(
    course_id: str,
    goal_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> list[PlanVersionOut]:
    """目标的计划版本列表（新版本在前；历史版本只读，供计划 Tab 切换查看）。"""
    goal = await GoalService.get(session, str(goal_id))
    if goal is None or goal.course_id != course_id:
        raise CodedHTTPException(code="GOAL_NOT_FOUND", status_code=404, detail="学习目标不存在")
    versions = await PlanService.list_versions_for_goal(session, goal.id)
    return [
        PlanService.version_out(plan, course_id=course_id, item_count=count)
        for plan, count in versions
    ]


@router.get("/{course_id}/plans/{plan_id}", response_model=PlanOut)
async def get_course_plan(
    course_id: str,
    plan_id: str,
    session: AsyncSession = Depends(get_db),
) -> PlanOut:
    """计划版本详情（含全部计划项与进度状态，任意版本只读）。"""
    plan, _goal = await _load_plan(session, course_id, plan_id)
    items = await PlanService.list_items(session, plan.id)
    return PlanService.plan_out(plan, items, course_id=course_id)


async def _mutate_item(
    session: AsyncSession,
    course_id: str,
    plan_id: str,
    item_id: str,
    action: str,
    payload: dict[str, Any],
    apply: Any,
) -> PlanItemOut:
    """项级页面直改共用：归属链 + ACTIVE 版本校验 → 领域核心 → USER_MANUAL
    审计行（同一事务，spec「每次改动落 Operation 审计」）。

    apply 回调接收项行并执行领域核心（编辑 / 完成 / 跳过）；投影在事务内
    构造，提交后返回。
    """
    async with session.begin():
        plan, _goal = await _load_plan(session, course_id, plan_id)
        PlanItemService.require_active_plan(plan)
        item = await PlanItemService.get_for_plan(session, plan.id, item_id)
        if item is None:
            raise CodedHTTPException(
                code="PLAN_ITEM_NOT_FOUND", status_code=404, detail="计划项不存在"
            )
        await apply(item)
        projection = item_out(item)
        await record_manual_audit(
            session,
            action=action,
            target=("plan_item", item.id),
            payload={"item_id": item.id, **payload},
            result=projection.model_dump(mode="json"),
        )
    return projection


@router.patch("/{course_id}/plans/{plan_id}/items/{item_id}", response_model=PlanItemOut)
async def update_plan_item_row(
    course_id: str,
    plan_id: str,
    item_id: str,
    payload: PlanItemUpdate,
    session: AsyncSession = Depends(get_db),
) -> PlanItemOut:
    """就地编辑计划项（日期 / 时长 / 内容，仅当前生效版本）：即时生效，
    Service 置 user_locked（重生成原样保留）。"""

    async def apply(item: Any) -> None:
        await PlanItemService.update_core(session, item, payload)

    return await _mutate_item(
        session,
        course_id,
        plan_id,
        item_id,
        "update_plan_item",
        {"changes": payload.model_dump(exclude_unset=True, mode="json")},
        apply,
    )


@router.post("/{course_id}/plans/{plan_id}/items/{item_id}/complete", response_model=PlanItemOut)
async def complete_plan_item_row(
    course_id: str,
    plan_id: str,
    item_id: str,
    session: AsyncSession = Depends(get_db),
) -> PlanItemOut:
    """勾选完成：DONE + 完成时间戳（学习时长统计口径，不进学习证据链）。"""

    async def apply(item: Any) -> None:
        await PlanItemService.complete_core(session, item)

    return await _mutate_item(session, course_id, plan_id, item_id, "complete_plan_item", {}, apply)


@router.post("/{course_id}/plans/{plan_id}/items/{item_id}/skip", response_model=PlanItemOut)
async def skip_plan_item_row(
    course_id: str,
    plan_id: str,
    item_id: str,
    session: AsyncSession = Depends(get_db),
) -> PlanItemOut:
    """跳过计划项：SKIPPED，清完成时间戳（跳过不进学习时长统计）。"""

    async def apply(item: Any) -> None:
        await PlanItemService.skip_core(session, item)

    return await _mutate_item(session, course_id, plan_id, item_id, "skip_plan_item", {}, apply)
