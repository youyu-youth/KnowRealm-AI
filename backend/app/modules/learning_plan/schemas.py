"""学习计划域 API Schema：学习目标（工单 01）。

时间序列化统一 UTC ``Z``；target_date 是按日的期限（YYYY-MM-DD，无时段）。
"""

from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)


def _serialize_utc(value: datetime) -> str:
    utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def clean_goal_title(value: str) -> str:
    """目标标题清洗（领域 schema 与 Agent 载荷 schema 共用）：去首尾空白、
    空白即拒；可选字段由调用方先判 None。"""
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("目标标题不能为空白")
    return cleaned


class GoalType(StrEnum):
    SKILL = "SKILL"
    EXAM = "EXAM"
    PROJECT = "PROJECT"
    READING = "READING"
    CUSTOM = "CUSTOM"


class GoalScopeSource(StrEnum):
    """目标范围来源（spec 决策：AI_INFERRED 必须用户确认才生效）。"""

    USER_CONFIRMED = "USER_CONFIRMED"
    COURSE_SELECTION = "COURSE_SELECTION"
    AI_INFERRED = "AI_INFERRED"


class GoalStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class GoalCreate(BaseModel):
    """HTTP 创建契约：页面 / Agent 应用器共用领域核心，本 schema 是页面入口。

    页面创建恒为用户确认范围（scope_source=USER_CONFIRMED）；Agent 路径的
    AI_INFERRED + 确认卡语义由应用器经领域核心参数传入，不走本 schema。
    """

    model_config = ConfigDict(extra="forbid")

    goal_type: GoalType = Field(description="目标类型")
    title: str = Field(min_length=1, max_length=200, description="目标标题")
    target_date: date | None = Field(default=None, description="期限（按日）")
    daily_minutes: int | None = Field(
        default=None, gt=0, le=24 * 60, description="计划每日投入分钟数"
    )
    target_score: float | None = Field(
        default=None, ge=0, le=100, description="目标分数（如考试目标分，可选）"
    )

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        return clean_goal_title(value)


class GoalUpdate(BaseModel):
    """目标编辑契约（期限 / 每日投入 / 标题 / 目标分数）：仅 ACTIVE 目标可改。"""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200, description="目标标题")
    target_date: date | None = Field(default=None, description="期限（按日）")
    daily_minutes: int | None = Field(
        default=None, gt=0, le=24 * 60, description="计划每日投入分钟数"
    )
    target_score: float | None = Field(default=None, ge=0, le=100, description="目标分数（可选）")

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str | None) -> str | None:
        return clean_goal_title(value) if value is not None else None


class GoalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str
    goal_type: GoalType
    title: str
    target_date: date | None = Field(default=None, description="期限（按日）")
    daily_minutes: int | None = Field(default=None, description="计划每日投入分钟数")
    target_score: float | None = Field(default=None, description="目标分数（可选）")
    scope_source: GoalScopeSource
    scope_confirmed: bool
    status: GoalStatus
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_utc(self, value: datetime) -> str:
        return _serialize_utc(value)


class GoalCreateCore(BaseModel):
    """领域核心创建参数（HTTP 与 Agent 应用器共用）：scope 语义显式传入。

    Agent 路径传 scope_source=AI_INFERRED + scope_confirmed=True（确认卡即
    用户确认）；AI_INFERRED 未确认由领域核心拒绝（不变量，spec 用户故事 6）。
    """

    model_config = ConfigDict(extra="forbid")

    goal_type: GoalType
    title: str
    target_date: date | None = None
    daily_minutes: int | None = Field(default=None, gt=0, le=24 * 60)
    target_score: float | None = Field(default=None, ge=0, le=100)
    scope_source: GoalScopeSource = GoalScopeSource.USER_CONFIRMED
    scope_confirmed: bool = True

    @model_validator(mode="after")
    def _require_confirmed_scope(self) -> "GoalCreateCore":
        if self.scope_source == GoalScopeSource.AI_INFERRED and not self.scope_confirmed:
            raise ValueError("AI 推断的目标范围必须经用户确认")
        return self
