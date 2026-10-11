"""ChatTurn 公开契约：提交（幂等）、快照、事件、取消与继续（票 02）。"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.modules.agent.runs.schemas import AuthMode
from app.modules.agent.schemas import (
    ChatPageSnapshot,
    ChatResponseProcessOut,
    iso_utc,
)


class ChatTurnStatus(StrEnum):
    """轮次状态机（规格 §6）；WAITING_* 由后续票写入。"""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_USER = "WAITING_USER"
    WAITING_JOB = "WAITING_JOB"
    INTERRUPTED = "INTERRUPTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL_STATUSES

    @property
    def is_observer_terminal(self) -> bool:
        """观察侧终态（含 INTERRUPTED）：订阅在此收口；会话占用仍按 is_terminal。"""
        return self in _OBSERVER_TERMINAL_STATUSES


_TERMINAL_STATUSES = frozenset(
    {
        ChatTurnStatus.COMPLETED,
        ChatTurnStatus.FAILED,
        ChatTurnStatus.CANCELLED,
    }
)

# 观察侧终态：SSE 事件订阅在该口径收口（INTERRUPTED/WAITING_USER 仍占用会话，
# 须经显式 resume 继续或 cancel 停止释放）。
_OBSERVER_TERMINAL_STATUSES = frozenset(
    _TERMINAL_STATUSES | {ChatTurnStatus.INTERRUPTED, ChatTurnStatus.WAITING_USER}
)

# 过程展示投影的状态映射（ChatResponseProcessOut.status 值域）。
_PROCESS_STATUS_BY_TURN: dict[ChatTurnStatus, str] = {
    ChatTurnStatus.QUEUED: "RUNNING",
    ChatTurnStatus.RUNNING: "RUNNING",
    ChatTurnStatus.WAITING_USER: "RUNNING",
    ChatTurnStatus.WAITING_JOB: "RUNNING",
    ChatTurnStatus.INTERRUPTED: "INTERRUPTED",
    ChatTurnStatus.COMPLETED: "COMPLETED",
    ChatTurnStatus.FAILED: "FAILED",
    ChatTurnStatus.CANCELLED: "INTERRUPTED",
}


def process_status_for_turn(status: ChatTurnStatus | str) -> str:
    return _PROCESS_STATUS_BY_TURN.get(ChatTurnStatus(status), "RUNNING")


class ChatTurnEventType(StrEnum):
    """持久事件类型；公开过程只含可展示内容，不含模型私有思维链。"""

    TOKEN = "token"
    COMMENTARY = "commentary"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    CITATION = "citation"
    DONE = "done"
    # 模型节点重放的正文替换边界（票 02）：未完成 segment 被新 output_revision
    # 替换，旧片段保留在事件流中可查看。
    REVISION = "revision"


class ChatTurnWaitingKind(StrEnum):
    """WAITING_USER 等待原因类型（票 02，规格 §7/§11/§12）。"""

    # 原供应商身份不可用（未配置 / 凭据被清空）。
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    # 当前配置与原供应商身份 / 模型不一致（不静默换服务）。
    PROVIDER_CHANGED = "PROVIDER_CHANGED"
    # 外发同意已失效或未确认（密钥或地址变化使指纹失配，规格 §12——凭据
    # 不落盘，密钥变化只能经同意指纹检测）。
    OUTBOUND_CONSENT_REVOKED = "OUTBOUND_CONSENT_REVOKED"
    # 已注入记忆但记忆外发同意已收回。
    MEMORY_OUTBOUND_REVOKED = "MEMORY_OUTBOUND_REVOKED"
    # 原轮次允许联网但当前联网配置不可用。
    WEB_SEARCH_UNAVAILABLE = "WEB_SEARCH_UNAVAILABLE"
    # 图 / 工具集版本与原执行不兼容（保守等待，不盲目重放）。
    GRAPH_INCOMPATIBLE = "GRAPH_INCOMPATIBLE"
    # checkpoint 缺失且已有已提交副作用，安全边界无法确定。
    CHECKPOINT_MISSING = "CHECKPOINT_MISSING"

    @property
    def resumable(self) -> bool:
        """是否可经 resume（条件恢复后重验继续）；不可恢复类只能停止或新问。"""
        return self not in (
            ChatTurnWaitingKind.GRAPH_INCOMPATIBLE,
            ChatTurnWaitingKind.CHECKPOINT_MISSING,
        )


class ChatTurnWaitingReason(BaseModel):
    """等待原因载荷（chat_turns.waiting_reason JSON）。"""

    model_config = ConfigDict(extra="forbid")

    kind: ChatTurnWaitingKind
    detail: str | None = None


class ChatTurnResumeRequest(BaseModel):
    """继续执行（票 02）：类型化决定；继续按钮不等于批准业务提案或重新授权。"""

    model_config = ConfigDict(extra="forbid")

    decision_kind: Literal[Literal["RETRY_AFTER_FIX"]] = "RETRY_AFTER_FIX"


class ChatTurnSubmitRequest(BaseModel):
    """提交回答生成：request_id 由客户端一次提交生成并在网络重试中保留。"""

    model_config = ConfigDict(extra="forbid")

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
    request_id: str = Field(
        min_length=8, max_length=64, description="客户端稳定受理身份（一次提交一个）"
    )

    @field_validator("content")
    @classmethod
    def clean_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("消息内容不能为空白")
        return cleaned


class ChatTurnEventOut(BaseModel):
    """已提交事件（events 端点补发载荷）；payload 形状按 type 判别。"""

    model_config = ConfigDict(extra="forbid")

    seq: int = Field(ge=1)
    attempt: int = Field(ge=0)
    output_revision: int = Field(ge=1)
    type: ChatTurnEventType
    segment_id: str | None = None
    tool_call_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict[str, Any])


class ChatTurnOut(BaseModel):
    """轮次快照：一致视图返回状态、正文投影与 last_seq（客户端从该序号补发）。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    session_id: str
    user_message_id: str
    final_message_id: str | None = None
    status: ChatTurnStatus
    cancel_requested: bool
    attempt: int = Field(ge=0)
    output_revision: int = Field(ge=1)
    last_seq: int = Field(ge=0)
    error_code: str | None = None
    error_message: str | None = None
    # WAITING_USER 等待原因（票 02）：null＝非等待态。
    waiting_reason: ChatTurnWaitingReason | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    # 当前已提交正文的权威投影（非评注 segment 按事件序拼接）；完成时与最终
    # assistant 行一致，前端完成渲染以 done 事件 / 最终消息为准。
    output_text: str = ""
    process: ChatResponseProcessOut | None = None

    @field_serializer("created_at", "updated_at")
    def serialize_time(self, value: datetime) -> str:
        return iso_utc(value)

    @field_serializer("started_at", "finished_at")
    def serialize_opt_time(self, value: datetime | None) -> str | None:
        return iso_utc(value) if value is not None else None


class ChatTurnsPage(BaseModel):
    """会话轮次列表（游标分页，before = 上一页最旧一条的 created_at/id）。"""

    model_config = ConfigDict(extra="forbid")

    turns: list[ChatTurnOut]
    next_before: tuple[datetime, str] | None = None


class ChatTurnCancelOut(BaseModel):
    """取消受理结果：cancel_requested 恒 True；状态可能仍 RUNNING（正在停止）。"""

    model_config = ConfigDict(extra="forbid")

    turn: ChatTurnOut


class ChatTurnResumeOut(BaseModel):
    """继续受理结果：重验恢复条件通过后重新排队（QUEUED）。"""

    model_config = ConfigDict(extra="forbid")

    turn: ChatTurnOut


__all__ = [
    "ChatTurnCancelOut",
    "ChatTurnEventOut",
    "ChatTurnEventType",
    "ChatTurnOut",
    "ChatTurnResumeOut",
    "ChatTurnResumeRequest",
    "ChatTurnStatus",
    "ChatTurnSubmitRequest",
    "ChatTurnWaitingKind",
    "ChatTurnWaitingReason",
    "ChatTurnsPage",
    "process_status_for_turn",
]
