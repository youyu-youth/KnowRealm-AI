from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

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


class ContextViewOut(BaseModel):
    session_id: str
    version: int
    segment: int
    actual_turn_id: str | None
    actual: list[ModelRequestOut]
    next_estimate: InputEstimate | None
    next_error_code: str | None


class ContextPreviewRequest(BaseModel):
    content: str = Field(default="", max_length=8000)
    web_search: bool = False
    page: ChatPageSnapshot | None = None
