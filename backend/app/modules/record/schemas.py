from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer

from app.modules.capture.schemas import CaptureType

RecordContentTab = Literal["summary", "transcript", "knowledge-points", "quiz", "review", "todo"]


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


class InboxRecordOut(RecordOut):
    """收件箱条目：RecordOut + 列表展示用元信息。

    file_size_bytes 为该记录全部文件（record_files，未软删）大小之和，无文件为 None；
    content_chars 为当前生效转写/正文的字符数，转写未就绪为 None。
    """

    file_size_bytes: int | None = None
    content_chars: int | None = None


class RecordClassificationRequest(BaseModel):
    course_id: UUID


class RecordMoveRequest(BaseModel):
    target_course_id: UUID


class RecordUpgradeRequest(BaseModel):
    course_id: UUID | None = None


class RecordUpgradeAccepted(BaseModel):
    record: RecordOut
    summary_job_id: str | None
