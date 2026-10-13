from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.agent.schemas import ChatPageSnapshot
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


class ContextPreviewRequest(BaseModel):
    content: str = Field(default="", max_length=8000)
    web_search: bool = False
    page: ChatPageSnapshot | None = None
