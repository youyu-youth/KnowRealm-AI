from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_launch_token
from app.schemas.course import ErrorResponse
from app.schemas.knowledge_point import KnowledgePointJobAccepted, KnowledgePointReadOut
from app.services.knowledge_point_service import KnowledgePointService

router = APIRouter(
    prefix="/api/records",
    tags=["knowledge-points"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@router.get("/{record_id}/knowledge-points", response_model=KnowledgePointReadOut)
async def get_knowledge_points(
    record_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> KnowledgePointReadOut:
    return await KnowledgePointService.read(session, request.app.state.data_dir, str(record_id))


@router.post(
    "/{record_id}/knowledge-point-jobs",
    response_model=KnowledgePointJobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_knowledge_point_job(
    record_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> KnowledgePointJobAccepted:
    job_id = await KnowledgePointService.submit(
        session,
        request.app.state.data_dir,
        str(record_id),
    )
    return KnowledgePointJobAccepted(job_id=job_id)
