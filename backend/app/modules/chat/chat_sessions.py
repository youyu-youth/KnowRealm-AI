from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette import EventSourceResponse

from app.modules.chat.message_service import ChatMessageService
from app.modules.chat.schemas import (
    ChatMessageCreate,
    ChatMessageOut,
    ChatRecordOption,
    ChatSessionCreate,
    ChatSessionOut,
    ChatSessionRename,
)
from app.modules.chat.session_service import ChatSessionService
from app.shared.deps import get_db, require_launch_token
from app.shared.schemas import ErrorResponse

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
        session,
        record_id=str(payload.record_id) if payload.record_id is not None else None,
        knowledge_point_id=(
            str(payload.knowledge_point_id) if payload.knowledge_point_id is not None else None
        ),
    )
    # 创建时挂载记录已校验存活，失效态恒为 False。
    return ChatSessionService.to_out(chat)


@router.get("", response_model=list[ChatSessionOut])
async def list_chat_sessions(
    session: AsyncSession = Depends(get_db),
) -> list[ChatSessionOut]:
    return await ChatSessionService.list_out(session)


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
    chat = await ChatSessionService.get_out(session, str(session_id))
    if chat is None:
        raise HTTPException(status_code=404, detail="对话不存在或已删除")
    return chat


@router.patch("/{session_id}", response_model=ChatSessionOut)
async def rename_chat_session(
    session_id: UUID,
    payload: ChatSessionRename,
    session: AsyncSession = Depends(get_db),
) -> ChatSessionOut:
    renamed = await ChatSessionService.rename(session, str(session_id), payload.title)
    if renamed is None:
        raise HTTPException(status_code=404, detail="对话不存在或已删除")
    out = await ChatSessionService.get_out(session, str(session_id))
    if out is None:
        raise HTTPException(status_code=404, detail="对话不存在或已删除")
    return out


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
