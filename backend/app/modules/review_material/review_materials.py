from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.review_material.schemas import (
    ReviewMaterialJobAccepted,
    ReviewMaterialReadOut,
)
from app.modules.review_material.service import ReviewMaterialService
from app.shared.deps import get_db, require_launch_token
from app.shared.schemas import ErrorResponse

router = APIRouter(
    prefix="/api/records",
    tags=["review-materials"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@router.get("/{record_id}/review-material", response_model=ReviewMaterialReadOut)
async def get_review_material(
    record_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ReviewMaterialReadOut:
    return await ReviewMaterialService.read(session, request.app.state.data_dir, str(record_id))


@router.post(
    "/{record_id}/review-material-jobs",
    response_model=ReviewMaterialJobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_review_material(
    record_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ReviewMaterialJobAccepted:
    job_id = await ReviewMaterialService.submit(
        session,
        request.app.state.data_dir,
        str(record_id),
    )
    return ReviewMaterialJobAccepted(job_id=job_id)
