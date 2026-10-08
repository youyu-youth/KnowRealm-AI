"""ChatTurn 持久模型（切换会话不中断任务，票 01）。"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ISODateTime, utcnow


class ChatTurn(Base):
    """一条用户输入对应的一次回答生成：受理原子落库，执行与观察分离。"""

    __tablename__ = "chat_turns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE")
    )
    user_message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_messages.id", ondelete="CASCADE")
    )
    request_id: Mapped[str] = mapped_column(String(64))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    cancel_requested: Mapped[bool] = mapped_column(Integer, default=False)
    execution_json: Mapped[str] = mapped_column(Text, default="{}")
    claim_token: Mapped[str | None] = mapped_column(String(36), default=None)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    output_revision: Mapped[int] = mapped_column(Integer, default=1)
    last_seq: Mapped[int] = mapped_column(Integer, default=0)
    final_message_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("chat_messages.id", ondelete="SET NULL"), default=None
    )
    error_code: Mapped[str | None] = mapped_column(String(50), default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)
    finished_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)


class ChatTurnEvent(Base):
    """轮次持久事件：单调 seq（唯一），先同事务提交后通知 / 发送。"""

    __tablename__ = "chat_turn_events"
    __table_args__ = (UniqueConstraint("turn_id", "seq", name="idx_chat_turn_events_seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    turn_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_turns.id", ondelete="CASCADE")
    )
    seq: Mapped[int] = mapped_column(Integer)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    output_revision: Mapped[int] = mapped_column(Integer, default=1)
    type: Mapped[str] = mapped_column(String(20))
    segment_id: Mapped[str | None] = mapped_column(String(64), default=None)
    tool_call_id: Mapped[str | None] = mapped_column(String(64), default=None)
    payload_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
