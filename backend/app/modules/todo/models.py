from datetime import datetime
from uuid import uuid4

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ISODateTime, utcnow


class TodoItem(Base):
    __tablename__ = "todo_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    record_id: Mapped[str] = mapped_column(String(36), ForeignKey("records.id", ondelete="CASCADE"))
    batch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("processing_jobs.id", ondelete="SET NULL"), default=None
    )
    content: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(String(10))
    generated_from_summary_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ai_summaries.id", ondelete="SET NULL"), default=None
    )
    generation_status: Mapped[str | None] = mapped_column(String(20), default=None)
    sort_order: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)
