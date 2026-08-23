from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_launch_token
from app.schemas.course import ErrorResponse
from app.schemas.summary import SummaryJobAccepted, SummaryReadOut
from app.services.summary_service import SummaryService

router = APIRouter(
    prefix="/api/records",
    tags=["summaries"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@router.get("/{record_id}/summary", response_model=SummaryReadOut)
async def get_summary(
    record_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> SummaryReadOut:
    return await SummaryService.read(session, request.app.state.data_dir, str(record_id))


@router.post(
    "/{record_id}/summary-jobs",
    response_model=SummaryJobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_summary(
    record_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> SummaryJobAccepted:
    submitted = await SummaryService.submit(session, request.app.state.data_dir, str(record_id))
    return SummaryJobAccepted(job_id=submitted.job_id)
