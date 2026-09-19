"""library 域 Pydantic 契约：条目列表/详情/内容、联邦记录与资产行、提案框架载荷。

列表搜索 q 是导航级查询（标题/来源/元数据 LIKE），不是 RAG 检索；
RAG 检索经工单 04 的 LibraryRetrievalService，不开公开查询端点。
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.modules.capture.schemas import CaptureType
from app.modules.record.schemas import RecordStatus


class LibrarySourceType(StrEnum):
    AUDIO = "AUDIO"
    DOCUMENT = "DOCUMENT"
    WEB = "WEB"
    BOOK = "BOOK"
    TEXT = "TEXT"


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
    availability: LibraryAvailability = LibraryAvailability.EMPTY

    @field_serializer("created_at", "updated_at")
    def _ser(self, value: datetime) -> str:
        return _utc(value)

    @field_serializer("fetched_at")
    def _ser_opt(self, value: datetime | None) -> str | None:
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
    """02 仅开放收藏；重命名/归类/归档/删除随工单 05 生命周期端点。"""

    favorite: bool | None = None


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
    evidence_refs: Any | None = None
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
