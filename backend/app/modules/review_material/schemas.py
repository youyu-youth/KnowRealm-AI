import re
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class ReviewMaterialStatus(StrEnum):
    GENERATED = "GENERATED"
    CONFIRMED = "CONFIRMED"
    SUPERSEDED = "SUPERSEDED"


class ReviewMaterialContent(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    quick_review: str = Field(min_length=1, max_length=5000, description="考前速记 Markdown")
    key_list: list[str] = Field(
        min_length=1,
        max_length=50,
        description="按内容密度生成的 Top 重点清单",
    )
    mind_map_markdown: str = Field(
        min_length=1,
        max_length=5000,
        description="仅含标题与列表行的 Markdown 大纲",
    )

    @field_validator("key_list")
    @classmethod
    def validate_key_list(cls, value: list[str]) -> list[str]:
        items = [item.strip() for item in value]
        if any(not item or len(item) > 80 for item in items):
            raise ValueError("重点清单每项必须为 1 至 80 字")
        return items

    @field_validator("mind_map_markdown")
    @classmethod
    def validate_mind_map(cls, value: str) -> str:
        allowed = re.compile(r"^(?:#{1,6}\s+\S|[-*+]\s+\S|\d+[.)]\s+\S)")
        if any(line.strip() and not allowed.match(line.strip()) for line in value.splitlines()):
            raise ValueError("Markdown 大纲只能包含标题与列表行")
        return value


class ReviewMaterialAction(StrEnum):
    NONE = "NONE"
    CONFIGURE_PROVIDER = "CONFIGURE_PROVIDER"
    GRANT_CONSENT = "GRANT_CONSENT"
    GENERATE = "GENERATE"
    RETRY = "RETRY"


class ReviewMaterialBlockedReason(StrEnum):
    SUMMARY_NOT_CONFIRMED = "SUMMARY_NOT_CONFIRMED"
    COURSE_ARCHIVED = "COURSE_ARCHIVED"
    TRANSCRIPT_NOT_READY = "TRANSCRIPT_NOT_READY"


class ReviewMaterialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    record_id: str
    version_no: int
    transcript_source_version: int
    generated_from_summary_id: str | None
    quick_review: str
    key_list: list[str]
    mind_map_markdown: str
    status: ReviewMaterialStatus
    model: str
    prompt_version: str
    user_feedback: str | None = None
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")


class ReviewMaterialReadOut(BaseModel):
    review_material: ReviewMaterialOut | None
    action_required: ReviewMaterialAction
    blocked_reason: ReviewMaterialBlockedReason | None = None
    active_job_id: str | None = None
    transcript_stale: bool = False


class ReviewMaterialAdjustRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    feedback: str = Field(min_length=1, max_length=1000, description="调整反馈")


class ReviewMaterialJobAccepted(BaseModel):
    job_id: str
