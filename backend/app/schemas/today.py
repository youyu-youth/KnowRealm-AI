from datetime import UTC, datetime

from pydantic import BaseModel, field_serializer


class TodaySummaryTodoOut(BaseModel):
    record_id: str
    title: str
    course_id: str
    course_name: str
    ready_at: datetime

    @field_serializer("ready_at")
    def serialize_ready_at(self, value: datetime) -> str:
        utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")
