from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette import EventSourceResponse

from app.api.deps import get_db, require_launch_token
from app.schemas.chat import (
    ChatMessageCreate,
    ChatMessageOut,
    ChatRecordOption,
    ChatSessionCreate,
    ChatSessionOut,
    ChatSessionRename,
)
from app.schemas.course import ErrorResponse
from app.services.chat_message_service import ChatMessageService
from app.services.chat_session_service import ChatSessionService

router = APIRouter(
    prefix="/api/chat-sessions",
    tags=["chat-sessions"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@router.post("", response_model=ChatSessionOut, status_code=201)
async def create_chat_session(
    payload: ChatSessionCreate,
    session: AsyncSession = Depends(get_db),
) -> ChatSessionOut:
    chat = await ChatSessionService.create(
        session, record_id=str(payload.record_id) if payload.record_id is not None else None
    )
    return ChatSessionOut.model_validate(chat)


@router.get("", response_model=list[ChatSessionOut])
async def list_chat_sessions(
    session: AsyncSession = Depends(get_db),
) -> list[ChatSessionOut]:
    chats = await ChatSessionService.list(session)
    return [ChatSessionOut.model_validate(chat) for chat in chats]


@router.get("/record-options", response_model=list[ChatRecordOption])
async def list_chat_record_options(
    session: AsyncSession = Depends(get_db),
) -> list[ChatRecordOption]:
    return await ChatSessionService.record_options(session)


@router.get("/{session_id}", response_model=ChatSessionOut)
async def get_chat_session(
    session_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> ChatSessionOut:
    chat = await ChatSessionService.get(session, str(session_id))
    if chat is None:
        raise HTTPException(status_code=404, detail="对话不存在或已删除")
    return ChatSessionOut.model_validate(chat)


@router.patch("/{session_id}", response_model=ChatSessionOut)
async def rename_chat_session(
    session_id: UUID,
    payload: ChatSessionRename,
    session: AsyncSession = Depends(get_db),
) -> ChatSessionOut:
    chat = await ChatSessionService.rename(session, str(session_id), payload.title)
    if chat is None:
        raise HTTPException(status_code=404, detail="对话不存在或已删除")
    return ChatSessionOut.model_validate(chat)


@router.delete("/{session_id}", status_code=204, response_class=Response, response_model=None)
async def delete_chat_session(
    session_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> Response:
    if not await ChatSessionService.soft_delete(session, str(session_id)):
        raise HTTPException(status_code=404, detail="对话不存在或已删除")
    return Response(status_code=204)


@router.get("/{session_id}/messages", response_model=list[ChatMessageOut])
async def list_chat_messages(
    session_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> list[ChatMessageOut]:
    messages = await ChatMessageService.list_messages(session, str(session_id))
    if messages is None:
        raise HTTPException(status_code=404, detail="对话不存在或已删除")
    return [ChatMessageOut.model_validate(message) for message in messages]


@router.post("/{session_id}/messages", response_class=EventSourceResponse)
async def send_chat_message(
    session_id: UUID,
    payload: ChatMessageCreate,
    request: Request,
) -> EventSourceResponse:
    """发送用户消息并流式返回回答（SSE：status → token… → done / error）。"""
    app = request.app
    accepted = await ChatMessageService.accept(
        session_factory=app.state.session_factory,
        data_dir=app.state.data_dir,
        registry=app.state.chat_stream_registry,
        session_id=str(session_id),
        content=payload.content,
    )
    return EventSourceResponse(
        ChatMessageService.stream_events(
            session_factory=app.state.session_factory,
            checkpointer=app.state.chat_checkpointer,
            registry=app.state.chat_stream_registry,
            accepted=accepted,
        )
    )
