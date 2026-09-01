from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.jobs.schemas import ProcessingJobOut, ProcessingJobRetryRequest
from app.modules.jobs.service import ProcessingJobService
from app.modules.record import RecordService
from app.shared.deps import get_db, require_launch_token
from app.shared.schemas import ErrorResponse

router = APIRouter(
    prefix="/api/processing-jobs",
    tags=["processing-jobs"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
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
    if job is None or await RecordService.get(session, str(job.record_id)) is None:
        raise HTTPException(status_code=404, detail="处理任务不存在")
    return ProcessingJobService.to_out(job)


@router.post("/{job_id}/retries", status_code=202, response_model=ProcessingJobOut)
async def retry_processing_job(
    job_id: UUID,
    body: ProcessingJobRetryRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ProcessingJobOut:
    job = await ProcessingJobService.retry(session, str(job_id), str(body.record_id))
    await request.app.state.record_notifier.notify(str(body.record_id))
    return job
