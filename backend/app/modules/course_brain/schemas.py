"""Course Brain 查询域 Schema（F4 CB-03）：快照六态、概念视图、来源回溯与检索结果。"""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_serializer, field_validator

from app.modules.search.schemas import SegmentEntityType
from app.modules.source_anchor.schemas import SourceAnchorType


class BrainStatus(StrEnum):
    EMPTY = "EMPTY"
    BUILDING = "BUILDING"
    REVIEW = "REVIEW"
    READY = "READY"
    STALE = "STALE"
    FAILED = "FAILED"


class ConceptStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    CONFIRMED = "CONFIRMED"
    ARCHIVED = "ARCHIVED"


class ConceptSource(StrEnum):
    AI_EXTRACTED = "AI_EXTRACTED"
    USER_CONFIRMED = "USER_CONFIRMED"
    SYSTEM = "SYSTEM"


def _serialize_utc(value: datetime) -> str:
    utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")


class BrainConceptListQuery(BaseModel):
    status: ConceptStatus = Field(default=ConceptStatus.CONFIRMED, description="概念状态筛选")
    limit: int = Field(default=50, ge=1, le=200, description="返回数量上限")
    offset: int = Field(default=0, ge=0, description="分页偏移")


class BrainConceptCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="概念规范名")
    description: str = Field(default="", max_length=2000, description="概念说明")
    concept_type: str = Field(default="TERM", min_length=1, max_length=30, description="概念类型")
    importance: int = Field(default=3, ge=1, le=5, description="重要度 1~5")

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("概念名称不能为空白")
        return cleaned

    @field_validator("description", "concept_type")
    @classmethod
    def clean_optional(cls, value: str) -> str:
        return value.strip()


class BrainConceptOut(BaseModel):
    id: str
    course_id: str
    canonical_name: str
    description: str
    concept_type: str
    importance: int
    status: ConceptStatus
    source: ConceptSource
    created_at: datetime
    updated_at: datetime
    record_count: int = Field(default=0, description="出现该概念的未删除记录数")
    occurrence_count: int = Field(default=0, description="出现次数合计（证据计数）")

    @field_serializer("created_at", "updated_at")
    def serialize_utc(self, value: datetime) -> str:
        return _serialize_utc(value)


class BrainConceptDetailOut(BrainConceptOut):
    anchor_count: int = Field(default=0, description="来源锚点链接数")


class BrainSnapshotOut(BaseModel):
    course_id: str
    status: BrainStatus
    concept_count: int = Field(description="已确认（CONFIRMED）概念数")
    candidate_count: int = Field(description="待审核（CANDIDATE）概念数")
    stale: bool = Field(description="来源指纹与上次成功构建不一致")
    active_job_id: str | None = Field(default=None, description="进行中的构建任务 id")
    last_built_at: datetime | None = Field(default=None, description="最近一次成功构建完成时间")

    @field_serializer("last_built_at")
    def serialize_utc(self, value: datetime | None) -> str | None:
        return None if value is None else _serialize_utc(value)


class ConceptAnchorSourceOut(BaseModel):
    anchor_id: str
    source_type: SourceAnchorType
    relation_type: str
    record_id: str | None = Field(default=None, description="锚点挂靠记录；无记录来源为 null")
    record_title: str | None = Field(default=None, description="锚点挂靠记录标题")
    quote: str | None = Field(default=None, description="来源逐字原文（分片/对话内容）")
    start_ms: int | None = Field(default=None, description="转写分片时间轴起点")
    end_ms: int | None = Field(default=None, description="转写分片时间轴终点")
    page_no: int | None = Field(default=None, description="文档分片页码")
    chat_session_id: str | None = Field(default=None, description="对话来源会话 id（跳转用）")


class ConceptKpSourceOut(BaseModel):
    record_id: str
    record_title: str
    knowledge_point_id: str
    knowledge_point_name: str
    relevance: float
    evidence_count: int


class ConceptSourcesOut(BaseModel):
    concept_id: str
    anchors: list[ConceptAnchorSourceOut]
    knowledge_points: list[ConceptKpSourceOut]


class BrainSearchConceptOut(BaseModel):
    concept_id: str
    canonical_name: str
    description: str
    record_count: int = Field(description="出现该概念的未删除记录数")
    occurrence_count: int = Field(description="出现次数合计（证据计数）")


class BrainSearchOccurrenceOut(BaseModel):
    record_id: str
    record_title: str
    source_type: SegmentEntityType
    segment_id: str
    quote: str = Field(description="回表取得的逐字原文（引用逐字校验的根基）")
    position: int = Field(description="分片序号（定位用）")
    start_ms: int | None = Field(default=None, description="转写分片时间轴起点")
    end_ms: int | None = Field(default=None, description="转写分片时间轴终点")
    page_no: int | None = Field(default=None, description="文档分片页码")


class BrainSearchRelationOut(BaseModel):
    concept_id: str
    canonical_name: str
    relation_type: str


class CourseBrainSearchOut(BaseModel):
    matched_concepts: list[BrainSearchConceptOut]
    related_concepts: list[BrainSearchRelationOut]
    occurrences: list[BrainSearchOccurrenceOut]
