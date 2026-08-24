from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class KnowledgePointCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1, max_length=100, description="知识点名称")
    detail: str = Field(min_length=1, max_length=2000, description="知识点详情")
    tags: list[str] = Field(max_length=5, description="最多五个简短标签")
    importance: int = Field(ge=1, le=5, description="重要度，1 至 5 的整数")

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        if any(not tag or tag != tag.strip() or len(tag) > 20 for tag in value):
            raise ValueError("每个标签必须为 1 至 20 字")
        return value

    @field_validator("name", "detail")
    @classmethod
    def reject_surrounding_whitespace(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("名称与详情不能包含首尾空白")
        return value


class KnowledgePointBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    items: list[KnowledgePointCandidate] = Field(
        min_length=1,
        max_length=20,
        description="按内容密度生成的知识点候选",
    )


class KnowledgePointWriteRequest(KnowledgePointCandidate):
    """手工新增与行内编辑共用的请求体，校验边界与候选一致。"""


class KnowledgePointGenerationStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"


class KnowledgePointInputMode(StrEnum):
    FULL_TRANSCRIPT = "FULL_TRANSCRIPT"
    SUMMARY_ONLY = "SUMMARY_ONLY"


class KnowledgePointAction(StrEnum):
    NONE = "NONE"
    GENERATE = "GENERATE"
    CONFIRM = "CONFIRM"
    RETRY = "RETRY"


class KnowledgePointBlockedReason(StrEnum):
    SUMMARY_NOT_CONFIRMED = "SUMMARY_NOT_CONFIRMED"
    SUMMARY_SUPERSEDED = "SUMMARY_SUPERSEDED"
    COURSE_ARCHIVED = "COURSE_ARCHIVED"
    TRANSCRIPT_NOT_READY = "TRANSCRIPT_NOT_READY"
    PROVIDER_NOT_CONFIGURED = "PROVIDER_NOT_CONFIGURED"
    CONSENT_REQUIRED = "CONSENT_REQUIRED"


class KnowledgePointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    record_id: str
    batch_id: str | None
    name: str
    detail: str
    tags: list[str]
    importance: int
    generated_from_summary_id: str | None
    generation_status: KnowledgePointGenerationStatus
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_utc(self, value: datetime) -> str:
        utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")


class KnowledgePointReadOut(BaseModel):
    items: list[KnowledgePointOut]
    action_required: KnowledgePointAction
    active_job_id: str | None = None
    blocked_reason: KnowledgePointBlockedReason | None = None
    input_mode: KnowledgePointInputMode | None = None


class KnowledgePointJobAccepted(BaseModel):
    job_id: str
