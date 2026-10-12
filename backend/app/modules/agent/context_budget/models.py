from datetime import datetime
from uuid import uuid4

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ISODateTime, utcnow
from app.modules.agent.context_budget.schemas import ModelRequestStatus


class ChatContextState(Base):
    __tablename__ = "chat_context_states"
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    segment: Mapped[int] = mapped_column(Integer, default=1)


class ChatContextInput(Base):
    __tablename__ = "chat_context_inputs"
    turn_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_turns.id", ondelete="CASCADE"), primary_key=True
    )
    context_version: Mapped[int] = mapped_column(Integer)
    policy_json: Mapped[str] = mapped_column(Text)
    messages_json: Mapped[str | None] = mapped_column(Text, default=None)


class ChatModelRequest(Base):
    __tablename__ = "chat_model_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    turn_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_turns.id", ondelete="CASCADE")
    )
    status: Mapped[ModelRequestStatus] = mapped_column(
        Enum(ModelRequestStatus, native_enum=False, length=20)
    )
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    estimate_json: Mapped[str] = mapped_column(Text)
    usage_json: Mapped[str | None] = mapped_column(Text, default=None)
    error_code: Mapped[str | None] = mapped_column(String(50), default=None)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
