from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette import EventSourceResponse

from app.modules.agent.message_service import ChatMessageService
from app.modules.agent.schemas import (
    ChatKnowledgePointSaveRequest,
    ChatMessageCreate,
    ChatMessageOut,
    ChatRecordOption,
    ChatScope,
    ChatSessionCreate,
    ChatSessionOut,
    ChatSessionRename,
)
from app.modules.agent.session_service import ChatSessionService
from app.modules.knowledge_point.schemas import KnowledgePointOut
from app.modules.knowledge_point.service import KnowledgePointService
from app.shared.deps import get_db, require_launch_token
from app.shared.errors import CodedHTTPException
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
        scope=payload.scope or ChatScope.FREE,
        mode=payload.mode,
        record_id=str(payload.record_id) if payload.record_id is not None else None,
        course_id=str(payload.course_id) if payload.course_id is not None else None,
        library_item_id=(
            str(payload.library_item_id) if payload.library_item_id is not None else None
        ),
        knowledge_point_id=(
            str(payload.knowledge_point_id) if payload.knowledge_point_id is not None else None
        ),
    )
    # 创建时挂载记录/课程/资料已校验存活，失效态恒为 False。
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
        raise CodedHTTPException(
            code="CHAT_SESSION_NOT_FOUND", status_code=404, detail="对话不存在或已删除"
        )
    return chat


@router.patch("/{session_id}", response_model=ChatSessionOut)
async def rename_chat_session(
    session_id: UUID,
    payload: ChatSessionRename,
    session: AsyncSession = Depends(get_db),
) -> ChatSessionOut:
    renamed = await ChatSessionService.rename(session, str(session_id), payload.title)
    if renamed is None:
        raise CodedHTTPException(
            code="CHAT_SESSION_NOT_FOUND", status_code=404, detail="对话不存在或已删除"
        )
    out = await ChatSessionService.get_out(session, str(session_id))
    if out is None:
        raise CodedHTTPException(
            code="CHAT_SESSION_NOT_FOUND", status_code=404, detail="对话不存在或已删除"
        )
    return out


@router.delete("/{session_id}", status_code=204, response_class=Response, response_model=None)
async def delete_chat_session(
    session_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> Response:
    if not await ChatSessionService.soft_delete(session, str(session_id)):
        raise CodedHTTPException(
            code="CHAT_SESSION_NOT_FOUND", status_code=404, detail="对话不存在或已删除"
        )
    return Response(status_code=204)


@router.get("/{session_id}/messages", response_model=list[ChatMessageOut])
async def list_chat_messages(
    session_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> list[ChatMessageOut]:
    messages = await ChatMessageService.list_messages(session, str(session_id))
    if messages is None:
        raise CodedHTTPException(
            code="CHAT_SESSION_NOT_FOUND", status_code=404, detail="对话不存在或已删除"
        )
    return [ChatMessageOut.model_validate(message) for message in messages]


@router.post(
    "/{session_id}/messages/{message_id}/knowledge-points",
    response_model=KnowledgePointOut,
    status_code=201,
)
async def save_chat_message_as_knowledge_point(
    session_id: UUID,
    message_id: UUID,
    payload: ChatKnowledgePointSaveRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> KnowledgePointOut:
    """把一条 AI 回答保存为目标记录的知识点（对话转学习资产 V1）。

    单事务包住 agent 域会话校验与知识点域写入（校验查询会触发 autobegin，
    Service 内再 begin 会撞已开事务，事务由编排层统一管理）：知识点 + 搜索
    索引 + CHAT_MESSAGE 锚点与链接同生同灭；不写学习事件。
    """
    async with session.begin():
        await ChatSessionService.get_message(session, str(session_id), str(message_id))
        item = await KnowledgePointService.create_from_chat(
            session,
            body=payload,
            target_record_id=str(payload.target_record_id),
            chat_message_id=str(message_id),
        )
    await request.app.state.record_notifier.notify(str(payload.target_record_id))
    return item


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
        web_search=payload.web_search,
        page=payload.page,
    )
    return EventSourceResponse(
        ChatMessageService.stream_events(
            session_factory=app.state.session_factory,
            checkpointer=app.state.chat_checkpointer,
            registry=app.state.chat_stream_registry,
            accepted=accepted,
        )
    )
