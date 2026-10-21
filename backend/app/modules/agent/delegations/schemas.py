from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.agent.schemas import ChatCitationOut


class KnowledgeTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task: str = Field(min_length=1, max_length=8000, description="同一挂载范围内明确的本地知识任务")

    @field_validator("task")
    @classmethod
    def clean_task(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("任务不能为空白")
        return value.strip()


class KnowledgeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: Literal[1] = 1
    task_id: str
    status: Literal["COMPLETED", "PARTIAL", "FAILED", "INTERRUPTED", "CANCELLED"]
    summary: str = ""
    citations: list[ChatCitationOut] = Field(default_factory=list[ChatCitationOut])
    gaps: list[str] = Field(default_factory=list[str])
    error_code: str | None = None


class DelegationSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    execution_id: str
    execution_attempt: int = Field(ge=1)
    request_ids: list[str] = Field(min_length=1)
