from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self, cast

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
    MULTIPLE_SELECT = "MULTIPLE_SELECT"
    TRUE_FALSE = "TRUE_FALSE"
    FILL_BLANK = "FILL_BLANK"
    SHORT_ANSWER = "SHORT_ANSWER"


class QuizLearningEventType(StrEnum):
    ANSWERED = "QUIZ_ANSWERED"


class QuizLearningEventSourceType(StrEnum):
    QUESTION = "QUIZ_QUESTION"


class QuizQuestionCandidate(BaseModel):
    """LLM 结构化输出的单题候选，题型形状在 Schema 层就地校验。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    question_type: Literal[
        "MULTIPLE_CHOICE", "MULTIPLE_SELECT", "TRUE_FALSE", "FILL_BLANK", "SHORT_ANSWER"
    ] = Field(description="题型：单选题 / 多选题 / 判断题 / 填空题 / 简答题")
    stem: str = Field(min_length=1, max_length=500, description="题干")
    options: list[str] = Field(
        max_length=5,
        description="选项文本；判断题固定两项「对 / 错」，填空题与简答题为空数组",
    )
    correct_answer: int | str | list[int] | list[list[str]] = Field(
        description=(
            "单选题 / 判断题为正确项下标；多选题为正确项下标数组；"
            "填空题为逐空可接受答案数组；简答题为参考答案文本"
        )
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
        elif self.question_type == "MULTIPLE_SELECT":
            if not 3 <= len(self.options) <= 5:
                raise ValueError("多选题必须有 3 至 5 个选项")
            if (
                not isinstance(self.correct_answer, list)
                or not self.correct_answer
                or not all(isinstance(item, int) for item in self.correct_answer)
            ):
                raise ValueError("多选题正确答案必须是非空选项下标数组")
            answer_indexes = cast(list[int], self.correct_answer)
            if len(set(answer_indexes)) != len(answer_indexes) or any(
                item < 0 or item >= len(self.options) for item in answer_indexes
            ):
                raise ValueError("多选题正确答案下标必须唯一且位于选项范围内")
        elif self.question_type == "TRUE_FALSE":
            if tuple(self.options) != TRUE_FALSE_OPTIONS:
                raise ValueError("判断题选项固定为「对 / 错」两项")
            if not isinstance(self.correct_answer, int) or self.correct_answer not in (0, 1):
                raise ValueError("判断题正确答案必须是 0 或 1")
        elif self.question_type == "FILL_BLANK":
            if self.options:
                raise ValueError("填空题选项必须为空数组")
            if (
                not isinstance(self.correct_answer, list)
                or not self.correct_answer
                or not all(isinstance(item, list) for item in self.correct_answer)
            ):
                raise ValueError("填空题正确答案必须是逐空可接受答案数组")
            blank_answers = cast(list[list[str]], self.correct_answer)
            if len(blank_answers) != self.stem.count("____"):
                raise ValueError("填空题空位数量必须与正确答案数量一致")
            if any(
                not answers
                or len(set(answers)) != len(answers)
                or any(
                    answer != answer.strip() or not 1 <= len(answer) <= 100 for answer in answers
                )
                for answers in blank_answers
            ):
                raise ValueError("填空题每空必须有唯一且不含首尾空白的可接受答案")
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
    question_types: list[QuizQuestionType] = Field(min_length=1, max_length=5)
    total_count: Literal[3, 5, 10] = Field(description="总题数档位")

    @field_validator("question_types")
    @classmethod
    def reject_duplicates(cls, value: list[QuizQuestionType]) -> list[QuizQuestionType]:
        if len(set(value)) != len(value):
            raise ValueError("题型不能重复")
        return value

    @model_validator(mode="after")
    def reject_more_types_than_questions(self) -> Self:
        if len(self.question_types) > self.total_count:
            raise ValueError("题型数量不能超过总题数")
        return self


class QuizObjectiveAnswerRequest(BaseModel):
    answer: int | list[int] | list[str] = Field(
        description="单选 / 判断题为一个下标，多选题为下标数组，填空题为逐空答案数组"
    )

    @field_validator("answer")
    @classmethod
    def validate_answer(cls, value: int | list[int] | list[str]) -> int | list[int] | list[str]:
        if isinstance(value, int):
            if value < 0:
                raise ValueError("选项下标不能为负数")
            return value
        if not value:
            raise ValueError("客观题作答不能为空")
        if all(isinstance(item, int) for item in value):
            indexes = cast(list[int], value)
            if any(item < 0 for item in indexes) or len(set(indexes)) != len(indexes):
                raise ValueError("多选题下标必须非负且不能重复")
            return sorted(indexes)
        answers = cast(list[str], value)
        if any(not answer.strip() or len(answer) > 100 for answer in answers):
            raise ValueError("填空题每个空位都必须作答且不超过 100 字")
        return [answer.strip() for answer in answers]


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
    correct_answer: int | str | list[int] | list[list[str]] | None
    explanation: str | None
    difficulty: QuizDifficulty
    user_answer: int | str | list[int] | list[str] | None = None
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
