from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_serializer, field_validator

SegmentEntityType = Literal["transcript_segment", "document_segment", "CONCEPT"]


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


class SegmentSearchHit(BaseModel):
    """分片检索命中：content 为回表取得的逐字原文（引用逐字校验的根基）。"""

    entity_type: SegmentEntityType
    segment_id: str
    content: str
    sequence_no: int
    record_start_ms: int | None = Field(default=None, description="转写分片时间轴起点")
    record_end_ms: int | None = Field(default=None, description="转写分片时间轴终点")
    page_no: int | None = Field(default=None, description="文档分片页码")


class LibrarySegmentSearchHit(BaseModel):
    """跨记录分片检索命中（B2）：额外携带归属记录（id + 标题）供引用归属。"""

    entity_type: SegmentEntityType
    segment_id: str
    record_id: str
    record_title: str
    content: str
    sequence_no: int
    record_start_ms: int | None = Field(default=None, description="转写分片时间轴起点")
    record_end_ms: int | None = Field(default=None, description="转写分片时间轴终点")
    page_no: int | None = Field(default=None, description="文档分片页码")
