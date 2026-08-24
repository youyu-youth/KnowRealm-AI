from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_launch_token
from app.schemas.course import ErrorResponse
from app.schemas.knowledge_point import (
    KnowledgePointJobAccepted,
    KnowledgePointOut,
    KnowledgePointReadOut,
    KnowledgePointWriteRequest,
)
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
    include: Literal["superseded"] | None = Query(default=None),
) -> KnowledgePointReadOut:
    return await KnowledgePointService.read(
        session,
        request.app.state.data_dir,
        str(record_id),
        include_superseded=include == "superseded",
    )


@router.post(
    "/{record_id}/knowledge-points",
    response_model=KnowledgePointOut,
    status_code=201,
)
async def create_knowledge_point(
    record_id: UUID,
    body: KnowledgePointWriteRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> KnowledgePointOut:
    item = await KnowledgePointService.create(session, str(record_id), body)
    await request.app.state.record_notifier.notify(str(record_id))
    return item


@router.patch(
    "/{record_id}/knowledge-points/{item_id}",
    response_model=KnowledgePointOut,
)
async def update_knowledge_point(
    record_id: UUID,
    item_id: UUID,
    body: KnowledgePointWriteRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> KnowledgePointOut:
    item = await KnowledgePointService.update(session, str(record_id), str(item_id), body)
    await request.app.state.record_notifier.notify(str(record_id))
    return item


@router.delete(
    "/{record_id}/knowledge-points/{item_id}",
    status_code=204,
    response_class=Response,
    response_model=None,
)
async def delete_knowledge_point(
    record_id: UUID,
    item_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    await KnowledgePointService.delete(session, str(record_id), str(item_id))
    await request.app.state.record_notifier.notify(str(record_id))
    return Response(status_code=204)


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


@router.post(
    "/{record_id}/knowledge-point-batches/{batch_id}/confirmations",
    response_model=KnowledgePointReadOut,
)
async def confirm_knowledge_point_batch(
    record_id: UUID,
    batch_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> KnowledgePointReadOut:
    result = await KnowledgePointService.confirm(
        session,
        request.app.state.data_dir,
        str(record_id),
        str(batch_id),
    )
    await request.app.state.record_notifier.notify(str(record_id))
    return result


@router.post(
    "/{record_id}/knowledge-point-batches/{batch_id}/discards",
    response_model=KnowledgePointReadOut,
)
async def discard_knowledge_point_batch(
    record_id: UUID,
    batch_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> KnowledgePointReadOut:
    result = await KnowledgePointService.discard(
        session,
        request.app.state.data_dir,
        str(record_id),
        str(batch_id),
    )
    await request.app.state.record_notifier.notify(str(record_id))
    return result
