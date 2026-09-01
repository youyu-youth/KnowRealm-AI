from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class SummarySection(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    heading: str = Field(min_length=1, max_length=80, description="章节标题")
    points: list[str] = Field(min_length=1, max_length=8, description="章节分点")

    @field_validator("points")
    @classmethod
    def validate_points(cls, value: list[str]) -> list[str]:
        points = [point.strip() for point in value]
        if any(not point or len(point) > 500 for point in points):
            raise ValueError("每个总结分点必须为 1 至 500 字")
        return points


class SummaryContent(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    topic: str = Field(min_length=1, max_length=80, description="一句话主题")
    abstract: str = Field(min_length=500, max_length=1000, description="500 至 1000 字摘要")
    sections: list[SummarySection] = Field(
        min_length=1,
        max_length=12,
        description="按顺序排列的总结章节",
    )


class SummaryAction(StrEnum):
    NONE = "NONE"
    CONFIGURE_PROVIDER = "CONFIGURE_PROVIDER"
    GRANT_CONSENT = "GRANT_CONSENT"
    GENERATE = "GENERATE"
    RETRY = "RETRY"


class SummaryBlockedReason(StrEnum):
    COURSE_REQUIRED = "COURSE_REQUIRED"
    COURSE_ARCHIVED = "COURSE_ARCHIVED"
    TRANSCRIPT_NOT_READY = "TRANSCRIPT_NOT_READY"


class SummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    record_id: str
    version_no: int
    transcript_source_version: int
    topic: str
    abstract: str
    sections: list[SummarySection]
    status: str
    model: str
    prompt_version: str
    user_feedback: str | None = None
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")


class SummaryReadOut(BaseModel):
    summary: SummaryOut | None
    action_required: SummaryAction
    blocked_reason: SummaryBlockedReason | None = None
    active_job_id: str | None = None


class SummaryJobAccepted(BaseModel):
    job_id: str


class SummaryAdjustRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    summary_id: UUID
    feedback: str = Field(min_length=1, max_length=1000, description="调整反馈")


class SummaryConfirmRequest(BaseModel):
    summary_id: UUID


class SummaryConfirmOut(BaseModel):
    summary: SummaryOut
    record_status: str
