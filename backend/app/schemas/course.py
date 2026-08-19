import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, cast

from loguru import logger
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)


class LearningContext(StrEnum):
    SCHOOL = "SCHOOL"
    CAREER = "CAREER"
    INTEREST = "INTEREST"


class EducationStage(StrEnum):
    MIDDLE_SCHOOL = "MIDDLE_SCHOOL"
    HIGH_SCHOOL = "HIGH_SCHOOL"
    UNDERGRADUATE = "UNDERGRADUATE"
    GRADUATE = "GRADUATE"
    DOCTORAL = "DOCTORAL"


class LearningDepth(StrEnum):
    BEGINNER = "BEGINNER"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"


class CourseType(StrEnum):
    MAJOR = "MAJOR"
    GENERAL = "GENERAL"
    ELECTIVE = "ELECTIVE"


class CourseStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class ErrorResponse(BaseModel):
    detail: str = Field(description="可直接展示的错误说明")


class CourseListQuery(BaseModel):
    q: str | None = Field(default=None, max_length=100, description="课程名称子串")
    education_stage: EducationStage | None = Field(default=None, description="教育阶段筛选")
    course_type: CourseType | None = Field(default=None, description="课程类型筛选")

    @field_validator("q", mode="before")
    @classmethod
    def clean_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class CourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="课程名称")
    learning_context: LearningContext = Field(description="课程学习场景")
    education_stage: EducationStage | None = Field(default=None, description="学业教育阶段")
    depth: LearningDepth | None = Field(default=None, description="职业或兴趣学习深度")
    course_type: CourseType | None = Field(default=None, description="可选课程类型")
    description: str | None = Field(default=None, description="可选课程说明")

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("课程名称不能为空白")
        return cleaned

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def validate_context_fields(self) -> "CourseCreate":
        if self.learning_context is LearningContext.SCHOOL:
            if self.education_stage is None:
                raise ValueError("学业场景必须选择教育阶段")
            self.depth = None
        else:
            if self.depth is None:
                raise ValueError("职业或兴趣场景必须选择学习深度")
            self.education_stage = None
        return self


class CourseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100, description="课程名称")
    learning_context: LearningContext | None = Field(default=None, description="课程学习场景")
    education_stage: EducationStage | None = Field(default=None, description="学业教育阶段")
    depth: LearningDepth | None = Field(default=None, description="职业或兴趣学习深度")
    course_type: CourseType | None = Field(default=None, description="可选课程类型")
    description: str | None = Field(default=None, description="可选课程说明")
    hot_words: list[str] | None = Field(
        default=None,
        max_length=100,
        description="按输入顺序保存的 ASR 手动热词",
    )

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("课程名称不能为空白")
        return cleaned

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("hot_words")
    @classmethod
    def clean_hot_words(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [word.strip() for word in value]
        if any(not word for word in cleaned):
            raise ValueError("热词不能为空白")
        return cleaned


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    learning_context: LearningContext
    education_stage: EducationStage | None
    depth: LearningDepth | None
    course_type: CourseType | None
    description: str | None
    status: CourseStatus
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_utc(self, value: datetime) -> str:
        utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")


class CourseDetailOut(CourseOut):
    hot_words: list[str] = Field(default_factory=list, description="ASR 热词摘要")

    @field_validator("hot_words", mode="before")
    @classmethod
    def parse_hot_words(cls, value: Any) -> list[str]:
        if value is None:
            return []
        # 列在 ORM 中是 TEXT 存储的 JSON 数组；元素类型静态未知（cast），逐项运行时收窄。
        try:
            parsed: object = json.loads(value) if isinstance(value, str) else value
        except json.JSONDecodeError:
            # 隐私红线：日志不携带热词内容，只记录事件本身。
            logger.warning("course_hot_words_json_invalid")
            return []
        if not isinstance(parsed, list):
            logger.warning("course_hot_words_json_invalid")
            return []
        return [word for word in cast("list[object]", parsed) if isinstance(word, str)]
