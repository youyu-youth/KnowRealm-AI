from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.todo import (
    TodoConflictResponse,
    TodoJobAccepted,
    TodoOut,
    TodoReadOut,
    TodoToggleRequest,
    TodoWriteRequest,
)
from app.services.todo_service import TodoAdoptionBlocked, TodoService
from app.shared.deps import get_db, require_launch_token
from app.shared.schemas import ErrorResponse

router = APIRouter(
    prefix="/api/records",
    tags=["todos"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@router.get("/{record_id}/todos", response_model=TodoReadOut)
async def get_todos(
    record_id: UUID,
    request: Request,
    include: Literal["superseded"] | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> TodoReadOut:
    return await TodoService.read(
        session,
        request.app.state.data_dir,
        str(record_id),
        include_superseded=include == "superseded",
    )


@router.post(
    "/{record_id}/todo-jobs",
    response_model=TodoJobAccepted,
    status_code=202,
)
async def submit_todo_job(
    record_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> TodoJobAccepted:
    job_id = await TodoService.submit(session, request.app.state.data_dir, str(record_id))
    await request.app.state.record_notifier.notify(str(record_id))
    return TodoJobAccepted(job_id=job_id)


@router.post(
    "/{record_id}/todo-batches/{batch_id}/discards",
    response_model=TodoReadOut,
)
async def discard_todo_batch(
    record_id: UUID,
    batch_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> TodoReadOut:
    result = await TodoService.discard(
        session, request.app.state.data_dir, str(record_id), str(batch_id)
    )
    await request.app.state.record_notifier.notify(str(record_id))
    return result


@router.post(
    "/{record_id}/todo-batches/{batch_id}/confirmations",
    response_model=TodoReadOut,
    responses={409: {"model": TodoConflictResponse}},
)
async def adopt_todo_batch(
    record_id: UUID,
    batch_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> TodoReadOut | JSONResponse:
    try:
        result = await TodoService.adopt(
            session, request.app.state.data_dir, str(record_id), str(batch_id)
        )
    except TodoAdoptionBlocked as error:
        body = TodoConflictResponse(detail=error.detail, blocked_reason=error.blocked_reason)
        return JSONResponse(status_code=409, content=body.model_dump(mode="json"))
    await request.app.state.record_notifier.notify(str(record_id))
    return result


@router.post(
    "/{record_id}/todos",
    response_model=TodoOut,
    status_code=201,
)
async def create_todo(
    record_id: UUID,
    body: TodoWriteRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> TodoOut:
    item = await TodoService.create(session, str(record_id), body)
    await request.app.state.record_notifier.notify(str(record_id))
    return item


@router.patch(
    "/{record_id}/todos/{todo_id}",
    response_model=TodoOut,
)
async def update_todo(
    record_id: UUID,
    todo_id: UUID,
    body: TodoWriteRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> TodoOut:
    item = await TodoService.update(session, str(record_id), str(todo_id), body)
    await request.app.state.record_notifier.notify(str(record_id))
    return item


@router.delete(
    "/{record_id}/todos/{todo_id}",
    status_code=204,
    response_class=Response,
    response_model=None,
)
async def delete_todo(
    record_id: UUID,
    todo_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    await TodoService.delete(session, str(record_id), str(todo_id))
    await request.app.state.record_notifier.notify(str(record_id))
    return Response(status_code=204)


@router.post(
    "/{record_id}/todos/{todo_id}/toggles",
    response_model=TodoOut,
)
async def toggle_todo(
    record_id: UUID,
    todo_id: UUID,
    body: TodoToggleRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> TodoOut:
    item = await TodoService.toggle(session, str(record_id), str(todo_id), body)
    await request.app.state.record_notifier.notify(str(record_id))
    return item
