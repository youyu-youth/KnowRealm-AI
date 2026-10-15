from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.today.asset_schemas import AssetType, RecentAssetListOut
from app.modules.today.recent_assets import RecentAssetService
from app.modules.today.resume import LearningResumeService
from app.modules.today.resume_schemas import LearningResumeOut, LearningResumeUpdate, ResumeKind
from app.modules.today.schemas import (
    TodayPlanItemOut,
    TodayProgressOut,
    TodayStatsOut,
    TodaySummaryTodoOut,
    TodayTrendPointOut,
)
from app.modules.today.service import TodayService
from app.shared.deps import get_db, require_launch_token
from app.shared.errors import CodedHTTPException
from app.shared.schemas import ErrorResponse

router = APIRouter(
    prefix="/api/today",
    tags=["today"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@router.get("/recent-assets", response_model=RecentAssetListOut)
async def list_recent_assets(
    asset_type: AssetType | None = None,
    course_id: UUID | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=5, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> RecentAssetListOut:
    return await RecentAssetService.list_recent(
        session,
        asset_type=asset_type,
        course_id=str(course_id) if course_id is not None else None,
        offset=offset,
        limit=limit,
    )


@router.get("/progress", response_model=TodayProgressOut)
async def get_progress(
    course_id: UUID | None = None,
    order: Literal["date", "duration"] = "date",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> TodayProgressOut:
    return await TodayService.progress(
        session,
        course_id=str(course_id) if course_id is not None else None,
        order=order,
        offset=offset,
        limit=limit,
    )


@router.get("/continue-learning", response_model=list[LearningResumeOut])
async def list_continue_learning(
    limit: int = Query(default=3, ge=1, le=30),
    session: AsyncSession = Depends(get_db),
) -> list[LearningResumeOut]:
    return (await LearningResumeService.list_recent(session))[:limit]


@router.put(
    "/continue-learning",
    status_code=204,
    response_model=None,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def record_learning_visit(
    body: LearningResumeUpdate, session: AsyncSession = Depends(get_db)
) -> None:
    await LearningResumeService.visit(session, body)


@router.delete("/continue-learning", status_code=204, response_model=None)
async def clear_continue_learning(session: AsyncSession = Depends(get_db)) -> None:
    await LearningResumeService.remove(session)


@router.delete("/continue-learning/{kind}/{target_id}", status_code=204, response_model=None)
async def remove_continue_learning(
    kind: ResumeKind, target_id: UUID, session: AsyncSession = Depends(get_db)
) -> None:
    await LearningResumeService.remove(session, kind=kind, target_id=str(target_id))


@router.get("/pending-summaries", response_model=list[TodaySummaryTodoOut])
async def list_pending_summaries(
    session: AsyncSession = Depends(get_db),
) -> list[TodaySummaryTodoOut]:
    return await TodayService.list_pending_summaries(session)


@router.get("/plan-items", response_model=list[TodayPlanItemOut])
async def list_due_plan_items(
    session: AsyncSession = Depends(get_db),
) -> list[TodayPlanItemOut]:
    """今日待学的计划项（跨空间，工单 04）：排期日 ≤ 今天且未完成，含逾期限期
    催办；勾选完成走课程嵌套计划项端点（与计划 Tab 状态一致）。"""
    return await TodayService.list_due_plan_items(session)


@router.get("/stats", response_model=TodayStatsOut)
async def get_stats(session: AsyncSession = Depends(get_db)) -> TodayStatsOut:
    return await TodayService.stats(session)


@router.get("/stats/trend", response_model=list[TodayTrendPointOut])
async def get_stats_trend(
    days: int,
    session: AsyncSession = Depends(get_db),
) -> list[TodayTrendPointOut]:
    # 查询参数白名单校验：pydantic Literal 不做查询串的 str→int 强转，走业务 422。
    if days not in (7, 30):
        raise CodedHTTPException(
            code="INVALID_TREND_DAYS",
            status_code=422,
            detail="INVALID_TREND_DAYS：days 仅支持 7 或 30",
        )
    return await TodayService.stats_trend(session, days)
