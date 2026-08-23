from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_serializer


class CaptureType(StrEnum):
    RECORDING = "RECORDING"
    AUDIO_IMPORT = "AUDIO_IMPORT"
    DOCUMENT_IMPORT = "DOCUMENT_IMPORT"
    MULTI_SOURCE = "MULTI_SOURCE"
    PASTE = "PASTE"
    QUICK_NOTE = "QUICK_NOTE"
    CLIP = "CLIP"


class RecordStatus(StrEnum):
    NOTE = "NOTE"
    DRAFT = "DRAFT"
    CONTENT_PROCESSING = "CONTENT_PROCESSING"
    SUMMARY_PENDING = "SUMMARY_PENDING"
    SUMMARY_PROCESSING = "SUMMARY_PROCESSING"
    SUMMARY_READY = "SUMMARY_READY"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str | None
    capture_type: CaptureType
    title: str
    status: RecordStatus
    duration_ms: int
    summary_confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_utc(self, value: datetime) -> str:
        utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")

    @field_serializer("summary_confirmed_at")
    def serialize_optional_utc(self, value: datetime | None) -> str | None:
        return None if value is None else self.serialize_utc(value)
