from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_launch_token
from app.schemas.course import ErrorResponse
from app.schemas.todo import (
    TodoOut,
    TodoReadOut,
    TodoToggleRequest,
    TodoWriteRequest,
)
from app.services.todo_service import TodoService

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
