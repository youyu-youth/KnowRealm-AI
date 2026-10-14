from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.agent.schemas import ChatPageSnapshot
from app.modules.agent.turns.schemas import ChatTurnStatus
from app.modules.settings.model_budget import ModelCapabilityOut


class ContextPolicy(BaseModel):
    version: Literal[1] = 1
    base_url: str
    model: str
    capability: ModelCapabilityOut


class InputEstimate(BaseModel):
    policy: ContextPolicy
    counting: Literal["APPROXIMATE"] = "APPROXIMATE"
    tokenizer: str = "utf8_bytes/2"
    input_tokens: int
    components: dict[str, int]
    output_reserve: int
    input_capacity: int
    safety_margin: int
    usable_budget: int
    remaining: int
    message_count: int
    tool_count: int
    input_fingerprint: str
    error_code: str | None = None


class ModelRequestStatus(StrEnum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class ModelRequestOut(BaseModel):
    id: str
    turn_id: str
    status: ModelRequestStatus
    context_version: int | None
    estimate: InputEstimate
    usage: dict[str, int] | None
    error_code: str | None
    created_at: datetime
    purpose: Literal["ANSWER", "SUMMARY"] = "ANSWER"


class SummaryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, description="摘要内容；约束和决定必须摘录用户原文")
    source_ids: list[str] = Field(min_length=1, description="程序提供的消息来源身份")


class ConversationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goals: list[SummaryItem] = Field(description="用户目标")
    constraints: list[SummaryItem] = Field(description="明确约束，逐字摘录")
    decisions: list[SummaryItem] = Field(description="已确认决定，逐字摘录")
    objects: list[SummaryItem] = Field(description="相关对象和来源")
    unfinished: list[SummaryItem] = Field(description="未完成事项")
    questions: list[SummaryItem] = Field(description="待澄清问题、冲突与推测")


class CompactionOut(BaseModel):
    id: str
    status: Literal["RUNNING", "WAITING", "FAILED", "COMPLETED", "CANCELLED"]
    completed_chunks: int
    total_chunks: int
    requests_used: int = Field(description="当前压缩批次的实际摘要请求次数")
    turn_requests_used: int = Field(description="所属轮次所有批次的累计实际摘要请求次数")
    allowance: int = Field(description="所属轮次的摘要请求总额度")
    covered_message_ids: list[str]
    summary: ConversationSummary | None
    error_code: str | None


class ContextViewOut(BaseModel):
    session_id: str
    version: int
    segment: int
    actual_turn_id: str | None
    actual: list[ModelRequestOut]
    next_estimate: InputEstimate | None
    next_error_code: str | None
    compactions: list[CompactionOut] = Field(default_factory=lambda: list[CompactionOut]())
    active_summary: CompactionOut | None = None
    pins: list[ContextPinOut] = Field(default_factory=lambda: list[ContextPinOut]())
    actual_pins: list[ContextPinOut] = Field(default_factory=lambda: list[ContextPinOut]())
    rules: ContextRules = Field(default_factory=lambda: ContextRules())
    actual_rules: ContextRules | None = None
    actual_segment: int | None = None


class ContextPreviewRequest(BaseModel):
    content: str = Field(default="", max_length=8000)
    web_search: bool = False
    page: ChatPageSnapshot | None = None


class ContextSourceOut(BaseModel):
    source_id: str
    kind: Literal["message", "output", "record", "library"]
    title: str
    version: str
    turn_id: str | None = None
    locator: dict[str, str | int | None] = Field(default_factory=dict)


class ContextSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(default="", max_length=200)
    cursor: str | None = Field(default=None, max_length=2000)
    limit: int = Field(default=8, ge=1, le=8)


class ContextSearchOut(BaseModel):
    sources: list[ContextSourceOut]
    next_cursor: str | None
    remaining: int


class ContextReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(min_length=1, max_length=200)
    version: str | None = Field(default=None, max_length=128)
    cursor: str | None = Field(default=None, max_length=2000)
    max_chars: int = Field(default=1600, ge=1, le=2400)
    quote: str | None = Field(default=None, max_length=80)
    offset: int | None = Field(default=None, ge=0)


class ContextReadOut(BaseModel):
    source: ContextSourceOut
    content: str
    offset: int
    next_cursor: str | None
    remaining: int


class ContextPin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    mode: Literal["TEXT", "SNIPPET", "OBJECT"]
    content: str = ""
    source_id: str | None = None
    source_version: str | None = None
    offset: int = 0
    title: str


class ContextPinOut(ContextPin):
    status: Literal["VALID", "STALE", "UNAVAILABLE", "EXCLUDED"] = "VALID"
    reason: str | None = None
    injected: bool = False


class ContextPinChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, description="查看上下文获得的预期设置版本")
    action: Literal["ADD", "UPDATE", "REMOVE"] = "ADD"
    pin_id: str | None = Field(default=None, max_length=36)
    mode: Literal["TEXT", "SNIPPET", "OBJECT"] | None = None
    content: str = Field(default="", max_length=8000)
    source_id: str | None = Field(default=None, max_length=200)
    source_version: str | None = Field(default=None, max_length=128)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_change(self) -> ContextPinChange:
        if self.action == "ADD" and self.pin_id:
            raise ValueError("ADD cannot replace an existing pin")
        if self.action in ("UPDATE", "REMOVE") and not self.pin_id:
            raise ValueError("pin_id is required")
        if self.action == "REMOVE":
            return self
        if self.mode is None:
            raise ValueError("mode is required")
        if self.mode == "TEXT":
            if not self.content.strip() or self.source_id is not None:
                raise ValueError("explicit text without source_id is required")
        elif not self.source_id or not self.source_version:
            raise ValueError("explicit source_id and source_version are required")
        elif self.mode == "SNIPPET" and not self.content.strip():
            raise ValueError("exact source text is required")
        elif self.mode == "OBJECT" and (
            not self.source_id.startswith(("record:", "library:")) or self.content
        ):
            raise ValueError("object must identify a material without copying its body")
        return self


class ContextPinPayload(ContextPinChange):
    session_id: str = Field(min_length=36, max_length=36)


class ContextPinsOut(BaseModel):
    session_id: str
    version: int
    pins: list[ContextPinOut]


class ContextRules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    excluded_turn_ids: list[str] = Field(default_factory=list[str])
    excluded_source_ids: list[str] = Field(default_factory=list[str])
    included_turn_ids: list[str] = Field(default_factory=list[str])


class ContextRuleChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1, description="当前会话设置版本")
    action: Literal[
        "EXCLUDE_TURN",
        "RESTORE_TURN",
        "EXCLUDE_SOURCE",
        "RESTORE_SOURCE",
        "RESET",
        "INCLUDE_HISTORY",
    ]
    turn_ids: list[Annotated[str, Field(min_length=36, max_length=43)]] = Field(
        default_factory=list[str], max_length=100, description="明确选择的轮次身份"
    )
    source_id: str | None = Field(
        default=None, max_length=200, description="record:或library:资料身份"
    )
    source_version: str | None = Field(
        default=None, max_length=128, description="选择资料时的来源版本"
    )

    @model_validator(mode="after")
    def validate_action(self) -> ContextRuleChange:
        if self.action in ("EXCLUDE_TURN", "RESTORE_TURN", "INCLUDE_HISTORY"):
            if not self.turn_ids or self.source_id or self.source_version:
                raise ValueError("explicit turn_ids without source are required")
        elif self.action in ("EXCLUDE_SOURCE", "RESTORE_SOURCE"):
            if (
                self.turn_ids
                or not self.source_id
                or not self.source_id.startswith(("record:", "library:"))
            ):
                raise ValueError("explicit material source_id is required")
            if self.action == "EXCLUDE_SOURCE" and not self.source_version:
                raise ValueError("source_version is required")
        elif self.turn_ids or self.source_id or self.source_version:
            raise ValueError("reset does not accept a range")
        if len(set(self.turn_ids)) != len(self.turn_ids):
            raise ValueError("duplicate turns")
        return self


class ContextRulePayload(ContextRuleChange):
    session_id: str = Field(min_length=36, max_length=36)


class ContextRulesOut(BaseModel):
    session_id: str
    version: int
    segment: int
    rules: ContextRules


class ContextHistoryTurnOut(BaseModel):
    turn_id: str
    segment: int
    status: ChatTurnStatus | Literal["INCOMPLETE"]
    title: str
    excluded: bool
    included: bool


class ContextHistoryOut(BaseModel):
    version: int
    turns: list[ContextHistoryTurnOut]
    next_offset: int | None
