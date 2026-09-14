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


class ChatScope(StrEnum):
    """会话挂载范围（B2）：FREE 自由 / RECORD 单记录 / COURSE 课程 / ALL 全部资料。

    与 mode 轴正交（mode 恒 ASK，交互形态留给 B3）；范围会话内不可变。
    """

    FREE = "FREE"
    RECORD = "RECORD"
    COURSE = "COURSE"
    ALL = "ALL"


class ChatRole(StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"
    TOOL = "TOOL"


class ChatSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal[ChatMode.ASK] = Field(default=ChatMode.ASK, description="会话模式")
    scope: ChatScope | None = Field(
        default=None,
        description="会话范围；不传时按 record_id 派生（非空 → RECORD，否则 FREE），旧调用方零破坏",
    )
    record_id: UUID | None = Field(default=None, description="挂载的学习记录，空为自由聊天")
    course_id: UUID | None = Field(default=None, description="课程范围会话挂载的课程")
    knowledge_point_id: UUID | None = Field(
        default=None, description="知识点解释入口的知识点快照来源"
    )

    @model_validator(mode="after")
    def validate_scope_matrix(self) -> "ChatSessionCreate":
        """范围 × 挂载 id 校验矩阵；派生后写回 scope，调用方读取到的一定是显式值。"""
        scope = self.scope or (ChatScope.RECORD if self.record_id is not None else ChatScope.FREE)
        if scope == ChatScope.RECORD:
            if self.record_id is None:
                raise ValueError("RECORD 范围必须挂载学习记录")
            if self.course_id is not None:
                raise ValueError("RECORD 范围的课程由挂载记录派生，不接受 course_id")
        elif scope == ChatScope.COURSE:
            if self.course_id is None:
                raise ValueError("COURSE 范围必须指定课程")
            if self.record_id is not None:
                raise ValueError("COURSE 范围不接受 record_id")
            if self.knowledge_point_id is not None:
                raise ValueError("知识点解释仅支持 RECORD 范围会话")
        else:
            if self.record_id is not None or self.course_id is not None:
                raise ValueError("FREE/ALL 范围不能携带挂载 id")
            if self.knowledge_point_id is not None:
                raise ValueError("知识点解释仅支持 RECORD 范围会话")
        self.scope = scope
        return self


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
    web_search: bool = Field(
        default=False, description="本轮是否允许联网搜索；无 key 时后端强制忽略"
    )

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
    scope: ChatScope = Field(default=ChatScope.FREE, description="会话挂载范围")
    title: str | None = Field(default=None, description="会话标题，未重命名时为空")
    record_id: str | None = Field(default=None, description="挂载的学习记录，RECORD 会话非空")
    course_id: str | None = Field(
        default=None,
        description="COURSE 会话挂载的课程；RECORD 会话为挂载记录所属课程（运行时派生）",
    )
    record_deleted: bool = Field(
        default=False, description="挂载记录已软删（运行时推导，无失效列），会话只读"
    )
    course_deleted: bool = Field(
        default=False, description="COURSE 会话挂载课程已软删（运行时推导），会话只读"
    )
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_utc(self, value: datetime) -> str:
        return _iso_utc(value)


class ChatCitationOut(BaseModel):
    """回答引用：record=转写摘录（逐字校验），web=网络来源（标题+URL，B1）。

    citations_json 按条目判别化：record 条目 {index, record_id, quote}（历史
    行无 source 键，按默认 "record" 读取）；web 条目 {index, source:"web",
    url, title}。跨记录条目（B2）额外携带 record_title（标题快照，创建时
    固化；历史行无此键 → None，前端降级展示）。
    """

    index: int = Field(ge=1, description="正文角标序号")
    source: Literal["record", "web"] = Field(default="record", description="来源类型")
    record_id: str | None = Field(default=None, description="被引用的学习记录 ID，web 来源为空")
    record_title: str | None = Field(
        default=None, max_length=200, description="被引用记录的标题快照（跨记录引用），历史行为空"
    )
    quote: str | None = Field(
        default=None, max_length=80, description="转写原文摘录（≤80 字），web 来源为空"
    )
    url: str | None = Field(default=None, description="网络来源 URL，record 来源为空")
    title: str | None = Field(default=None, description="网络来源标题，record 来源为空")

    @model_validator(mode="after")
    def require_fields_for_source(self) -> "ChatCitationOut":
        if self.source == "record":
            if not self.record_id or not self.quote:
                raise ValueError("record 引用必须携带 record_id 与 quote")
        elif not self.url or not self.title:
            raise ValueError("web 引用必须携带 url 与 title")
        return self


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
