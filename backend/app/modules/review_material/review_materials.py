from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.review_material.schemas import (
    ReviewMaterialAdjustRequest,
    ReviewMaterialContent,
    ReviewMaterialJobAccepted,
    ReviewMaterialOut,
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


@router.post(
    "/{record_id}/review-material-adjustments",
    response_model=ReviewMaterialJobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def adjust_review_material(
    record_id: UUID,
    body: ReviewMaterialAdjustRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ReviewMaterialJobAccepted:
    job_id = await ReviewMaterialService.adjust(
        session,
        request.app.state.data_dir,
        str(record_id),
        body,
    )
    return ReviewMaterialJobAccepted(job_id=job_id)


@router.post(
    "/{record_id}/review-material-confirmations",
    response_model=ReviewMaterialOut,
)
async def confirm_review_material(
    record_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ReviewMaterialOut:
    material = await ReviewMaterialService.confirm(session, str(record_id))
    await request.app.state.record_notifier.notify(str(record_id))
    return material


@router.patch("/{record_id}/review-material", response_model=ReviewMaterialOut)
async def edit_review_material(
    record_id: UUID,
    body: ReviewMaterialContent,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ReviewMaterialOut:
    material = await ReviewMaterialService.edit(session, str(record_id), body)
    await request.app.state.record_notifier.notify(str(record_id))
    return material


@router.get("/{record_id}/review-materials", response_model=list[ReviewMaterialOut])
async def list_review_materials(
    record_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> list[ReviewMaterialOut]:
    return await ReviewMaterialService.list_versions(session, str(record_id))
