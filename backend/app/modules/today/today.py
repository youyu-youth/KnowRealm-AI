from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.today.schemas import TodayStatsOut, TodaySummaryTodoOut, TodayTrendPointOut
from app.modules.today.service import TodayService
from app.shared.deps import get_db, require_launch_token
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


@router.get("/pending-summaries", response_model=list[TodaySummaryTodoOut])
async def list_pending_summaries(
    session: AsyncSession = Depends(get_db),
) -> list[TodaySummaryTodoOut]:
    return await TodayService.list_pending_summaries(session)


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
        raise HTTPException(status_code=422, detail="INVALID_TREND_DAYS：days 仅支持 7 或 30")
    return await TodayService.stats_trend(session, days)
