from datetime import datetime
from uuid import uuid4

from sqlalchemy import Enum, ForeignKey, Integer, String, Text, UniqueConstraint
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
    summary_id: Mapped[str | None] = mapped_column(String(36), default=None)


class ChatContextInput(Base):
    __tablename__ = "chat_context_inputs"
    turn_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_turns.id", ondelete="CASCADE"), primary_key=True
    )
    context_version: Mapped[int] = mapped_column(Integer)
    policy_json: Mapped[str] = mapped_column(Text)
    messages_json: Mapped[str | None] = mapped_column(Text, default=None)
    segment: Mapped[int] = mapped_column(Integer, default=1)
    summary_id: Mapped[str | None] = mapped_column(String(36), default=None)
    summary_allowance: Mapped[int] = mapped_column(Integer, default=4)


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
    purpose: Mapped[str] = mapped_column(String(10), default="ANSWER")
    messages_json: Mapped[str | None] = mapped_column(Text, default=None)
    retry_of: Mapped[str | None] = mapped_column(String(64), default=None)


class ChatCompaction(Base):
    __tablename__ = "chat_compactions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    turn_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_turns.id", ondelete="CASCADE")
    )
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    context_version: Mapped[int] = mapped_column(Integer)
    segment: Mapped[int] = mapped_column(Integer)
    base_summary_id: Mapped[str | None] = mapped_column(String(36), default=None)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")
    plan_json: Mapped[str] = mapped_column(Text)
    results_json: Mapped[str] = mapped_column(Text, default="[]")
    summary_json: Mapped[str | None] = mapped_column(Text, default=None)
    covered_json: Mapped[str] = mapped_column(Text)
    requests_used: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(50), default=None)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)


class ChatContextOutput(Base):
    __tablename__ = "chat_context_outputs"
    __table_args__ = (UniqueConstraint("turn_id", "namespace", "logical_call_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    turn_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_turns.id", ondelete="CASCADE")
    )
    namespace: Mapped[str] = mapped_column(Text)
    logical_call_id: Mapped[str] = mapped_column(Text)
    tool_name: Mapped[str] = mapped_column(Text)
    args_fingerprint: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)
    inline_content: Mapped[str | None] = mapped_column(Text, default=None)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
