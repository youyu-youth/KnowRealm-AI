from datetime import UTC, datetime
from enum import StrEnum

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


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    learning_context: LearningContext
    education_stage: EducationStage | None
    depth: LearningDepth | None
    course_type: CourseType | None
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_utc(self, value: datetime) -> str:
        utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")
