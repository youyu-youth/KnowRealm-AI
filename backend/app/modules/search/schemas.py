from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_serializer, field_validator


class SearchQuery(BaseModel):
    q: str = Field(min_length=1, max_length=100, description="检索关键词")
    limit: int = Field(default=5, ge=1, le=50, description="每类结果上限")

    @field_validator("q")
    @classmethod
    def clean_q(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("q 不能为空白")
        return value


def _serialize_utc(value: datetime) -> str:
    utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")


class SearchCourseItem(BaseModel):
    id: str
    title: str
    snippet: str
    updated_at: datetime

    @field_serializer("updated_at")
    def serialize_updated_at(self, value: datetime) -> str:
        return _serialize_utc(value)


class SearchRecordItem(BaseModel):
    id: str
    title: str
    snippet: str
    course_name: str | None = Field(description="所属课程名；未归类记录为 null")
    updated_at: datetime

    @field_serializer("updated_at")
    def serialize_updated_at(self, value: datetime) -> str:
        return _serialize_utc(value)


class SearchKnowledgePointItem(BaseModel):
    id: str
    title: str
    snippet: str
    course_name: str | None = Field(description="所属课程名；记录未归类时为 null")
    record_id: str = Field(description="所属学习记录 id（跳转宿主）")
    updated_at: datetime

    @field_serializer("updated_at")
    def serialize_updated_at(self, value: datetime) -> str:
        return _serialize_utc(value)


class SearchOut(BaseModel):
    courses: list[SearchCourseItem]
    records: list[SearchRecordItem]
    knowledge_points: list[SearchKnowledgePointItem]
