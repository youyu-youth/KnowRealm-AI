from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_launch_token
from app.schemas.course import ErrorResponse
from app.schemas.document import ProcessingJobOut
from app.services.processing_job_service import ProcessingJobService

router = APIRouter(
    prefix="/api/processing-jobs",
    tags=["processing-jobs"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@router.get("/{job_id}", response_model=ProcessingJobOut)
async def get_processing_job(
    job_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> ProcessingJobOut:
    job = await ProcessingJobService.get(session, str(job_id))
    if job is None:
        raise HTTPException(status_code=404, detail="处理任务不存在")
    return ProcessingJobService.to_out(job)
