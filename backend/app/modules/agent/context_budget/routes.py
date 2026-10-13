from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.modules.agent.context_budget.retrieval import read_context, search_context
from app.modules.agent.context_budget.schemas import (
    ContextPreviewRequest,
    ContextReadOut,
    ContextReadRequest,
    ContextSearchOut,
    ContextSearchRequest,
    ContextViewOut,
)
from app.modules.agent.context_budget.service import view_context
from app.shared.deps import require_launch_token
from app.shared.schemas import ErrorResponse

router = APIRouter(
    tags=["chat-context"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)


@router.get("/api/chat-sessions/{session_id}/context", response_model=ContextViewOut)
async def get_context(session_id: UUID, request: Request) -> ContextViewOut:
    return await view_context(
        request.app.state.session_factory,
        request.app.state.data_dir,
        str(session_id),
        ContextPreviewRequest(),
    )


@router.post("/api/chat-sessions/{session_id}/context/estimates", response_model=ContextViewOut)
async def preview_context(
    session_id: UUID, body: ContextPreviewRequest, request: Request
) -> ContextViewOut:
    return await view_context(
        request.app.state.session_factory, request.app.state.data_dir, str(session_id), body
    )


@router.post(
    "/api/chat-sessions/{session_id}/context/sources/search", response_model=ContextSearchOut
)
async def search_sources(
    session_id: UUID, body: ContextSearchRequest, request: Request
) -> ContextSearchOut:
    return await search_context(request.app.state.session_factory, str(session_id), body)


@router.post("/api/chat-sessions/{session_id}/context/sources/read", response_model=ContextReadOut)
async def read_source(
    session_id: UUID, body: ContextReadRequest, request: Request
) -> ContextReadOut:
    return await read_context(request.app.state.session_factory, str(session_id), body)
