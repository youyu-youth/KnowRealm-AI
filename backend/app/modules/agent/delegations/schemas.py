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


class KnowledgeReport(BaseModel):
    """提交知识报告；仅用于最终输出，不执行检索、写入或授权。"""

    model_config = ConfigDict(extra="forbid")
    summary: str = Field(
        description=(
            "基于实际证据的 Markdown 报告，正文用[n]标注引用；"
            "引用行单独填 citation_lines；无有效报告时为空"
        )
    )
    gaps: list[str] = Field(
        description=(
            "只列 task 明确要求但尚未回答的问题；已回答 task 必须为空列表。"
            "未要求的扩展主题不列缺口，不能用常识补足资料缺口"
        ),
    )
    citation_lines: list[str] = Field(
        default_factory=list[str],
        description=(
            "原文引用行，每项一行：[n] 逐字摘录（来源：来源标题）；摘录最多80字，正文不要重复引用块"
        ),
    )

    @field_validator("citation_lines")
    @classmethod
    def single_line_citations(cls, value: list[str]) -> list[str]:
        if any("\n" in line or "\r" in line or not line.strip() for line in value):
            raise ValueError("每条引用须为独立非空单行")
        return [line.strip() for line in value]

    @field_validator("gaps")
    @classmethod
    def clean_gaps(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("缺口不能为空白")
        return list(dict.fromkeys(item.strip() for item in value))


class DelegationSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    execution_id: str
    execution_attempt: int = Field(ge=1)
    request_ids: list[str] = Field(min_length=1)
