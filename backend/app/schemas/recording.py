from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer, field_validator

from app.schemas.document import RecordingSessionState


class RecordingSessionCreate(BaseModel):
    course_id: UUID | None = None
    title: str | None = Field(default=None, max_length=100)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class RecordingSessionTargetState(StrEnum):
    RECORDING = "RECORDING"
    FINALIZING = "FINALIZING"


class RecordingSessionUpdate(BaseModel):
    target_state: RecordingSessionTargetState


class RecordingChunkTargetState(StrEnum):
    RECORDING = "RECORDING"
    PAUSED = "PAUSED"
    FINALIZING = "FINALIZING"


class RecordingSessionOut(BaseModel):
    id: str
    course_id: str | None
    title: str
    started_at: datetime
    updated_at: datetime
    state: RecordingSessionState
    recorded_duration_ms: int
    chunk_count: int

    @field_serializer("started_at", "updated_at")
    def serialize_utc(self, value: datetime) -> str:
        utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")


class RecordingChunkAccepted(BaseModel):
    session: RecordingSessionOut
    sequence_no: int = Field(ge=0)
    content_hash: str = Field(min_length=64, max_length=64)
    can_continue: bool
