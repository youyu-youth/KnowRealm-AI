from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer, model_validator

RecordResumeTab = Literal["summary", "transcript", "knowledge-points", "quiz", "review", "todo"]


class ResumeKind(StrEnum):
    RECORD = "RECORD"
    QUIZ_TEST = "QUIZ_TEST"
    CHAT_SESSION = "CHAT_SESSION"


class LearningResumeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ResumeKind
    target_id: UUID
    record_tab: RecordResumeTab | None = None

    @model_validator(mode="after")
    def validate_tab(self) -> Self:
        if self.kind != ResumeKind.RECORD and self.record_tab is not None:
            raise ValueError("只有学习记录支持 record_tab")
        return self


class LearningResumeOut(BaseModel):
    kind: ResumeKind
    target_id: str
    title: str | None
    course_id: str | None = None
    course_name: str | None = None
    record_tab: RecordResumeTab | None = None
    visited_at: datetime
    answered_count: int | None = None
    total_count: int | None = None
    href: str

    @field_serializer("visited_at")
    def serialize_time(self, value: datetime) -> str:
        utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return utc_value.isoformat().replace("+00:00", "Z")
