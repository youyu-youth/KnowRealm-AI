from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.library.shared_refs import REQUEST_COURSE_ID
from app.modules.summary.schemas import (
    SummaryAdjustRequest,
    SummaryConfirmOut,
    SummaryConfirmRequest,
    SummaryJobAccepted,
    SummaryOut,
    SummaryReadOut,
)
from app.modules.summary.service import SummaryService
from app.shared.deps import get_db, require_launch_token
from app.shared.schemas import ErrorResponse

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
    course_id: REQUEST_COURSE_ID = None,
) -> SummaryJobAccepted:
    submitted = await SummaryService.submit(
        session,
        request.app.state.data_dir,
        str(record_id),
        request_course_id=None if course_id is None else str(course_id),
    )
    return SummaryJobAccepted(job_id=submitted.job_id)


@router.post(
    "/{record_id}/summary-adjustments",
    response_model=SummaryJobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def adjust_summary(
    record_id: UUID,
    body: SummaryAdjustRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> SummaryJobAccepted:
    submitted = await SummaryService.adjust(
        session,
        request.app.state.data_dir,
        str(record_id),
        body,
    )
    return SummaryJobAccepted(job_id=submitted.job_id)


@router.post("/{record_id}/summary-confirmations", response_model=SummaryConfirmOut)
async def confirm_summary(
    record_id: UUID,
    body: SummaryConfirmRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> SummaryConfirmOut:
    result = await SummaryService.confirm(session, str(record_id), body)
    await request.app.state.record_notifier.notify(str(record_id))
    return result


@router.get("/{record_id}/summaries", response_model=list[SummaryOut])
async def list_summaries(
    record_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> list[SummaryOut]:
    return await SummaryService.list_versions(session, str(record_id))


@router.get("/{record_id}/summaries/{summary_id}", response_model=SummaryOut)
async def get_summary_version(
    record_id: UUID,
    summary_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> SummaryOut:
    return await SummaryService.get_version(session, str(record_id), str(summary_id))
