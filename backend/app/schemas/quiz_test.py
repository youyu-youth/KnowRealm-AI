from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_serializer, field_validator

from app.schemas.quiz import QuizDifficulty, QuizQuestionType


class QuizTestMode(StrEnum):
    MOCK = "MOCK"
    ADAPTIVE = "ADAPTIVE"


class QuizTestStatus(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    GRADING = "GRADING"
    GRADING_FAILED = "GRADING_FAILED"
    COMPLETED = "COMPLETED"
    ABANDONED = "ABANDONED"


class QuizTestItemResult(StrEnum):
    CORRECT = "CORRECT"
    WRONG = "WRONG"
    PARTIAL = "PARTIAL"


class QuizTestBlockedReason(StrEnum):
    COURSE_ARCHIVED = "COURSE_ARCHIVED"
    NO_AVAILABLE_QUIZZES = "NO_AVAILABLE_QUIZZES"


def _iso_utc(value: datetime) -> str:
    utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _serialize_utc(value: datetime | None) -> str | None:
    return _iso_utc(value) if value is not None else None


class QuizTestCreateRequest(BaseModel):
    question_types: list[QuizQuestionType] = Field(min_length=1, max_length=5)
    total_count: Literal[5, 10, 20]

    @field_validator("question_types")
    @classmethod
    def reject_duplicate_types(cls, value: list[QuizQuestionType]) -> list[QuizQuestionType]:
        if len(set(value)) != len(value):
            raise ValueError("题型不能重复")
        return value


class QuizTestSummaryOut(BaseModel):
    id: str
    course_id: str
    record_id: None
    mode: QuizTestMode
    status: QuizTestStatus
    score: float | None
    total_count: int
    answered_count: int
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @field_serializer("started_at", "created_at", "updated_at")
    def serialize_utc(self, value: datetime) -> str:
        return _iso_utc(value)

    @field_serializer("completed_at")
    def serialize_completed_at(self, value: datetime | None) -> str | None:
        return _serialize_utc(value)


class QuizTestCreateOut(BaseModel):
    test: QuizTestSummaryOut
    requested_count: int
    selected_count: int
    shortage: bool


class QuizTestListOut(BaseModel):
    items: list[QuizTestSummaryOut]
    blocked_reason: QuizTestBlockedReason | None = None


class QuizTestItemOut(BaseModel):
    id: str
    quiz_id: str
    sequence_no: int
    question_type: QuizQuestionType
    stem: str
    options: list[str]
    difficulty: QuizDifficulty
    user_answer: int | str | list[int] | list[str] | None
    result: QuizTestItemResult | None
    score: float | None
    answered_at: datetime | None

    @field_serializer("answered_at")
    def serialize_answered_at(self, value: datetime | None) -> str | None:
        return _serialize_utc(value)


class QuizTestDetailOut(QuizTestSummaryOut):
    items: list[QuizTestItemOut]


class QuizTestConflictOut(BaseModel):
    detail: str
    blocked_reason: QuizTestBlockedReason
