from datetime import datetime
from uuid import uuid4

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ISODateTime, utcnow


class AiSummary(Base):
    __tablename__ = "ai_summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    record_id: Mapped[str] = mapped_column(String(36), ForeignKey("records.id", ondelete="CASCADE"))
    version_no: Mapped[int] = mapped_column(Integer)
    transcript_source_version: Mapped[int] = mapped_column(Integer)
    topic: Mapped[str] = mapped_column(Text)
    abstract: Mapped[str] = mapped_column(Text)
    summary_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    token_usage_json: Mapped[str] = mapped_column(Text)
    latency_ms: Mapped[int] = mapped_column(Integer)
    user_feedback: Mapped[str | None] = mapped_column(Text, default=None)
    confirmed_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)
