from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


class ChatMode(StrEnum):
    ASK = "ASK"
    COURSE_QA = "COURSE_QA"
    SOCRATIC_TUTOR = "SOCRATIC_TUTOR"
    TEACH_BACK = "TEACH_BACK"


class ChatRole(StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"
    TOOL = "TOOL"


class ChatSessionCreate(BaseModel):
    # 本阶段仅自由聊天（无挂载的 ASK）；挂载对话随后续工单扩展。
    mode: Literal[ChatMode.ASK] = Field(default=ChatMode.ASK, description="会话模式")


class ChatSessionRename(BaseModel):
    title: str = Field(min_length=1, max_length=100, description="会话标题")

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("会话标题不能为空白")
        return cleaned


class ChatSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    mode: ChatMode
    title: str | None = Field(default=None, description="会话标题，未重命名时为空")
    record_id: str | None = Field(default=None, description="挂载的学习记录，自由聊天为空")
    course_id: str | None = Field(default=None, description="挂载记录所属课程，自由聊天为空")
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_utc(self, value: datetime) -> str:
        utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")
