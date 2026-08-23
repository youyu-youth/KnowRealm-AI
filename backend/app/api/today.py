from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_launch_token
from app.schemas.course import ErrorResponse
from app.schemas.today import TodaySummaryTodoOut
from app.services.today_service import TodayService

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
