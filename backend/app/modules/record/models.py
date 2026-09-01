from datetime import datetime
from uuid import uuid4

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ISODateTime, utcnow


class Record(Base):
    __tablename__ = "records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("courses.id", ondelete="CASCADE"),
    )
    capture_type: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30))
    duration_ms: Mapped[int] = mapped_column(Integer)
    summary_confirmed_at: Mapped[datetime | None] = mapped_column(ISODateTime)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)


class LearningEvent(Base):
    __tablename__ = "learning_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(String(36))
    record_id: Mapped[str | None] = mapped_column(String(36), default=None)
    concept_id: Mapped[str | None] = mapped_column(String(36), default=None)
    event_type: Mapped[str] = mapped_column(String(50))
    source_type: Mapped[str] = mapped_column(String(50))
    source_id: Mapped[str] = mapped_column(String(36))
    result: Mapped[str | None] = mapped_column(Text, default=None)
    score: Mapped[float | None] = mapped_column(Float, default=None)
    difficulty: Mapped[str | None] = mapped_column(String(30), default=None)
    duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    metadata_json: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True)
    schema_version: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(ISODateTime)
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
