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

from app.modules.agent.runs.schemas import AuthMode
from app.modules.capture.text_capture import MAX_TEXT_BYTES
from app.modules.course.schemas import CourseCreate
from app.modules.knowledge_point.schemas import KnowledgePointWriteRequest
from app.modules.library.schemas import ChatScope


class ChatMode(StrEnum):
    ASK = "ASK"
    COURSE_QA = "COURSE_QA"
    SOCRATIC_TUTOR = "SOCRATIC_TUTOR"
    TEACH_BACK = "TEACH_BACK"
    RESEARCH = "RESEARCH"


class ChatRole(StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"
    TOOL = "TOOL"


class ChatSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal[ChatMode.ASK, ChatMode.RESEARCH] = Field(
        default=ChatMode.ASK, description="会话模式（研究会话 V1 起放开 RESEARCH）"
    )
    scope: ChatScope | None = Field(
        default=None,
        description="会话范围；不传时按 record_id 派生（非空 → RECORD，否则 FREE），旧调用方零破坏",
    )
    record_id: UUID | None = Field(default=None, description="挂载的学习记录，空为自由聊天")
    course_id: UUID | None = Field(default=None, description="课程范围会话挂载的课程")
    library_item_id: UUID | None = Field(
        default=None, description="资料范围会话挂载的资料条目（仅资料详情入口创建）"
    )
    knowledge_point_id: UUID | None = Field(
        default=None, description="知识点解释入口的知识点快照来源"
    )

    @model_validator(mode="after")
    def validate_scope_matrix(self) -> "ChatSessionCreate":
        """范围 × 挂载 id 校验矩阵；派生后写回 scope，调用方读取到的一定是显式值。"""
        scope = self.scope or (
            ChatScope.RECORD
            if self.record_id is not None
            else ChatScope.LIBRARY_ITEM
            if self.library_item_id is not None
            else ChatScope.FREE
        )
        if scope == ChatScope.RECORD:
            if self.record_id is None:
                raise ValueError("RECORD 范围必须挂载学习记录")
            if self.course_id is not None:
                raise ValueError("RECORD 范围的课程由挂载记录派生，不接受 course_id")
        elif scope == ChatScope.LIBRARY_ITEM:
            if self.library_item_id is None:
                raise ValueError("LIBRARY_ITEM 范围必须挂载资料条目")
            if self.record_id is not None or self.course_id is not None:
                raise ValueError("LIBRARY_ITEM 范围的记录与课程由资料条目派生，不接受挂载 id")
            if self.knowledge_point_id is not None:
                raise ValueError("知识点解释仅支持 RECORD 范围会话")
        elif scope == ChatScope.COURSE:
            if self.course_id is None:
                raise ValueError("COURSE 范围必须指定课程")
            if self.record_id is not None:
                raise ValueError("COURSE 范围不接受 record_id")
            if self.library_item_id is not None:
                raise ValueError("COURSE 范围不接受 library_item_id")
            if self.knowledge_point_id is not None:
                raise ValueError("知识点解释仅支持 RECORD 范围会话")
        else:
            if (
                self.record_id is not None
                or self.course_id is not None
                or self.library_item_id is not None
            ):
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


class ChatPageSnapshot(BaseModel):
    """随消息携带的轻量页面快照（通用 Agent 工单 01）：仅提示用户当前所在
    页面，不落库、不构成授权、不扩大读取范围。

    字段分工：page_type 与 entity_id 经后端重校验（失效引用静默丢弃，见
    message_service）后注入模型上下文；selected_id 与 captured_at 只随快照进
    运行时上下文（供后续操作工具按需消费），不进提示文本——对象名与页面
    位置对模型有用，原始选中 id 与客户端时钟是噪音。
    """

    model_config = ConfigDict(extra="forbid")

    page_type: Literal["chat", "course", "record", "library", "inbox"] = Field(
        description="发送消息时所在页面类型"
    )
    entity_id: str | None = Field(
        default=None, max_length=64, description="页面当前实体 id（如课程/记录 id）"
    )
    selected_id: str | None = Field(default=None, max_length=64, description="页面内选中对象 id")
    captured_at: datetime = Field(description="快照生成时间（客户端时钟）")


class ChatMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=8000, description="用户消息文本")
    web_search: bool = Field(
        default=False, description="本轮是否允许联网搜索；无 key 时后端强制忽略"
    )
    page: ChatPageSnapshot | None = Field(
        default=None, description="可选页面快照（提示信息，不构成授权）"
    )
    auth_mode: AuthMode | None = Field(
        default=None,
        description="会话授权档位覆盖（前端按会话内存携带）；不携带＝全局默认档",
    )

    @field_validator("content")
    @classmethod
    def clean_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("消息内容不能为空白")
        return cleaned


class ChatKnowledgePointSaveRequest(KnowledgePointWriteRequest):
    """对话转知识点（对话转学习资产 V1）请求体。

    继承手工新增的校验边界，但显式关闭 strict（pydantic config 为合并语义，
    不写则继承 True；target_record_id 经 JSON 字符串传入，strict 下 UUID
    不接受字符串）。
    """

    model_config = ConfigDict(extra="forbid", strict=False)

    target_record_id: UUID = Field(description="知识点归属的目标学习记录")


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
        description="COURSE 会话挂载的课程；RECORD/LIBRARY_ITEM 会话为挂载对象"
        "所属课程（运行时派生）",
    )
    library_item_id: str | None = Field(
        default=None, description="挂载的资料条目，LIBRARY_ITEM 会话非空"
    )
    record_deleted: bool = Field(
        default=False, description="挂载记录已软删（运行时推导，无失效列），会话只读"
    )
    course_deleted: bool = Field(
        default=False, description="COURSE 会话挂载课程已软删（运行时推导），会话只读"
    )
    library_item_deleted: bool = Field(
        default=False,
        description="LIBRARY_ITEM 会话挂载资料已删除/归档（运行时推导），会话只读",
    )
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_utc(self, value: datetime) -> str:
        return _iso_utc(value)


class ChatCitationOut(BaseModel):
    """回答引用：record=转写摘录（逐字校验）、web=网络来源（标题+URL，B1）、
    library=资料条目正文摘录（资料直挂分片逐字校验，工单 04）。

    citations_json 按条目判别化：record 条目 {index, record_id, quote}（历史
    行无 source 键，按默认 "record" 读取）；web 条目 {index, source:"web",
    url, title}；library 条目 {index, source:"library", library_item_id,
    title, quote}。跨记录条目（B2）额外携带 record_title（标题快照，创建时
    固化；历史行无此键 → None，前端降级展示）。
    """

    index: int = Field(ge=1, description="正文角标序号")
    source: Literal["record", "web", "library"] = Field(default="record", description="来源类型")
    record_id: str | None = Field(default=None, description="被引用的学习记录 ID，web 来源为空")
    record_title: str | None = Field(
        default=None, max_length=200, description="被引用记录的标题快照（跨记录引用），历史行为空"
    )
    library_item_id: str | None = Field(
        default=None, description="被引用的资料条目 ID，library 条目必填"
    )
    quote: str | None = Field(
        default=None, max_length=80, description="本地原文摘录（≤80 字逐字），web 来源为空"
    )
    url: str | None = Field(default=None, description="网络来源 URL，record/library 来源为空")
    title: str | None = Field(default=None, description="网络来源或资料条目标题，record 来源为空")
    anchor_id: str | None = Field(
        default=None, description="来源锚点 ID（预留：锚点写入者产生，当前为空）"
    )

    @model_validator(mode="after")
    def require_fields_for_source(self) -> "ChatCitationOut":
        if self.source == "record":
            if not self.record_id or not self.quote:
                raise ValueError("record 引用必须携带 record_id 与 quote")
        elif self.source == "library":
            if not self.library_item_id or not self.quote:
                raise ValueError("library 引用必须携带 library_item_id 与 quote")
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


# ---------------------------------------------------------------------------
# 操作提案契约（agent/operations 注册消费，先例：library/schemas.py 提案载荷）


class CourseCreatePayload(CourseCreate):
    """COURSE_CREATE 提案判别载荷：字段与校验复用 HTTP 创建契约 CourseCreate
    （同源零漂移），仅收紧未知键拒绝（extra=forbid，ADR-0024 载荷纪律）。"""

    model_config = ConfigDict(extra="forbid")


class CourseCreateResult(BaseModel):
    """COURSE_CREATE 结果投影（操作回执，spec 决策 8：课程创建 → 课程 id）。"""

    course_id: str


class TextRecordAddPayload(BaseModel):
    """TEXT_RECORD_ADD 提案判别载荷（工单 03）：目标课程 id + 文本正文。

    course_id 是 search_courses 消歧后固化进提案的目标（spec 决策 9「固定目标」：
    切页不影响）；正文空/超限在提案创建时结构化拒绝（空 → 缺失项，超限 → 模型级
    detail），由模型转述（spec 决策 2），领域核心兜底同口径校验。
    """

    model_config = ConfigDict(extra="forbid")

    course_id: str = Field(
        pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
        description="目标课程 id（经 search_courses 查找消歧后取得）",
    )
    content: str = Field(min_length=1, description="要保存的文本正文（上限 1 MiB）")

    @model_validator(mode="after")
    def _content_within_size_limit(self) -> "TextRecordAddPayload":
        if len(self.content.encode("utf-8")) > MAX_TEXT_BYTES:
            raise ValueError("正文超过 1 MiB 上限，请改用 TXT 或 MD 文档导入")
        return self


class TextRecordAddResult(BaseModel):
    """TEXT_RECORD_ADD 结果投影（spec 决策 8/15）：记录 id + 总结任务真实状态。

    summary_job_id 与 summary_error_code 互斥：提交成功 → 任务 id；提交失败 →
    错误码（记录已保存，不回滚）；均 None → 总结未触发（AI 未配置或未同意外发）。
    """

    record_id: str
    summary_job_id: str | None = None
    summary_error_code: str | None = None
