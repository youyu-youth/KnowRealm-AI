import json
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any, Literal, cast
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
from app.modules.course.schemas import (
    CourseCreate,
    CourseType,
    CourseUpdate,
    EducationStage,
    LearningContext,
    LearningDepth,
)
from app.modules.knowledge_point.schemas import KnowledgePointWriteRequest
from app.modules.learning_plan.schemas import (
    GoalType,
    PlanConfirmCore,
    PlanItemUpdate,
    PlanRegenerateCore,
    clean_goal_title,
)
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
    shared: bool | None = Field(
        default=None,
        description="共享来源标志（工单 05）：命中经共享引用覆盖的归属他空间资料时为 true，"
        "前端展示「共享来源」徽章；历史行与本地资料为空",
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


def parse_executed_operation_ids(raw: str | None) -> list[str]:
    """executed_operations_json → 直执行 operation_id 列表（坏数据容忍，
    与 parse_citations 同口径）；锚点只判定存在性，详情经 agent_operations 查询。"""
    if raw is None:
        return []
    try:
        value: object = json.loads(raw)
    except ValueError:
        return []
    if not isinstance(value, list):
        return []
    return [item for item in cast(list[object], value) if isinstance(item, str)]


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
    executed_operations_json: str | None = Field(default=None, exclude=True)
    executed_operation_ids: list[str] = Field(
        default_factory=list[str],
        description="本轮直执行回执锚点（operation_id 列表；详情经操作历史查询）",
    )
    created_at: datetime

    @model_validator(mode="after")
    def load_message_payloads(self) -> "ChatMessageOut":
        self.citations = parse_citations(self.citations_json)
        self.executed_operation_ids = parse_executed_operation_ids(self.executed_operations_json)
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


# ---------------------------------------------------------------------------
# 修改与归档动作契约（通用 Agent 第二阶段工单 03，spec 决策 12/14）：快照由
# 后端在提交时同事务读取固化（模型不提供），before/after 进确认卡与回执。
# ---------------------------------------------------------------------------

_UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


class CourseStateSnapshot(BaseModel):
    """course.* 修改 / 归档动作的执行前快照（spec 决策 12）。

    updated_at（微秒精度）＋before 值双保险承载版本依据（不给业务表加 version
    列）；快照一份三用——确认卡预览投影、执行前重验依据、Undo 补偿数据。
    """

    model_config = ConfigDict(extra="forbid")

    updated_at: datetime
    name: str
    status: str
    learning_context: LearningContext
    education_stage: EducationStage | None = None
    depth: LearningDepth | None = None
    course_type: CourseType | None = None
    description: str | None = None


class LibraryItemStateSnapshot(BaseModel):
    """library_item.* 修改 / 归档动作的执行前快照（同 CourseStateSnapshot）。"""

    model_config = ConfigDict(extra="forbid")

    updated_at: datetime
    title: str
    course_id: str | None = None
    status: str


class CourseUpdatePayload(BaseModel):
    """OP_COURSE_UPDATE 提案判别载荷：目标课程 id + 修改字段（spec 用户故事 10）。

    hot_words 是录音设置的手动热词、不接入 Agent；名称在提交时复用 HTTP
    契约校验，场景条件校验在应用器构造 CourseUpdate 时执行。
    """

    model_config = ConfigDict(extra="forbid")

    course_id: str = Field(
        pattern=_UUID_PATTERN,
        description="目标课程 id（经 search_courses 查找消歧后取得）",
    )
    name: str | None = Field(default=None, min_length=1, max_length=100, description="课程名称")
    learning_context: LearningContext | None = Field(default=None, description="课程学习场景")
    education_stage: EducationStage | None = Field(default=None, description="学业教育阶段")
    depth: LearningDepth | None = Field(default=None, description="职业或兴趣学习深度")
    course_type: CourseType | None = Field(default=None, description="课程类型")
    description: str | None = Field(default=None, description="课程说明")

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return CourseUpdate.clean_name(value)

    @model_validator(mode="after")
    def _require_change(self) -> "CourseUpdatePayload":
        provided = self.model_dump(exclude_unset=True)
        if set(provided) <= {"course_id"}:
            raise ValueError("至少提供一个修改字段")
        return self


class CourseUpdateResult(BaseModel):
    """OP_COURSE_UPDATE 结果投影：被修改字段的 before / after 对照（回执卡）。"""

    course_id: str
    before: dict[str, Any]
    after: dict[str, Any]
    # 执行后版本戳（工单 06 review：undo 前重验版本用，spec 决策 19）——
    # 领域写统一维护 updated_at，此后目标被任何写碰过即偏离，撤销拒。
    after_updated_at: datetime | None = None


class CourseArchivePayload(BaseModel):
    """OP_COURSE_ARCHIVE / OP_COURSE_RESTORE 提案判别载荷。"""

    model_config = ConfigDict(extra="forbid")

    course_id: str = Field(
        pattern=_UUID_PATTERN,
        description="目标课程 id（经 search_courses 查找消歧后取得）",
    )


class CourseArchiveResult(BaseModel):
    """OP_COURSE_ARCHIVE / OP_COURSE_RESTORE 结果投影：执行后状态。"""

    course_id: str
    status: str
    # 执行后版本戳（undo 前重验版本用，同 CourseUpdateResult）。
    after_updated_at: datetime | None = None


class LibraryItemUpdatePayload(BaseModel):
    """OP_LIBRARY_ITEM_UPDATE 提案判别载荷：标题 / 归类（spec 用户故事 12）。

    course_id 为 None＝不修改归类（收藏与取消归类不接入，走页面路径）；
    course_id 非 None＝归类到该课程（目标须存在且未归档，领域核心校验）。
    """

    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(
        pattern=_UUID_PATTERN,
        description="目标资料条目 id（经 search_library 查找消歧后取得）",
    )
    title: str | None = Field(default=None, min_length=1, description="条目标题")
    course_id: str | None = Field(default=None, description="归类目标课程 id；None＝不修改归类")

    @model_validator(mode="after")
    def _require_change(self) -> "LibraryItemUpdatePayload":
        provided = self.model_dump(exclude_unset=True)
        if set(provided) <= {"item_id"}:
            raise ValueError("至少提供一个修改字段")
        return self


class LibraryItemUpdateResult(BaseModel):
    """OP_LIBRARY_ITEM_UPDATE 结果投影：被修改字段的 before / after 对照。"""

    item_id: str
    before: dict[str, Any]
    after: dict[str, Any]
    # 执行后版本戳（undo 前重验版本用，同 CourseUpdateResult）。
    after_updated_at: datetime | None = None


class LibraryItemArchivePayload(BaseModel):
    """OP_LIBRARY_ITEM_ARCHIVE / OP_LIBRARY_ITEM_RESTORE 提案判别载荷。"""

    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(
        pattern=_UUID_PATTERN,
        description="目标资料条目 id（经 search_library 查找消歧后取得）",
    )


class LibraryItemArchiveResult(BaseModel):
    """OP_LIBRARY_ITEM_ARCHIVE / OP_LIBRARY_ITEM_RESTORE 结果投影：执行后状态。"""

    item_id: str
    status: str
    # 执行后版本戳（undo 前重验版本用，同 CourseUpdateResult）。
    after_updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# 删除与跨课迁移契约（通用 Agent 第二阶段工单 04，spec 决策 14/15/17/18）：
# 删除类快照固化级联影响清单（课程删除＝记录清单与计数、记录删除＝记录级资产
# 计数），批准后执行前出现实质差异（如新增记录）→ OPERATION_SNAPSHOT_STALE
# 失效重新授权（spec 决策 12 / 用户故事 15）；迁移快照存原 course_id
# （06 票 Undo＝反向迁移的补偿数据）。
# ---------------------------------------------------------------------------


class RecordStateSnapshot(BaseModel):
    """record.move_course 执行前快照（spec 决策 12/17）：原 course_id 是 Undo
    反向迁移的补偿数据。"""

    model_config = ConfigDict(extra="forbid")

    updated_at: datetime
    title: str
    status: str
    course_id: str | None = None


class RecordDeleteSnapshot(BaseModel):
    """record.soft_delete 执行前快照：updated_at 双保险＋记录级资产计数——
    预览后资产新增（如知识点确认）属实质差异，重验失效重新授权。"""

    model_config = ConfigDict(extra="forbid")

    updated_at: datetime
    title: str
    status: str
    course_id: str | None = None
    knowledge_point_count: int
    quiz_count: int
    todo_count: int
    review_material_count: int
    has_summary: bool


class CourseDeleteSnapshotRecord(BaseModel):
    """课程删除影响清单条目（id+标题，确认卡呈现记录清单）。"""

    model_config = ConfigDict(extra="forbid")

    record_id: str
    title: str


class CourseDeleteSnapshot(BaseModel):
    """course.soft_delete 执行前快照：级联影响清单＝当前记录清单（id 排序保证
    序列化稳定），批准后新增记录 → 清单差异 → 失效重新预览（Q8 场景）。"""

    model_config = ConfigDict(extra="forbid")

    updated_at: datetime
    name: str
    status: str
    records: list[CourseDeleteSnapshotRecord]
    record_count: int


class RecordSoftDeletePayload(BaseModel):
    """OP_RECORD_SOFT_DELETE 提案判别载荷（L3：任何档位逐项确认）。"""

    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(
        pattern=_UUID_PATTERN,
        description="目标学习记录 id（经 search_library 查找消歧后取得）",
    )


class RecordSoftDeleteResult(BaseModel):
    """OP_RECORD_SOFT_DELETE 结果投影：被删记录 id 与标题（回执卡）。"""

    record_id: str
    title: str


class CourseSoftDeletePayload(BaseModel):
    """OP_COURSE_SOFT_DELETE 提案判别载荷（L3：任何档位逐项确认）。"""

    model_config = ConfigDict(extra="forbid")

    course_id: str = Field(
        pattern=_UUID_PATTERN,
        description="目标课程 id（经 search_courses 查找消歧后取得）",
    )


class CourseSoftDeleteResult(BaseModel):
    """OP_COURSE_SOFT_DELETE 结果投影：课程 id 与被级联删除的记录数。"""

    course_id: str
    record_count: int


class RecordMoveCoursePayload(BaseModel):
    """OP_RECORD_MOVE_COURSE 提案判别载荷（L2）。"""

    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(
        pattern=_UUID_PATTERN,
        description="要迁移的学习记录 id（经 search_library 查找消歧后取得）",
    )
    target_course_id: str = Field(
        pattern=_UUID_PATTERN,
        description="目标课程 id（经 search_courses 查找消歧后取得）",
    )


class RecordMoveCourseResult(BaseModel):
    """OP_RECORD_MOVE_COURSE 结果投影：before/after 课程对照（回执卡）。"""

    record_id: str
    before_course_id: str | None = None
    after_course_id: str | None = None
    # 执行后版本戳（undo 前重验版本用，同 CourseUpdateResult）。
    after_updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# 学习目标契约（通用 Agent 第三阶段工单 01，spec 用户故事 1~6）：目标挂单个
# 知识空间，AI 推断的目标范围经确认卡确认后生效（scope_source=AI_INFERRED +
# scope_confirmed=True 由应用器固化——确认卡即用户确认，spec 用户故事 6）。
# ---------------------------------------------------------------------------


class GoalCreatePayload(BaseModel):
    """OP_GOAL_CREATE 提案判别载荷（L1）：目标课程 + 目标参数。

    course_id / goal_type / title 必填（缺失 → 结构化缺失项由模型转述追问，
    同 create_course 口径）；期限与每日投入可选（模型按指引先追问，用户明确
    表示没有时可不传）。日期为 YYYY-MM-DD。
    """

    model_config = ConfigDict(extra="forbid")

    course_id: str = Field(
        pattern=_UUID_PATTERN,
        description="目标知识空间 id（经 search_courses 查找消歧后取得）",
    )
    goal_type: GoalType = Field(description="目标类型")
    title: str = Field(min_length=1, max_length=200, description="目标标题")
    target_date: date | None = Field(
        default=None, description="期限（YYYY-MM-DD，按日）；用户明确表示无期限时不传"
    )
    daily_minutes: int | None = Field(
        default=None, gt=0, le=24 * 60, description="计划每日投入分钟数"
    )
    target_score: float | None = Field(default=None, ge=0, le=100, description="目标分数（可选）")

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        return clean_goal_title(value)


class GoalCreateResult(BaseModel):
    """OP_GOAL_CREATE 结果投影（操作回执）：目标 id + 课程入口（course_id）。"""

    goal_id: str
    course_id: str


class GoalCreateStateSnapshot(BaseModel):
    """goal.create 执行前快照：课程身份＋版本戳（确认前课程被改 → 失效重确认）。

    单 ACTIVE 冲突（提交时已存在进行中目标）在快照读取器直接拒绝（零提案，
    模型即时转述「先完成或归档旧目标」）——创建类动作携带快照的原因正是
    这个状态依赖：课程创建等无状态创建动作沿用恒缺省。
    """

    model_config = ConfigDict(extra="forbid")

    updated_at: datetime
    name: str


class GoalStateSnapshot(BaseModel):
    """goal.update 执行前快照（spec 决策 12 同口径）：updated_at 双保险＋
    before 值（确认卡预览 / 执行前重验 / 后续 Undo 补偿数据三用）。"""

    model_config = ConfigDict(extra="forbid")

    updated_at: datetime
    title: str
    goal_type: GoalType
    status: str
    target_date: date | None = None
    daily_minutes: int | None = None
    target_score: float | None = None


class GoalUpdatePayload(BaseModel):
    """OP_GOAL_UPDATE 提案判别载荷（L1）：编辑字段或状态流转（完成 / 归档）。

    工具面滤 None（模型无法传显式 null）：非 None 字段＝本次要修改的字段；
    status 仅接受 COMPLETED / ARCHIVED（终态单向流转）。编辑与状态流转均
    只对 ACTIVE 目标开放（领域核心校验）。
    """

    model_config = ConfigDict(extra="forbid")

    goal_id: str = Field(
        pattern=_UUID_PATTERN,
        description="目标学习目标 id（经 list_goals 查找取得）",
    )
    title: str | None = Field(default=None, min_length=1, max_length=200, description="目标标题")
    target_date: date | None = Field(default=None, description="期限（YYYY-MM-DD，按日）")
    daily_minutes: int | None = Field(
        default=None, gt=0, le=24 * 60, description="计划每日投入分钟数"
    )
    target_score: float | None = Field(default=None, ge=0, le=100, description="目标分数（可选）")
    status: Literal["COMPLETED", "ARCHIVED"] | None = Field(
        default=None, description="状态流转：COMPLETED 完成 / ARCHIVED 归档（终态单向）"
    )

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str | None) -> str | None:
        return clean_goal_title(value) if value is not None else None

    @model_validator(mode="after")
    def _require_change(self) -> "GoalUpdatePayload":
        provided = self.model_dump(exclude_unset=True)
        if set(provided) <= {"goal_id"}:
            raise ValueError("至少提供一个修改字段或状态")
        return self


class GoalUpdateResult(BaseModel):
    """OP_GOAL_UPDATE 结果投影：被修改字段的 before / after 对照（回执卡）。"""

    goal_id: str
    before: dict[str, Any]
    after: dict[str, Any]
    after_status: str = Field(description="执行后目标状态（完成 / 归档流转的回执事实）")
    # 执行后版本戳（undo 前重验版本用，同 CourseUpdateResult）。
    after_updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# 学习计划确认契约（通用 Agent 第三阶段工单 02，spec 用户故事 7~11）：草案由
# generate_learning_plan 生成（只读零落库）→ 模型经 confirm_plan 原样提交 →
# OP_PLAN_CONFIRM 提案卡（只读草案预览）→ 用户确认落库为 ACTIVE 版本。载荷即
# 草案全文——确认卡所见（payload 预览）与落库所写（applier 消费同一载荷）一致。
# ---------------------------------------------------------------------------


class PlanConfirmPayload(PlanConfirmCore):
    """OP_PLAN_CONFIRM 提案判别载荷（L2：计划头 + 批量计划项创建）。

    phases / scheduled_date 形状由领域 schema 执法；排期与目标的期限 / 预算
    一致性在快照读取器重算比对（模型转述漂移 → 结构化拒绝零提案）。
    """


class PlanConfirmResult(BaseModel):
    """OP_PLAN_CONFIRM 结果投影（操作回执）：计划 id / 版本 / 规模 / 排期区间。"""

    plan_id: str
    goal_id: str
    course_id: str
    plan_version: int
    item_count: int
    first_date: date | None = Field(default=None, description="排期首日")
    last_date: date | None = Field(default=None, description="排期末日")


class PlanConfirmStateSnapshot(BaseModel):
    """plan.confirm 执行前快照：目标身份 + 排期约束字段（确认前目标被改 →
    快照比对失效重新生成草案：期限 / 每日投入变化会让既排日期失真）。"""

    model_config = ConfigDict(extra="forbid")

    updated_at: datetime
    title: str
    target_date: date | None = None
    daily_minutes: int | None = None
    course_name: str


# ---------------------------------------------------------------------------
# 计划执行与调整契约（通用 Agent 第三阶段工单 03，spec 用户故事 12~17）：
# 项级编辑 / 完成（L1 就地写当前版本）与重生成（L2 换代：新版本 + SUPERSEDED
# + user_locked 原样保留）。完成不产 learning_event、不动 Concept Mastery。
# ---------------------------------------------------------------------------


class PlanItemUpdatePayload(PlanItemUpdate):
    """OP_PLAN_ITEM_UPDATE 提案判别载荷（L1）：领域编辑契约 + item_id 定位。

    字段、约束与清洗全量继承领域 PlanItemUpdate（含「至少一个修改字段」
    验证器），与页面 PATCH 路径同一契约；用户经 Agent 的编辑与页面直改
    同置 user_locked。工具面滤 None（模型无法传显式 null）。"""

    item_id: str = Field(
        pattern=_UUID_PATTERN,
        description="目标计划项 id（get_plan 取得）",
    )

    @model_validator(mode="after")
    def _require_change_field(self) -> "PlanItemUpdatePayload":
        # 父类验证器不知 item_id：仅传定位键（无实际修改字段）在此拒绝。
        if set(self.model_dump(exclude_unset=True)) <= {"item_id"}:
            raise ValueError("至少提供一个修改字段")
        return self


class PlanItemStateSnapshot(BaseModel):
    """plan_item.update / complete 执行前快照：计划项当前态 + 所在版本与目标
    状态（确认前项被并发修改或版本被换代 → 快照比对失效重新确认）。"""

    model_config = ConfigDict(extra="forbid")

    item_id: str
    plan_id: str
    plan_version: int
    plan_status: str
    goal_status: str
    phase_title: str
    content: str
    scheduled_date: date
    estimated_minutes: int | None = None
    status: str
    user_locked: bool


class PlanItemUpdateResult(BaseModel):
    """OP_PLAN_ITEM_UPDATE 结果投影：修改字段 before / after + 锁定事实。"""

    item_id: str
    plan_id: str
    goal_id: str
    before: dict[str, Any]
    after: dict[str, Any]
    user_locked: bool = Field(description="手动编辑后置位（重生成原样保留）")


class PlanItemCompletePayload(BaseModel):
    """OP_PLAN_ITEM_COMPLETE 提案判别载荷（L1）：勾选完成。"""

    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(
        pattern=_UUID_PATTERN,
        description="要完成的计划项 id（get_plan 取得）",
    )


class PlanItemCompleteResult(BaseModel):
    """OP_PLAN_ITEM_COMPLETE 结果投影：完成事实与完成时间戳。"""

    item_id: str
    plan_id: str
    goal_id: str
    status: str = Field(description="执行后项状态（DONE）")
    completed_at: datetime | None = Field(
        default=None, description="完成时间戳（学习时长统计口径，不进学习证据链）"
    )


class PlanRegeneratePayload(PlanRegenerateCore):
    """OP_PLAN_REGENERATE 提案判别载荷（L2 换代）。

    载荷由 regenerate_plan 工具确定性构造（锁定项从旧版本行原样复制 + LLM
    草案经排期器铺排），不经模型转述——确认卡所见与落库所写是同一份。
    """


class PlanLockedItemStamp(BaseModel):
    """锁定项版本戳（重生成快照）：计划头身份不随项级写入变化，项级编辑 /
    完成 / 跳过均只维护 item.updated_at——锁定集或其内容在载荷派生后变化，
    凭戳使快照比对可感。"""

    model_config = ConfigDict(extra="forbid")

    item_id: str
    updated_at: datetime


class PlanRegenerateStateSnapshot(BaseModel):
    """plan.regenerate 执行前快照：目标约束字段 + 当前 ACTIVE 计划身份 + 锁定项
    版本戳（载荷派生后目标被改、版本被并发处理或锁定项变化 → 比对失效重新
    生成）。"""

    model_config = ConfigDict(extra="forbid")

    updated_at: datetime
    title: str
    target_date: date | None = None
    daily_minutes: int | None = None
    course_name: str
    active_plan_version: int
    active_plan_updated_at: datetime
    locked_items: list[PlanLockedItemStamp]


class PlanRegenerateResult(BaseModel):
    """OP_PLAN_REGENERATE 结果投影：新版本身份 + 换代事实 + 保留项计数。"""

    plan_id: str
    goal_id: str
    course_id: str
    plan_version: int
    superseded_version: int | None = Field(
        default=None, description="被换代的旧版本号（此前无生效计划则为 None）"
    )
    item_count: int
    locked_count: int = Field(description="原样带入的用户锁定项数")
    first_date: date | None = Field(default=None, description="新版本排期首日")
    last_date: date | None = Field(default=None, description="新版本排期末日")


# ---------------------------------------------------------------------------
# 共享来源引用动作契约（通用 Agent 第三阶段工单 05）：course ↔ library_item
# 多对多；add / remove 为 L1 写动作（确认卡 + 三档授权），引用增删不触原资料。
# ---------------------------------------------------------------------------


class SharedRefPayload(BaseModel):
    """OP_SHARED_REF_ADD / OP_SHARED_REF_REMOVE 提案判别载荷。"""

    model_config = ConfigDict(extra="forbid")

    course_id: str = Field(
        pattern=_UUID_PATTERN,
        description="引用落点课程 id（经 search_courses 查找消歧后取得）",
    )
    library_item_id: str = Field(
        pattern=_UUID_PATTERN,
        description="被引用的资料条目 id（可先用 list_library_items / search_library 查找）",
    )


class SharedRefResult(BaseModel):
    """OP_SHARED_REF_ADD / OP_SHARED_REF_REMOVE 结果投影（回执卡）。"""

    course_id: str
    library_item_id: str
    title: str = Field(description="被引用资料条目标题（执行时快照）")


class SharedRefAddStateSnapshot(BaseModel):
    """shared_ref.add 执行前快照：课程与条目双目标态（确认窗口内任一方变化
    → OPERATION_SNAPSHOT_STALE 重新确认）。"""

    model_config = ConfigDict(extra="forbid")

    course_updated_at: datetime
    course_name: str
    item_title: str
    item_owner_course_id: str | None = Field(
        default=None, description="条目归属课程 id（未归档归属 None）"
    )


class SharedRefRemoveStateSnapshot(BaseModel):
    """shared_ref.remove 执行前快照：引用行 id（对象版本绑定——确认窗口内
    引用被删重建则行身份变化 → OPERATION_SNAPSHOT_STALE，旧批准不得删除
    新引用行，ADR-0026）＋课程名与条目标题（确认卡核对移除哪条关系——同一
    资料可被多空间引用；课程改名 → 快照比对失效重新确认，与 add 同口径）。"""

    model_config = ConfigDict(extra="forbid")

    ref_id: str
    course_name: str
    item_title: str


class LibraryItemIngestPayload(BaseModel):
    """ingest_library_item 提案判别载荷（第三阶段工单 06）：URL 导入资料库。

    计划内步骤动作（07 多资料 Run 的地基）：course_id 可为空或引用注入后的
    实际值（引用解析在推进 worker，payload 层只见终值）；url 校验复用
    create_web_ingest_rows 的统一入库口径。"""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, description="要导入的网页地址（http/https 公网地址）")
    title: str | None = Field(default=None, description="展示标题（缺省用域名）")
    course_id: str | None = Field(
        default=None, description="归类课程 id（可为空＝未归类；可经计划引用注入）"
    )


class LibraryItemIngestResult(BaseModel):
    """ingest_library_item 结果投影（工单 06）：导入即入库（Record + 条目 +
    WEB_FETCH 任务同事务），真实抓取由 web_fetch_worker 异步完成——
    awaited_job_id 是 Run 等待转移的核对对象（spec M2 执行闭环）。
    重试幂等（工单 07）：同 URL 条目已在库（上次执行建的、抓取失败）时复用
    既有行、不再提交新 job——条目处置走资料库既有重试 / 手动粘贴通道，
    此时 awaited_job_id 为 None（步骤直接成功，不进等待）。"""

    model_config = ConfigDict(extra="forbid")

    library_item_id: str
    record_id: str
    awaited_job_id: str | None = Field(
        default=None, description="等待的后台抓取任务 id（WEB_FETCH）；复用既有条目时为空"
    )


class LocalDocumentIngestPayload(BaseModel):
    """ingest_local_document 提案判别载荷（第三阶段工单 07）：本地文档导入。

    计划内步骤动作（多资料 Run 的本地文档来源）：path 是用户在对话中明确
    提供的本地文件绝对路径（模型不得猜测路径，缺失先追问）；扩展名白名单
    与空文件检查由 document import 核心执法。course_id 可经计划引用注入。"""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, description="本地文档绝对路径（TXT / MD / PDF / DOCX）")
    title: str | None = Field(default=None, description="展示标题（缺省用文件名去扩展名）")
    course_id: str | None = Field(
        default=None, description="归类课程 id（可为空＝未归类；可经计划引用注入）"
    )


class LocalDocumentIngestResult(BaseModel):
    """ingest_local_document 结果投影（工单 07）：文件落库（Record + 文件行 +
    DOCUMENT_PARSE 任务同事务），解析由既有 worker 异步完成——awaited_job_id
    是 Run 等待转移的核对对象；重试幂等复用既有导入（同课程同内容指纹）时，
    解析已完成则为空、上次失败则新投一个解析任务。"""

    model_config = ConfigDict(extra="forbid")

    record_id: str
    file_id: str
    awaited_job_id: str | None = Field(
        default=None, description="等待的后台解析任务 id（DOCUMENT_PARSE）；无可等待任务时为空"
    )


class PlanDraftGeneratePayload(BaseModel):
    """generate_plan_draft 提案判别载荷（第三阶段工单 07）：Run 末步产计划草案卡。

    计划内步骤动作（多资料 Run 的「计划生成意图」）：goal_id 是既有目标 id 或
    经计划引用注入的建目标步骤输出；应用器提交 PLAN_DRAFT 后台任务（LLM 草案
    生成），任务完成时落 OP_PLAN_CONFIRM 草案确认卡——草案确认是 Run 之外的
    人工闸门（spec M2：不算 Run 步骤）。"""

    model_config = ConfigDict(extra="forbid")

    goal_id: str = Field(
        pattern=_UUID_PATTERN,
        description="学习目标 id（既有目标，或指向建目标步骤输出的引用注入值）",
    )


class PlanDraftGenerateResult(BaseModel):
    """generate_plan_draft 结果投影（工单 07）：提交 PLAN_DRAFT 任务即成功，
    草案确认卡由任务完成时落库（提案 id 在任务 result，不回填本回执）。"""

    model_config = ConfigDict(extra="forbid")

    awaited_job_id: str = Field(description="等待的后台草案生成任务 id（PLAN_DRAFT）")
