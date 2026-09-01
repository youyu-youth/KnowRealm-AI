from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class AsrChunkStatus(StrEnum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class TranscriptAvailability(StrEnum):
    NOT_READY = "NOT_READY"
    READY = "READY"


class TranscriptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    language: str
    content: str
    source_version: int
    edited_by_user: bool
    updated_at: datetime

    @field_serializer("updated_at")
    def serialize_utc(self, value: datetime) -> str:
        utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")


class TranscriptReadOut(BaseModel):
    status: TranscriptAvailability
    transcript: TranscriptOut | None


class TranscriptUpdateRequest(BaseModel):
    content: str = Field(min_length=1)
    expected_source_version: int = Field(ge=1)
