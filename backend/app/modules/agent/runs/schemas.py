"""执行事实查询与清理契约（spec 决策 2/3/21/22）。

枚举值与迁移 0030 的 CHECK 逐一对应；终态集合供清理守卫与查询过滤复用。
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


def _iso_utc(value: datetime) -> str:
    utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _iso_utc_opt(value: datetime | None) -> str | None:
    return None if value is None else _iso_utc(value)


class AuthMode(StrEnum):
    """授权档位（ADR-0026；档位执行分流随 02 票落地，本票为授权事实的记录词汇）。"""

    REQUEST_APPROVAL = "REQUEST_APPROVAL"
    AUTO_APPROVE = "AUTO_APPROVE"
    FULL_ACCESS = "FULL_ACCESS"


class RunStatus(StrEnum):
    RUNNING = "RUNNING"
    WAITING_USER = "WAITING_USER"
    WAITING_JOB = "WAITING_JOB"  # 第三阶段预留，本阶段无写入者
    COMPLETED = "COMPLETED"
    PARTIAL_COMPLETED = "PARTIAL_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class OperationStatus(StrEnum):
    PLANNED = "PLANNED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class ActivityType(StrEnum):
    AUTH_MODE_SWITCH = "AUTH_MODE_SWITCH"


class ActivityScope(StrEnum):
    GLOBAL = "GLOBAL"
    SESSION = "SESSION"


# 终态集合（清理守卫：仅终态可清理；提案审批事实永不删，spec 决策 21）。
RUN_TERMINAL_STATUSES = (
    RunStatus.COMPLETED,
    RunStatus.PARTIAL_COMPLETED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
)
OPERATION_TERMINAL_STATUSES = (
    OperationStatus.SUCCEEDED,
    OperationStatus.FAILED,
    OperationStatus.SKIPPED,
    OperationStatus.CANCELLED,
)


class OperationAuthorization(BaseModel):
    """operation.authorization_json 的形状（ADR-0026 授权依据）。

    确认路径：档位恒 REQUEST_APPROVAL、trigger=USER_CONFIRMED_PROPOSAL、
    指令摘录为空（提案框架未携带触发指令原文）；直执行（工单 02）沿同列
    回填 trigger=AUTO_EXECUTED、当轮档位与触发指令摘录。单步无 run 时
    本列是授权事实的唯一载体。
    """

    model_config = ConfigDict(extra="forbid")

    auth_mode: AuthMode = AuthMode.REQUEST_APPROVAL
    trigger: Literal["USER_CONFIRMED_PROPOSAL", "AUTO_EXECUTED"] = "USER_CONFIRMED_PROPOSAL"
    instruction_excerpt: str | None = None
    session_id: str | None = None
    message_id: str | None = None


class AgentOperationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str | None
    proposal_id: str | None
    action: str
    level: str
    target_type: str | None
    target_id: str | None
    payload: dict[str, Any] = {}
    snapshot: dict[str, Any] | None = None
    authorization: dict[str, Any] | None = None
    status: str
    attempts: int
    result: dict[str, Any] | None = None
    error_code: str | None
    undo_of: str | None
    undone_by: str | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None

    @field_serializer("created_at", "updated_at")
    def _ser(self, value: datetime) -> str:
        return _iso_utc(value)

    @field_serializer("finished_at")
    def _ser_opt(self, value: datetime | None) -> str | None:
        return _iso_utc_opt(value)


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str | None
    auth_mode: AuthMode
    instruction_text: str | None
    proposal_id: str | None
    status: str
    plan: dict[str, Any] | None = None
    plan_version: int
    waiting_reason: str | None
    cancel_requested: bool
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None

    @field_serializer("created_at", "updated_at")
    def _ser(self, value: datetime) -> str:
        return _iso_utc(value)

    @field_serializer("finished_at")
    def _ser_opt(self, value: datetime | None) -> str | None:
        return _iso_utc_opt(value)


class AgentRunDetailOut(AgentRunOut):
    operations: list[AgentOperationOut] = []


class AgentActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    activity_type: ActivityType
    from_mode: AuthMode
    to_mode: AuthMode
    scope: ActivityScope
    session_id: str | None
    created_at: datetime

    @field_serializer("created_at")
    def _ser(self, value: datetime) -> str:
        return _iso_utc(value)


class RunListQuery(BaseModel):
    status: RunStatus | None = None
    session_id: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class OperationListQuery(BaseModel):
    status: OperationStatus | None = None
    session_id: str | None = Field(
        default=None, description="按触发会话过滤（授权依据列 JSON 投影）"
    )
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ActivityListQuery(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class PurgeResultOut(BaseModel):
    runs_deleted: int
    operations_deleted: int


# ---------------------------------------------------------------------------
# 授权档位 API 契约（工单 02：设置页全局默认档 + 会话切换审计）


class AgentAuthModeOut(BaseModel):
    """当前全局默认授权档（settings.json 偏离项，缺省 REQUEST_APPROVAL）。"""

    model_config = ConfigDict(extra="forbid")

    auth_mode: AuthMode


class AgentAuthModeSwitch(BaseModel):
    """全局默认档切换请求：只声明目标档，from 由后端自读 settings.json
    （审计链权威口径——客户端缓存过期时不上报失真的 from）。"""

    model_config = ConfigDict(extra="forbid")

    to_mode: AuthMode


class AgentAuthModeSessionSwitch(BaseModel):
    """会话内临时切档的审计行（会话档位本身是前端按会话内存，不落库）。
    from 由客户端上报：会话生效档（覆盖 ?? 全局默认）在后端无从得知。"""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=36)
    from_mode: AuthMode
    to_mode: AuthMode
