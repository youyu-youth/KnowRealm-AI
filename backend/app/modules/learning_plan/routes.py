"""学习计划域 HTTP 路由：课程嵌套的学习目标端点（工单 01）。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.learning_plan.schemas import (
    GoalCreate,
    GoalCreateCore,
    GoalOut,
    GoalScopeSource,
    GoalStatus,
    GoalUpdate,
)
from app.modules.learning_plan.service import GoalService
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
