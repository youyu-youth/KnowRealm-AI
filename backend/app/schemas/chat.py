import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, cast
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_serializer,
    field_validator,
    model_validator,
)


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
    model_config = ConfigDict(extra="forbid")

    mode: Literal[ChatMode.ASK] = Field(default=ChatMode.ASK, description="会话模式")
    record_id: UUID | None = Field(default=None, description="挂载的学习记录，空为自由聊天")


class ChatSessionRename(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=100, description="会话标题")

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("会话标题不能为空白")
        return cleaned


class ChatRecordOption(BaseModel):
    id: str = Field(description="学习记录 ID")
    title: str = Field(description="学习记录标题")
    course_id: str | None = Field(description="课程 ID，收件箱记录为空")
    has_transcript: bool = Field(description="存在可用转写时可挂载")


class ChatMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=8000, description="用户消息文本")

    @field_validator("content")
    @classmethod
    def clean_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("消息内容不能为空白")
        return cleaned


def _iso_utc(value: datetime) -> str:
    utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")


class ChatSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    mode: ChatMode
    title: str | None = Field(default=None, description="会话标题，未重命名时为空")
    record_id: str | None = Field(default=None, description="挂载的学习记录，自由聊天为空")
    course_id: str | None = Field(default=None, description="挂载记录所属课程，自由聊天为空")
    record_deleted: bool = Field(
        default=False, description="挂载记录已软删（运行时推导，无失效列），会话只读"
    )
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_utc(self, value: datetime) -> str:
        return _iso_utc(value)


class ChatCitationOut(BaseModel):
    """回答引用：正文 [n] 角标对应的一条转写摘录。"""

    index: int = Field(ge=1, description="正文角标序号")
    record_id: str = Field(description="被引用的学习记录 ID")
    quote: str = Field(max_length=80, description="转写原文摘录，不超过 80 字")


def parse_citations(raw: str | None) -> list[ChatCitationOut]:
    """citations_json → 引用列表；坏数据容忍，返回已通过落库前校验的条目。"""
    if raw is None:
        return []
    try:
        value = json.loads(raw)
    except ValueError:
        return []
    if not isinstance(value, list):
        return []
    citations: list[ChatCitationOut] = []
    for entry in cast(list[object], value):
        if not isinstance(entry, dict):
            continue
        try:
            citations.append(ChatCitationOut.model_validate(entry))
        except ValidationError:
            continue
    return citations


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: ChatRole
    content: str
    model: str | None = Field(default=None, description="生成该条回答的模型，user/system 行为空")
    citations_json: str | None = Field(default=None, exclude=True)
    citations: list[ChatCitationOut] = Field(
        default_factory=list[ChatCitationOut], description="回答引用，无引用为空"
    )
    created_at: datetime

    @model_validator(mode="after")
    def load_citations(self) -> "ChatMessageOut":
        self.citations = parse_citations(self.citations_json)
        return self

    @field_serializer("created_at")
    def serialize_utc(self, value: datetime) -> str:
        return _iso_utc(value)
