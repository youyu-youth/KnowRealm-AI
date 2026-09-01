from datetime import datetime
from uuid import uuid4

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, ISODateTime, utcnow
from app.modules.capture.schemas import RecordingSessionState


class RecordFile(Base):
    __tablename__ = "record_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    record_id: Mapped[str] = mapped_column(String(36), ForeignKey("records.id", ondelete="CASCADE"))
    file_type: Mapped[str] = mapped_column(String(20))
    source_type: Mapped[str] = mapped_column(String(20))
    file_path: Mapped[str] = mapped_column(Text)
    original_name: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    sequence_no: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(ISODateTime, default=None)


class RecordingSession(Base):
    __tablename__ = "recording_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    course_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("courses.id", ondelete="SET NULL"), default=None
    )
    title: Mapped[str | None] = mapped_column(Text, default=None)
    started_at: Mapped[datetime] = mapped_column(ISODateTime)
    updated_at: Mapped[datetime] = mapped_column(ISODateTime)
    state: Mapped[RecordingSessionState] = mapped_column(String(20))
    chunk_paths: Mapped[str] = mapped_column(Text)
    recorded_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
