"""自由聊天发消息：受理（校验 / 补答 / user 落库）与 SSE 流式事件生成。"""

import asyncio
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from langgraph.checkpoint.base import BaseCheckpointSaver  # pyright: ignore[reportMissingTypeStubs]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sse_starlette import ServerSentEvent

from app.agents.chat import (
    ChatStreamOutcome,
    ContextRow,
    build_context_messages,
    stream_chat_reply,
)
from app.models.base import utcnow
from app.models.chat import ChatMessage
from app.schemas.chat import ChatRole
from app.services.chat_session_service import ChatSessionService
from app.services.local_config import LlmProviderConfig, load_llm_provider

# 会话标题默认取首条用户消息的截断长度。
CHAT_TITLE_MAX_CHARS = 30

STREAM_STATUS_GENERATING = "generating"


class ChatStreamRegistry:
    """同一会话同时只允许一条在途生成（进程内状态；sidecar 单进程）。

    锁的配对唯一：accept 内 acquire（受理失败即在 accept 内释放），
    受理成功后由 stream_events 的 finally 释放（锁生命周期 = SSE 流生命周期，
    跨函数边界，contextmanager 无法覆盖）。
    """

    def __init__(self) -> None:
        self._active: set[str] = set()

    def acquire(self, session_id: str) -> bool:
        if session_id in self._active:
            return False
        self._active.add(session_id)
        return True

    def release(self, session_id: str) -> None:
        self._active.discard(session_id)


@dataclass(frozen=True)
class AcceptedMessage:
    """受理结果：user 行已落库（或补答复用），流式生成从这里开始。"""

    session_id: str
    user_row_id: str
    content: str
    provider: LlmProviderConfig


def _sse(event: str, payload: dict[str, object]) -> ServerSentEvent:
    return ServerSentEvent(event=event, data=json.dumps(payload, separators=(",", ":")))


async def _last_message(session: AsyncSession, session_id: str) -> ChatMessage | None:
    return await session.scalar(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(1)
    )


async def _session_rows(
    session_factory: async_sessionmaker[AsyncSession], session_id: str
) -> list[ContextRow]:
    async with session_factory() as session:
        rows = (
            await session.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at, ChatMessage.id)
            )
        ).all()
    return [ContextRow(id=row.id, role=row.role, content=row.content) for row in rows]


class ChatMessageService:
    @staticmethod
    async def list_messages(session: AsyncSession, session_id: str) -> list[ChatMessage] | None:
        """按时间顺序返回会话全部消息；会话不存在或已删返回 None。"""
        chat = await ChatSessionService.get(session, session_id)
        if chat is None:
            return None
        return list(
            (
                await session.scalars(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session_id)
                    .order_by(ChatMessage.created_at, ChatMessage.id)
                )
            ).all()
        )

    @staticmethod
    async def accept(
        *,
        session_factory: async_sessionmaker[AsyncSession],
        data_dir: Path,
        registry: ChatStreamRegistry,
        session_id: str,
        content: str,
    ) -> AcceptedMessage:
        """受理发送：校验供应商与在途状态，落库 user 行（补答复用原行）。"""
        provider = await asyncio.to_thread(load_llm_provider, data_dir)
        if provider is None or not provider.api_key:
            raise HTTPException(
                status_code=409,
                detail="LLM_PROVIDER_UNCONFIGURED：未配置 AI 服务，请先完成供应商配置",
            )
        if not registry.acquire(session_id):
            raise HTTPException(
                status_code=409,
                detail="CHAT_STREAM_IN_PROGRESS：该对话正在生成回答，请稍候",
            )
        try:
            async with session_factory() as session, session.begin():
                chat = await ChatSessionService.get(session, session_id)
                if chat is None:
                    raise HTTPException(status_code=404, detail="对话不存在或已删除")
                last = await _last_message(session, session_id)
                if last is not None and last.role == ChatRole.USER:
                    # 补答：会话末尾是无回复的 user 消息，复用原行重新生成，不重复落库。
                    last.content = content
                    user_row_id = last.id
                else:
                    user_row_id = str(uuid4())
                    session.add(
                        ChatMessage(
                            id=user_row_id,
                            session_id=session_id,
                            role=ChatRole.USER,
                            content=content,
                            citations_json=None,
                            model=None,
                            token_usage_json=None,
                            created_at=utcnow(),
                        )
                    )
                if chat.title is None:
                    chat.title = content[:CHAT_TITLE_MAX_CHARS]
                chat.updated_at = utcnow()
                await session.flush()
        except BaseException:
            registry.release(session_id)
            raise
        return AcceptedMessage(
            session_id=session_id,
            user_row_id=user_row_id,
            content=content,
            provider=provider,
        )

    @staticmethod
    async def stream_events(
        *,
        session_factory: async_sessionmaker[AsyncSession],
        checkpointer: BaseCheckpointSaver[str],
        registry: ChatStreamRegistry,
        accepted: AcceptedMessage,
    ) -> AsyncGenerator[ServerSentEvent, None]:
        """流式生成回答：status → token… → done / error；中断不落库、finally 释放锁。"""
        session_id = accepted.session_id
        try:
            yield _sse("status", {"phase": STREAM_STATUS_GENERATING})
            context = build_context_messages(await _session_rows(session_factory, session_id))
            outcome = ChatStreamOutcome()
            parts: list[str] = []
            try:
                async for text in stream_chat_reply(
                    session_factory=session_factory,
                    checkpointer=checkpointer,
                    provider=accepted.provider,
                    context_messages=context,
                    session_id=session_id,
                    outcome=outcome,
                ):
                    parts.append(text)
                    yield _sse("token", {"text": text})
            except Exception:
                yield _sse(
                    "error",
                    {"code": "CHAT_STREAM_FAILED", "detail": "回答生成失败，请稍后重试"},
                )
                return
            content = "".join(parts)
            if not content:
                yield _sse("error", {"code": "EMPTY_REPLY", "detail": "回答为空，请重试"})
                return
            assistant_id = str(uuid4())
            async with session_factory() as session, session.begin():
                session.add(
                    ChatMessage(
                        id=assistant_id,
                        session_id=session_id,
                        role=ChatRole.ASSISTANT,
                        content=content,
                        citations_json=None,
                        model=accepted.provider.model,
                        token_usage_json=json.dumps(outcome.token_usage, separators=(",", ":"))
                        if outcome.token_usage
                        else None,
                        created_at=utcnow(),
                    )
                )
                chat = await ChatSessionService.get(session, session_id)
                if chat is not None:
                    chat.updated_at = utcnow()
            yield _sse("done", {"message_id": assistant_id, "content": content})
        finally:
            registry.release(session_id)
