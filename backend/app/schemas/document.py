from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_serializer


class ProcessingJobType(StrEnum):
    DOCUMENT_PARSE = "DOCUMENT_PARSE"


class ProcessingJobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ProcessingJobErrorCode(StrEnum):
    NON_UTF8_TEXT = "NON_UTF8_TEXT"
    CORRUPT_DOCUMENT = "CORRUPT_DOCUMENT"
    PASSWORD_PROTECTED = "PASSWORD_PROTECTED"
    FORMAT_MISMATCH = "FORMAT_MISMATCH"
    NO_EXTRACTABLE_TEXT = "NO_EXTRACTABLE_TEXT"
    TEMPORARY_IO = "TEMPORARY_IO"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class DocumentImportAccepted(BaseModel):
    record_id: str
    job_id: str


class ProcessingJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    record_id: str | None
    job_type: ProcessingJobType
    status: ProcessingJobStatus
    progress: float
    attempts: int
    max_attempts: int
    error_code: ProcessingJobErrorCode | None
    retryable: bool


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
