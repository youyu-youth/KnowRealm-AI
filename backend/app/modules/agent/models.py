from datetime import datetime
from uuid import uuid4

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ISODateTime, utcnow
from app.modules.agent.schemas import ChatMode, ChatRole, ChatScope


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("courses.id", ondelete="SET NULL"),
        default=None,
    )
    record_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("records.id", ondelete="SET NULL"),
        default=None,
    )
    library_item_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("library_items.id", ondelete="SET NULL"),
        default=None,
    )
    concept_id: Mapped[str | None] = mapped_column(String(36), default=None)
    mode: Mapped[ChatMode] = mapped_column(String(20))
    scope: Mapped[ChatScope] = mapped_column(String(20), default=ChatScope.FREE)
    title: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
    )
    role: Mapped[ChatRole] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)
    citations_json: Mapped[str | None] = mapped_column(Text, default=None)
    model: Mapped[str | None] = mapped_column(Text, default=None)
    token_usage_json: Mapped[str | None] = mapped_column(Text, default=None)
    # 本轮直执行回执锚点（工单 02 P2 修复）：JSON 数组存 operation_id 列表，
    # 详情与授权依据以 agent_operations 查询为准（锚点只判定存在性）。
    executed_operations_json: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)


class ChatResponseProcess(Base):
    __tablename__ = "chat_response_processes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE")
    )
    user_message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_messages.id", ondelete="CASCADE")
    )
    assistant_message_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("chat_messages.id", ondelete="SET NULL"), default=None
    )
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(ISODateTime)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime)
    ended_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    entries_json: Mapped[str] = mapped_column(Text, default="[]")
