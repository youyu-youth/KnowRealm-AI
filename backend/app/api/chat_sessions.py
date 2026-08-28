from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_launch_token
from app.schemas.chat import ChatSessionCreate, ChatSessionOut, ChatSessionRename
from app.schemas.course import ErrorResponse
from app.services.chat_session_service import ChatSessionService

router = APIRouter(
    prefix="/api/chat-sessions",
    tags=["chat-sessions"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@router.post("", response_model=ChatSessionOut, status_code=201)
async def create_chat_session(
    payload: ChatSessionCreate,
    session: AsyncSession = Depends(get_db),
) -> ChatSessionOut:
    chat = await ChatSessionService.create_free(session)
    return ChatSessionOut.model_validate(chat)


@router.get("", response_model=list[ChatSessionOut])
async def list_chat_sessions(
    session: AsyncSession = Depends(get_db),
) -> list[ChatSessionOut]:
    chats = await ChatSessionService.list(session)
    return [ChatSessionOut.model_validate(chat) for chat in chats]


@router.get("/{session_id}", response_model=ChatSessionOut)
async def get_chat_session(
    session_id: str,
    session: AsyncSession = Depends(get_db),
) -> ChatSessionOut:
    chat = await ChatSessionService.get(session, session_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="对话不存在或已删除")
    return ChatSessionOut.model_validate(chat)


@router.patch("/{session_id}", response_model=ChatSessionOut)
async def rename_chat_session(
    session_id: str,
    payload: ChatSessionRename,
    session: AsyncSession = Depends(get_db),
) -> ChatSessionOut:
    chat = await ChatSessionService.rename(session, session_id, payload.title)
    if chat is None:
        raise HTTPException(status_code=404, detail="对话不存在或已删除")
    return ChatSessionOut.model_validate(chat)


@router.delete("/{session_id}", status_code=204, response_class=Response, response_model=None)
async def delete_chat_session(
    session_id: str,
    session: AsyncSession = Depends(get_db),
) -> Response:
    if not await ChatSessionService.soft_delete(session, session_id):
        raise HTTPException(status_code=404, detail="对话不存在或已删除")
    return Response(status_code=204)
