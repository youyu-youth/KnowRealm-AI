from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_serializer, field_validator

TODO_CONTENT_MAX_LENGTH = 500


class TodoStatus(StrEnum):
    TODO = "TODO"
    DONE = "DONE"


class TodoSource(StrEnum):
    AI = "AI"
    MANUAL = "MANUAL"


class TodoGenerationStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"


class TodoAction(StrEnum):
    NONE = "NONE"
    GENERATE = "GENERATE"
    ADOPT = "ADOPT"
    RETRY = "RETRY"


class TodoBlockedReason(StrEnum):
    SUMMARY_NOT_CONFIRMED = "SUMMARY_NOT_CONFIRMED"
    SUMMARY_SUPERSEDED = "SUMMARY_SUPERSEDED"
    COURSE_ARCHIVED = "COURSE_ARCHIVED"
    PROVIDER_NOT_CONFIGURED = "PROVIDER_NOT_CONFIGURED"
    CONSENT_REQUIRED = "CONSENT_REQUIRED"


class TodoWriteRequest(BaseModel):
    content: str = Field(
        min_length=1, max_length=TODO_CONTENT_MAX_LENGTH, description="待办内容"
    )

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("待办内容不能为空")
        return value


class TodoToggleRequest(BaseModel):
    status: TodoStatus


class TodoOut(BaseModel):
    id: str
    record_id: str
    batch_id: str | None
    content: str
    status: TodoStatus
    source: TodoSource
    generated_from_summary_id: str | None
    generation_status: TodoGenerationStatus | None
    sort_order: int
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_utc(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")


class TodoReadOut(BaseModel):
    items: list[TodoOut]
    action_required: TodoAction
    active_job_id: str | None = None
    blocked_reason: TodoBlockedReason | None = None
