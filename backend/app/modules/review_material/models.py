from datetime import datetime
from uuid import uuid4

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ISODateTime, utcnow


class ReviewMaterial(Base):
    __tablename__ = "review_materials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    record_id: Mapped[str] = mapped_column(String(36), ForeignKey("records.id", ondelete="CASCADE"))
    version_no: Mapped[int] = mapped_column(Integer)
    transcript_source_version: Mapped[int] = mapped_column(Integer)
    generated_from_summary_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ai_summaries.id", ondelete="SET NULL"), default=None
    )
    quick_review: Mapped[str] = mapped_column(Text)
    key_list_json: Mapped[str] = mapped_column(Text)
    mind_map_markdown: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    user_feedback: Mapped[str | None] = mapped_column(Text, default=None)
    token_usage_json: Mapped[str] = mapped_column(Text)
    latency_ms: Mapped[int] = mapped_column(Integer)
    confirmed_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)
