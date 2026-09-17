"""learning 域 API Schema：课程 Mastery 只读视图（无任何写 API）。

状态与 Confidence 分档复用算法枚举，避免两处口径；时间序列化统一 UTC ``Z``。
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_serializer

from app.modules.learning.mastery import MasteryConfidence, MasteryStatus


def _serialize_utc(value: datetime) -> str:
    utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")


class CourseMasteryQuery(BaseModel):
    status: MasteryStatus | None = Field(
        default=None, description="按掌握状态筛选概念列表；缺省返回全部四态"
    )


class ConceptMasteryOut(BaseModel):
    concept_id: str
    canonical_name: str
    description: str
    concept_type: str
    importance: int
    status: MasteryStatus
    mastery_score: float | None = Field(
        default=None, description="最近 12 条窗口加权分数 0~1；数据不足时为 null，不返回 0"
    )
    confidence: MasteryConfidence | None = Field(
        default=None, description="Confidence 分档（证据充足程度）；数据不足时为 null"
    )
    evidence_count: int = Field(description="参与当前算法版本的有效 Evidence 条数（窗口内）")
    positive_evidence_count: int
    negative_evidence_count: int
    last_practiced_at: datetime | None = Field(default=None, description="最近一次有效作答时间")
    last_verified_at: datetime | None = Field(default=None, description="最近一次答对时间")

    @field_serializer("last_practiced_at", "last_verified_at")
    def serialize_utc(self, value: datetime | None) -> str | None:
        return None if value is None else _serialize_utc(value)


class MasteryStatusCountsOut(BaseModel):
    not_enough_data: int
    weak: int
    learning: int
    stable: int


class CourseMasteryOut(BaseModel):
    course_id: str
    confirmed_concept_count: int = Field(description="活跃 CONFIRMED Concept 总数")
    verified_concept_count: int = Field(description="至少有一条有效证据的 Concept 数")
    coverage: float = Field(description="证据覆盖率 = 有证据 Concept / 已确认 Concept，0~1")
    status_counts: MasteryStatusCountsOut
    concepts: list[ConceptMasteryOut] = Field(
        description="按状态优先级排序（WEAK → LEARNING → 数据不足 → STABLE）；不返回课程平均分"
    )
