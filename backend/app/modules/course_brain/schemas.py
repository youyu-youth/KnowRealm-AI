"""Course Brain 查询域 Schema（F4 CB-03）：快照六态、概念视图、来源回溯与检索结果。"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator

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
    suggested_target_id: str | None = Field(
        default=None,
        description="确定性相似度量超阈值的合并建议目标（仅候选概念填充；只建议不自动合并）",
    )
    suggested_target_name: str | None = Field(default=None, description="合并建议目标的规范名")
    stale_archivable: bool = Field(
        default=False,
        description="待归档徽章（仅正式概念：出现映射全部失效时为真），查询时派生不落库",
    )

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


class BrainBuildAcceptedOut(BaseModel):
    job_id: str = Field(description="已入队的构建任务 id")


# ---------------------------------------------------------------------------
# CB-05 审核闭环：apply-review 决策（同事务原子应用；relation 审核见 CB-06）
# ---------------------------------------------------------------------------


class ReviewDecisionType(StrEnum):
    CONFIRM = "confirm"
    MERGE = "merge"
    DISMISS = "dismiss"


class ConfirmDecision(BaseModel):
    """候选确认：CANDIDATE→CONFIRMED，可带重命名（重命名走归一化撞名检查）。"""

    decision_type: Literal[ReviewDecisionType.CONFIRM]
    concept_id: str = Field(min_length=1, description="待确认候选概念 id")
    new_name: str | None = Field(
        default=None, max_length=100, description="可选重命名；缺省沿用候选规范名"
    )

    @field_validator("new_name")
    @classmethod
    def clean_new_name(cls, value: str | None) -> str | None:
        return None if value is None else value.strip()


class MergeDecision(BaseModel):
    """候选合并：候选并入同课程正式概念，迁移出现映射与锚点链接后退役。"""

    decision_type: Literal[ReviewDecisionType.MERGE]
    concept_id: str = Field(min_length=1, description="待合并候选概念 id")
    target_concept_id: str = Field(min_length=1, description="并入的正式概念 id")


class DismissDecision(BaseModel):
    """候选忽略：CANDIDATE→ARCHIVED；重建时同名概念可再次进入审核。"""

    decision_type: Literal[ReviewDecisionType.DISMISS]
    concept_id: str = Field(min_length=1, description="待忽略候选概念 id")


ReviewDecision = Annotated[
    ConfirmDecision | MergeDecision | DismissDecision,
    Field(discriminator="decision_type"),
]


class ApplyReviewRequest(BaseModel):
    decisions: list[ReviewDecision] = Field(
        min_length=1, max_length=200, description="审核决策列表（单事务原子应用）"
    )

    @model_validator(mode="after")
    def reject_duplicate_concepts(self) -> "ApplyReviewRequest":
        concept_ids = [decision.concept_id for decision in self.decisions]
        if len(set(concept_ids)) != len(concept_ids):
            raise ValueError("同一概念在决策列表中重复出现")
        return self


# ---------------------------------------------------------------------------
# CB-04 LLM 结构化抽取合同（with_structured_output 输出面；DB 值域见迁移 0023）
# ---------------------------------------------------------------------------


class CourseBrainRelationType(StrEnum):
    PREREQUISITE = "PREREQUISITE"
    PART_OF = "PART_OF"
    RELATED_TO = "RELATED_TO"
    COMPARE_WITH = "COMPARE_WITH"
    CAUSES = "CAUSES"
    APPLIES_TO = "APPLIES_TO"


class CourseBrainEvidence(BaseModel):
    quote: str = Field(
        min_length=1, max_length=120, description="逐字摘自原文的证据片段，不得改写或概括"
    )
    source_hint: str = Field(default="", max_length=200, description="来源提示（记录标题或章节）")


class CourseBrainExtractionConcept(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="概念规范名，跨记录保持一致")
    description: str = Field(default="", max_length=500, description="一句话概念说明")
    concept_type: str = Field(
        default="TERM", max_length=30, description="概念类型，如 TERM/PROCESS/PRINCIPLE/METHOD/TOOL"
    )
    importance: int = Field(default=3, ge=1, le=5, description="重要度 1~5")
    evidence: list[CourseBrainEvidence] = Field(
        default_factory=list[CourseBrainEvidence], description="支撑该概念的原文证据，至少一条"
    )


class CourseBrainExtractionRelation(BaseModel):
    source: str = Field(min_length=1, max_length=100, description="关系起点概念名")
    target: str = Field(min_length=1, max_length=100, description="关系终点概念名")
    relation_type: CourseBrainRelationType = Field(description="关系类型")
    confidence: float = Field(default=0.5, ge=0, le=1, description="置信度 0~1")


class CourseBrainExtractionBatch(BaseModel):
    concepts: list[CourseBrainExtractionConcept] = Field(
        default_factory=list[CourseBrainExtractionConcept], description="本次内容中抽取到的概念"
    )
    relations: list[CourseBrainExtractionRelation] = Field(
        default_factory=list[CourseBrainExtractionRelation],
        description="概念之间的关系（source/target 必须是本次概念名）",
    )
