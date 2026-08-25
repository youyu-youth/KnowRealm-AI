from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

QUIZ_COUNT_CHOICES = (3, 5, 10)
TRUE_FALSE_OPTIONS = ("对", "错")


class QuizQuestionType(StrEnum):
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
    TRUE_FALSE = "TRUE_FALSE"
    SHORT_ANSWER = "SHORT_ANSWER"


class QuizLearningEventType(StrEnum):
    ANSWERED = "QUIZ_ANSWERED"


class QuizLearningEventSourceType(StrEnum):
    QUESTION = "QUIZ_QUESTION"


class QuizQuestionCandidate(BaseModel):
    """LLM 结构化输出的单题候选，题型形状在 Schema 层就地校验。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    question_type: Literal["MULTIPLE_CHOICE", "TRUE_FALSE", "SHORT_ANSWER"] = Field(
        description="题型：单选选择题 / 判断题 / 简答题"
    )
    stem: str = Field(min_length=1, max_length=500, description="题干")
    options: list[str] = Field(
        max_length=5, description="选项文本；判断题固定两项「对 / 错」，简答题为空数组"
    )
    correct_answer: int | str = Field(
        description="选择题 / 判断题为正确项下标（从 0 开始），简答题为参考答案文本"
    )
    explanation: str = Field(min_length=1, max_length=2000, description="解析")
    difficulty: Literal["EASY", "MEDIUM", "HARD"] = Field(description="难度三档")

    @field_validator("stem", "explanation")
    @classmethod
    def reject_surrounding_whitespace(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("题干与解析不能包含首尾空白")
        return value

    @model_validator(mode="after")
    def validate_question_shape(self) -> Self:
        if any(option != option.strip() or not 1 <= len(option) <= 100 for option in self.options):
            raise ValueError("每个选项必须为 1 至 100 字且不含首尾空白")
        if self.question_type == "MULTIPLE_CHOICE":
            if not 3 <= len(self.options) <= 5:
                raise ValueError("选择题必须有 3 至 5 个选项")
            if not isinstance(self.correct_answer, int) or not 0 <= self.correct_answer < len(
                self.options
            ):
                raise ValueError("选择题正确答案必须是选项下标")
        elif self.question_type == "TRUE_FALSE":
            if tuple(self.options) != TRUE_FALSE_OPTIONS:
                raise ValueError("判断题选项固定为「对 / 错」两项")
            if not isinstance(self.correct_answer, int) or self.correct_answer not in (0, 1):
                raise ValueError("判断题正确答案必须是 0 或 1")
        else:
            if self.options:
                raise ValueError("简答题选项必须为空数组")
            if (
                not isinstance(self.correct_answer, str)
                or not 1 <= len(self.correct_answer) <= 2000
            ):
                raise ValueError("简答题正确答案必须是 1 至 2000 字的参考答案")
        return self


class QuizBatch(BaseModel):
    """一次 LLM 调用产出的整批候选；总数与题型构成依赖请求参数，由 worker 侧校验。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    items: list[QuizQuestionCandidate] = Field(min_length=1, max_length=10)


class QuizGenerationStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"


class QuizDifficulty(StrEnum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


class QuizAnswerResult(StrEnum):
    CORRECT = "CORRECT"
    WRONG = "WRONG"


class QuizAction(StrEnum):
    NONE = "NONE"
    GENERATE = "GENERATE"
    ADOPT = "ADOPT"
    RETRY = "RETRY"


class QuizBlockedReason(StrEnum):
    SUMMARY_NOT_CONFIRMED = "SUMMARY_NOT_CONFIRMED"
    SUMMARY_SUPERSEDED = "SUMMARY_SUPERSEDED"
    COURSE_ARCHIVED = "COURSE_ARCHIVED"
    PROVIDER_NOT_CONFIGURED = "PROVIDER_NOT_CONFIGURED"
    CONSENT_REQUIRED = "CONSENT_REQUIRED"


class QuizGenerateRequest(BaseModel):
    question_types: list[QuizQuestionType] = Field(min_length=1, max_length=3)
    total_count: Literal[3, 5, 10] = Field(description="总题数档位")

    @field_validator("question_types")
    @classmethod
    def reject_duplicates(cls, value: list[QuizQuestionType]) -> list[QuizQuestionType]:
        if len(set(value)) != len(value):
            raise ValueError("题型不能重复")
        return value


class QuizObjectiveAnswerRequest(BaseModel):
    answer: int = Field(ge=0, description="用户所选选项的下标（从 0 开始）")


class QuizShortAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=2000, description="用户提交的简答作答")

    @field_validator("answer")
    @classmethod
    def reject_blank_answer(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("简答作答不能为空")
        return value


class QuizSelfAssessmentRequest(BaseModel):
    result: QuizAnswerResult


class QuizOut(BaseModel):
    id: str
    record_id: str
    batch_id: str | None
    generated_from_summary_id: str | None
    generation_status: QuizGenerationStatus
    question_type: QuizQuestionType
    stem: str
    options: list[str]
    correct_answer: int | str | None
    explanation: str | None
    difficulty: QuizDifficulty
    user_answer: int | str | None = None
    answer_result: QuizAnswerResult | None = None
    answered_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @field_serializer("answered_at", "created_at", "updated_at")
    def serialize_utc(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")


class QuizReadOut(BaseModel):
    items: list[QuizOut]
    action_required: QuizAction
    active_job_id: str | None = None
    blocked_reason: QuizBlockedReason | None = None


class QuizConflictResponse(BaseModel):
    detail: str
    blocked_reason: QuizBlockedReason


class QuizJobAccepted(BaseModel):
    job_id: str
