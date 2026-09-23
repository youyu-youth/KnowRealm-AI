"""library 域 Pydantic 契约：条目列表/详情/内容、联邦记录与资产行、提案框架载荷。

列表搜索 q 是导航级查询（标题/来源/元数据 LIKE），不是 RAG 检索；
RAG 检索经工单 04 的 LibraryRetrievalService，不开公开查询端点。
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
    field_validator,
    model_validator,
)

from app.modules.capture.schemas import CaptureType
from app.modules.jobs.schemas import ProcessingJobOut
from app.modules.record.schemas import RecordStatus


class LibrarySourceType(StrEnum):
    AUDIO = "AUDIO"
    DOCUMENT = "DOCUMENT"
    WEB = "WEB"
    BOOK = "BOOK"
    TEXT = "TEXT"


class ChatScope(StrEnum):
    """会话挂载范围（工单 04 起五档，ADR-0024）：FREE 自由 / RECORD 单记录 /
    LIBRARY_ITEM 单资料 / COURSE 课程 / ALL 全部资料。

    chat 与 library 两域的共享契约（LIBRARY_ITEM/COURSE/ALL 的检索边界由
    LibraryRetrievalService 解释），故落 library 域定义、agent 域 re-export
    消费（法定方向 agent→library，避免模块环）。与 mode 轴正交（mode 恒 ASK）；
    范围会话内不可变；LIBRARY_ITEM 仅由资料详情「AI 解读」入口创建、不进
    全局范围切换。
    """

    FREE = "FREE"
    RECORD = "RECORD"
    LIBRARY_ITEM = "LIBRARY_ITEM"
    COURSE = "COURSE"
    ALL = "ALL"


class LibraryAvailability(StrEnum):
    """派生可用性（02 口径，04 检索服务落地后复核）：

    PROCESSING=关联记录有未终态的解析/转写/ASR 任务；FAILED=解析链终态失败且
    无分片；RETRIEVABLE=有关联分片（TEXT 条目转写正文亦可经子串兜底检索）；
    EMPTY=尚无可检索内容。
    """

    PROCESSING = "PROCESSING"
    RETRIEVABLE = "RETRIEVABLE"
    FAILED = "FAILED"
    EMPTY = "EMPTY"


class LibrarySmartView(StrEnum):
    ALL = "all"
    RECENT = "recent"
    FAVORITES = "favorites"
    NEEDS_REVIEW = "needs_review"
    ARCHIVED = "archived"
    TRASH = "trash"


def _utc(value: datetime) -> str:
    utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _utc_opt(value: datetime | None) -> str | None:
    return None if value is None else _utc(value)


class LibraryItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str | None
    course_name: str | None = None
    source_type: LibrarySourceType
    title: str
    origin_uri: str | None
    local_path: str | None
    mime_type: str | None
    file_size: int | None
    content_hash: str
    fetched_at: datetime | None
    source_metadata: dict[str, Any] = {}
    schema_version: int
    favorite: bool
    status: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    availability: LibraryAvailability = LibraryAvailability.EMPTY

    @field_serializer("created_at", "updated_at")
    def _ser(self, value: datetime) -> str:
        return _utc(value)

    @field_serializer("fetched_at")
    def _ser_opt(self, value: datetime | None) -> str | None:
        return _utc_opt(value)

    @field_serializer("deleted_at")
    def _ser_deleted(self, value: datetime | None) -> str | None:
        return _utc_opt(value)


class BackfillStatusOut(BaseModel):
    """回填任务摘要：仅存在任务行时随列表返回，供工作台横幅展示进度。"""

    model_config = ConfigDict(from_attributes=True)

    status: str
    progress: float
    error_code: str | None = None


class LibraryItemListOut(BaseModel):
    items: list[LibraryItemOut]
    total: int
    backfill: BackfillStatusOut | None = None


class LibraryItemListQuery(BaseModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=500)
    view: LibrarySmartView = LibrarySmartView.ALL
    source_type: LibrarySourceType | None = None
    course_id: UUID | None = None
    unclassified: bool = False
    availability: LibraryAvailability | None = None
    q: str | None = None


class LibraryItemPatch(BaseModel):
    """05 生命周期：重命名（title）/ 归类（course_id，null=取消归类）/ 收藏。

    字段未提供与显式置 null 语义不同（course_id=null 是取消归类），
    路由层以 model_fields_set 判别。
    """

    title: str | None = None
    course_id: UUID | None = None
    favorite: bool | None = None


class LibraryIngestSource(StrEnum):
    WEB = "web"
    TEXT = "text"


class LibraryIngestRequest(BaseModel):
    """统一入库 JSON 请求（本地文件走 /ingest/file multipart）。

    origin_uri 仅供 TEXT 降级粘贴携带原页面 URL（网页抓取失败闭环），不作抓取目标。
    """

    source: LibraryIngestSource
    url: str | None = None
    title: str | None = None
    content: str | None = None
    origin_uri: str | None = None
    course_id: UUID | None = None
    allow_duplicate: bool = False


class LibraryIngestAccepted(BaseModel):
    """202 立即建条目：处理状态由列表/详情派生字段轮询（web/file 带 Job 摘要）。"""

    item: LibraryItemOut
    job: ProcessingJobOut | None = None


class DerivedRecordOut(BaseModel):
    record_id: str
    title: str
    status: RecordStatus
    capture_type: CaptureType
    role: str
    sequence_no: int


class LibraryItemDetailOut(LibraryItemOut):
    derived_records: list[DerivedRecordOut] = []
    segment_count: int = 0
    failed_error_code: str | None = None


class LibraryItemContentQuery(BaseModel):
    limit: int = Field(default=4000, ge=1, le=100_000)


class LibraryItemContentOut(BaseModel):
    content: str
    truncated: bool


class LibraryRecordOut(BaseModel):
    """「学习记录」联邦行：跨课程记录 + 反向条目计数（检查器回链资料来源）。"""

    id: str
    course_id: str | None
    course_name: str | None = None
    capture_type: CaptureType
    title: str
    status: RecordStatus
    duration_ms: int
    linked_item_count: int = 0
    library_item_ids: list[str] = []
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def _ser(self, value: datetime) -> str:
        return _utc(value)


class LibraryRecordListQuery(BaseModel):
    course_id: UUID | None = None
    unclassified: bool = False
    q: str | None = None


class LibraryAssetOut(BaseModel):
    """「学习资产」联邦行（02=已确认知识点；其余资产经 Record 检查器触达）。"""

    id: str
    record_id: str
    record_title: str | None = None
    course_id: str | None
    course_name: str | None = None
    name: str
    detail: str = ""
    importance: float
    generation_status: str
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def _ser(self, value: datetime) -> str:
        return _utc(value)


class LibraryAssetListQuery(BaseModel):
    course_id: UUID | None = None
    q: str | None = None


class ProposalStatus(StrEnum):
    PENDING = "PENDING"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class ProposalType(StrEnum):
    ORGANIZE = "ORGANIZE"
    MEMORY = "MEMORY"
    RESEARCH_INGEST = "RESEARCH_INGEST"
    COURSE_CREATE = "COURSE_CREATE"
    TEXT_RECORD_ADD = "TEXT_RECORD_ADD"
    # OP_ 命名空间（迁移 0030 CHECK 通配，类型执法在判别 schema 注册表）：
    # 工单 03 修改与归档动作，后续新动作按同前缀递增。
    OP_COURSE_UPDATE = "OP_COURSE_UPDATE"
    OP_COURSE_ARCHIVE = "OP_COURSE_ARCHIVE"
    OP_COURSE_RESTORE = "OP_COURSE_RESTORE"
    OP_LIBRARY_ITEM_UPDATE = "OP_LIBRARY_ITEM_UPDATE"
    OP_LIBRARY_ITEM_ARCHIVE = "OP_LIBRARY_ITEM_ARCHIVE"
    OP_LIBRARY_ITEM_RESTORE = "OP_LIBRARY_ITEM_RESTORE"


class AgentProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    proposal_type: ProposalType
    status: ProposalStatus
    session_id: str | None
    message_id: str | None
    target_type: str | None
    target_id: str | None
    payload: dict[str, Any] = {}
    # 执行前快照（工单 03，spec 决策 12）：确认卡 before/after 预览读取；
    # 旧提案（含存量 ORGANIZE / COURSE_CREATE / TEXT_RECORD_ADD）无快照＝None。
    snapshot: dict[str, Any] | None = None
    evidence_refs: Any | None = None
    # 操作回执（工单 02）：APPLIED 提案的类型化结果（课程创建 → {course_id}）。
    result: dict[str, Any] | None = None
    error_code: str | None
    created_at: datetime
    decided_at: datetime | None

    @field_serializer("created_at")
    def _ser(self, value: datetime) -> str:
        return _utc(value)

    @field_serializer("decided_at")
    def _ser_opt(self, value: datetime | None) -> str | None:
        return _utc_opt(value)


class ProposalListQuery(BaseModel):
    status: ProposalStatus | None = None
    proposal_type: ProposalType | None = None
    # 会话维度过滤（工单 02 review）：聊天操作提案卡按本会话全状态恢复回执。
    session_id: str | None = None


# ---------------------------------------------------------------------------
# AI 整理（工单 05）：确定性扫描结果 + LLM 建议 + 提案载荷判别


class OrganizeDuplicateGroup(BaseModel):
    """确定性重复组：未软删且同 content_hash 的条目（≥2 才成组）。"""

    content_hash: str
    items: list[LibraryItemOut]


class OrganizeScanOut(BaseModel):
    """确定性检测结果（零 LLM）：机械问题先暴露，AI 只处理语义建议。"""

    duplicates: list[OrganizeDuplicateGroup]
    failed_items: list[LibraryItemOut]
    unclassified: list[LibraryItemOut]


class OrganizeSuggestion(BaseModel):
    """LLM 单条建议：只允许建议标题与归类，且 item_id / course_id 须回表校验。"""

    item_id: str = Field(description="目标资料条目 id（必须来自输入清单）")
    title: str | None = Field(default=None, description="规范化后的标题；标题已规范时不输出该字段")
    course_id: str | None = Field(
        default=None, description="建议归入的课程 id（必须来自课程清单；都不合适则不输出）"
    )


class OrganizeSuggestionBatch(BaseModel):
    """LLM 结构化输出契约（call_organize_model 校验用）。"""

    suggestions: list[OrganizeSuggestion] = Field(
        description="只为需要整理的条目给出建议；已规范的条目不要输出"
    )


class OrganizeProposeOut(BaseModel):
    """LLM 建议落为 ORGANIZE 提案后的返回（每条建议一提案，逐项确认）。"""

    created: list[AgentProposalOut]
    skipped: list[str] = []


class OrganizePayload(BaseModel):
    """ORGANIZE 提案载荷判别：只接受条目 id 与两个可应用字段。"""

    item_id: str
    title: str | None = None
    course_id: str | None = None


class ResearchIngestPayload(BaseModel):
    """RESEARCH_INGEST 提案载荷：web_search 候选来源（确认后才真实抓取）。"""

    url: str
    title: str
    course_id: str | None = None


_MEMORY_ITEM_MAX_CHARS = 100
_MEMORY_ITEMS_MAX_COUNT = 5
# 观察偏好键/值限长：确定性推断维度的短标签，防自由文本情节记忆（ADR-0025）。
_MEMORY_ENTRY_MAX_CHARS = 100

MemoryItemText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=_MEMORY_ITEM_MAX_CHARS),
]
MemoryEntryText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=_MEMORY_ENTRY_MAX_CHARS),
]


class MemoryProposalPayload(BaseModel):
    """MEMORY 提案载荷判别（工单 06）：EXPLICIT=用户明确「记住」的偏好条目；
    OBSERVED=结构化学习证据推导的观察偏好（必须携带置信度与证据计数）。
    确认后由 learner 域应用器写入 learner_preferences，创建不改事实。"""

    kind: Literal["EXPLICIT", "OBSERVED"]
    items: list[MemoryItemText] = Field(default_factory=list)
    entries: dict[MemoryEntryText, MemoryEntryText] = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_count: int | None = Field(default=None, ge=0)

    @field_validator("items")
    @classmethod
    def _limit_items(cls, value: list[str]) -> list[str]:
        if len(value) > _MEMORY_ITEMS_MAX_COUNT:
            raise ValueError(f"一次最多记忆 {_MEMORY_ITEMS_MAX_COUNT} 条偏好")
        return value

    @model_validator(mode="after")
    def _check_kind_shape(self) -> "MemoryProposalPayload":
        if self.kind == "EXPLICIT" and not self.items:
            raise ValueError("EXPLICIT 提案至少携带一条偏好条目")
        if self.kind == "OBSERVED" and (
            not self.entries or self.confidence is None or self.evidence_count is None
        ):
            raise ValueError("OBSERVED 提案必须携带观察条目、置信度与证据计数")
        return self


class ProposalCreateRequest(BaseModel):
    """通用提案创建（05）：payload 按 proposal_type 判别校验后落库，不改事实。"""

    proposal_type: ProposalType
    payload: dict[str, Any]
    session_id: str | None = None
    message_id: str | None = None
    target_type: str | None = None
    target_id: str | None = None
