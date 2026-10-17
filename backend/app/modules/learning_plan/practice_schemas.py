"""练习要求与准备阶段投影；此阶段永不返回题面或参考答案。"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.quiz.schemas import QuizQuestionType


class PreparationStatus(StrEnum):
    READY = "READY"
    INSUFFICIENT = "INSUFFICIENT"
    INCOMPLETE = "INCOMPLETE"


class PracticeMatchReason(StrEnum):
    TOPIC_CONCEPT = "TOPIC_CONCEPT"
    TOPIC_APPLICATION = "TOPIC_APPLICATION"
    OUT_OF_TOPIC = "OUT_OF_TOPIC"
    UNCERTAIN = "UNCERTAIN"


class PracticeRequirementsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0)
    plan_content: str = Field(min_length=1, max_length=200)
    topic: str = Field(min_length=1, max_length=200)
    question_count: int = Field(gt=0, strict=True)
    question_types: list[QuizQuestionType] = Field(min_length=1, max_length=5)
    record_ids: list[UUID] = Field(min_length=1)
    source_versions: dict[str, str]

    @field_validator("topic")
    @classmethod
    def clean_topic(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("主题不能为空白")
        return value.strip()

    @field_validator("record_ids", "question_types")
    @classmethod
    def unique_values[T](cls, values: list[T]) -> list[T]:
        if len(set(values)) != len(values):
            raise ValueError("对象和题型不能重复")
        return values


class PracticeRequirementsOut(BaseModel):
    id: str
    revision: int
    plan_content: str
    topic: str
    question_count: int
    question_types: list[QuizQuestionType]
    record_ids: list[str]
    source_versions: dict[str, str]
    confirmed_at: datetime


class PracticePrepareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    requirements_revision: int = Field(gt=0)


class PracticeSourceOut(BaseModel):
    record_id: str
    title: str
    eligible_count: int
    related_count: int = 0
    version: str = ""
    matching_basis: list[PracticeMatchReason] = Field(default_factory=list[PracticeMatchReason])


class PracticePreparationOut(BaseModel):
    id: str
    item_id: str
    entry_path: str
    job_id: str
    requirements_revision: int
    status: str
    outcome: PreparationStatus | None
    target_count: int
    eligible_count: int
    related_count: int
    selected_count: int
    examined_count: int
    total_candidates: int
    course_scan_complete: bool
    error_code: str | None
    sources: list[PracticeSourceOut]
    suggestions: list[PracticeSourceOut]


class PracticeStateOut(BaseModel):
    item_id: str
    course_id: str
    plan_id: str
    plan_content: str
    editable: bool
    requirements_stale: bool
    requirements: PracticeRequirementsOut | None
    preparations: list[PracticePreparationOut]
    sources: list[PracticeSourceOut]
    round: "PracticeRoundOut | None" = None


class PracticeRoundStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    requirements_revision: int = Field(gt=0)
    preparation_id: UUID | None = None


class PracticeRoundSourceOut(BaseModel):
    record_id: str
    title: str
    valid: bool


class PracticeRoundOut(BaseModel):
    """最近一轮计划练习投影：作答与评分状态分开，揭示前不含答案。"""

    test_id: str
    round_no: int
    requirements_revision: int
    status: str
    entry_path: str
    paper_path: str
    total_count: int
    answered_count: int
    graded_count: int
    unscored_count: int
    score: float | None
    score_denominator: int | None
    grading_complete: bool
    started_at: datetime
    completed_at: datetime | None
    sources: list[PracticeRoundSourceOut]


class MatchDecision(BaseModel):
    quiz_id: str = Field(description="候选中的原始习题 id")
    relevant: bool = Field(description="题目是否符合用户确认的主题")
    reason: PracticeMatchReason = Field(
        description=(
            "判定依据：TOPIC_CONCEPT=主题核心概念；TOPIC_APPLICATION=主题知识应用；"
            "OUT_OF_TOPIC=偏离主题；UNCERTAIN=无法确认。只用类别，不生成答案或自由文本理由"
        )
    )

    @model_validator(mode="after")
    def check_reason(self) -> "MatchDecision":
        if self.relevant != (
            self.reason
            in (PracticeMatchReason.TOPIC_CONCEPT, PracticeMatchReason.TOPIC_APPLICATION)
        ):
            raise ValueError("相关性与判定依据不一致")
        return self


class PracticeMatchOutput(BaseModel):
    decisions: list[MatchDecision] = Field(description="每个候选恰好一个判断，包含不相关题")
