"""资料学习只记录明确启动和最后页签，不推导学习时长或掌握度。"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer

from app.modules.learning_plan.schemas import PlanItemOut, serialize_plan_time
from app.modules.record.schemas import RecordContentTab


class StudySourceOut(BaseModel):
    record_id: str
    title: str
    read_only: bool


class RecordStudyOut(BaseModel):
    item: PlanItemOut
    course_id: str
    goal_id: str
    plan_id: str
    editable: bool
    source_status: Literal["AVAILABLE", "MISSING", "UNAVAILABLE"]
    source: StudySourceOut | None
    sources: list[StudySourceOut]
    sources_truncated: bool
    visit_id: str | None
    started_at: datetime | None
    tab: RecordContentTab
    entry_path: str

    @field_serializer("started_at")
    def serialize_time(self, value: datetime | None) -> str | None:
        return serialize_plan_time(value) if value else None


class RecordStudyStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    record_id: UUID


class RecordStudyTabUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visit_id: UUID
    record_id: UUID
    tab: RecordContentTab
