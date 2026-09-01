from datetime import datetime
from uuid import uuid4

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ISODateTime, utcnow


class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    record_id: Mapped[str] = mapped_column(String(36), ForeignKey("records.id", ondelete="CASCADE"))
    batch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("processing_jobs.id", ondelete="SET NULL"), default=None
    )
    name: Mapped[str] = mapped_column(String(100))
    detail: Mapped[str] = mapped_column(Text)
    tags: Mapped[str] = mapped_column(Text)
    importance: Mapped[float] = mapped_column(Float)
    generated_from_summary_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ai_summaries.id", ondelete="SET NULL"), default=None
    )
    generation_status: Mapped[str] = mapped_column(String(20))
    source_anchor_id: Mapped[str | None] = mapped_column(String(36), default=None)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)
