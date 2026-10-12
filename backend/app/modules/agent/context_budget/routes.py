from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.modules.agent.context_budget.schemas import ContextPreviewRequest, ContextViewOut
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
