from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.modules.agent.context_budget.pins import change_pins
from app.modules.agent.context_budget.retrieval import read_context, search_context
from app.modules.agent.context_budget.rules import change_rules, history_turns
from app.modules.agent.context_budget.schemas import (
    ContextHistoryOut,
    ContextPinChange,
    ContextPinsOut,
    ContextPreviewRequest,
    ContextReadOut,
    ContextReadRequest,
    ContextRuleChange,
    ContextRulesOut,
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


@router.post("/api/chat-sessions/{session_id}/context/pins", response_model=ContextPinsOut)
async def update_pins(session_id: UUID, body: ContextPinChange, request: Request) -> ContextPinsOut:
    return await change_pins(request.app.state.session_factory, str(session_id), body)


@router.post("/api/chat-sessions/{session_id}/context/rules", response_model=ContextRulesOut)
async def update_rules(
    session_id: UUID, body: ContextRuleChange, request: Request
) -> ContextRulesOut:
    return await change_rules(request.app.state.session_factory, str(session_id), body)


@router.get("/api/chat-sessions/{session_id}/context/history", response_model=ContextHistoryOut)
async def get_history(
    session_id: UUID,
    request: Request,
    offset: int = Query(default=0, ge=0),
    expected_version: int | None = Query(default=None, ge=1),
) -> ContextHistoryOut:
    return await history_turns(
        request.app.state.session_factory, str(session_id), offset, expected_version
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
