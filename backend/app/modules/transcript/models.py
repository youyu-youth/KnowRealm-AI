from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ISODateTime, utcnow


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("records.id", ondelete="CASCADE"), unique=True
    )
    language: Mapped[str] = mapped_column(String(35))
    content: Mapped[str] = mapped_column(Text)
    source_version: Mapped[int] = mapped_column(Integer, default=1)
    edited_by_user: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)
