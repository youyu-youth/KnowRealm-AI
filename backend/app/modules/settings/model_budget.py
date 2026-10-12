"""端点与模型共同决定可信能力；兼容部署只采用显式配置。"""

from pydantic import BaseModel, Field

from app.shared.errors import CodedHTTPException


class ModelBudgetConfig(BaseModel):
    input_limit: int | None = Field(default=None, ge=1, le=100_000_000)
    context_window: int | None = Field(default=None, ge=1, le=100_000_000)
    max_output: int | None = Field(default=None, ge=1, le=100_000_000)
    answer_output: int = Field(default=4096, ge=1, le=100_000_000)
    summary_output: int = Field(default=1024, ge=1, le=100_000_000)


class ModelCapabilityOut(ModelBudgetConfig):
    sources: dict[str, str] = Field(default_factory=dict)


QWEN_SOURCE = "https://help.aliyun.com/zh/model-studio/qwen-plus"
OPENAI_SOURCE = "https://developers.openai.com/api/docs/models/gpt-4.1"
# shortcut: 仅维护已核实的两项官方文本模型，新增模型先核实端点和官方能力。
TRUSTED_CAPABILITIES = {
    ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"): (
        ModelBudgetConfig(input_limit=995904, context_window=1000000, max_output=32768),
        QWEN_SOURCE,
    ),
    ("https://api.openai.com/v1", "gpt-4.1"): (
        ModelBudgetConfig(context_window=1047576, max_output=32768),
        OPENAI_SOURCE,
    ),
}


def resolve_capability(
    base_url: str, model: str, config: ModelBudgetConfig | None
) -> ModelCapabilityOut:
    trusted = TRUSTED_CAPABILITIES.get((base_url.rstrip("/"), model))
    values = (trusted[0] if trusted else ModelBudgetConfig()).model_dump()
    sources = {
        key: trusted[1]
        for key in ("input_limit", "context_window", "max_output")
        if trusted and values[key] is not None
    }
    if config is not None:
        for key, value in config.model_dump().items():
            if value is not None:
                values[key] = value
                sources[key] = "USER"
    return ModelCapabilityOut.model_validate({**values, "sources": sources})


def output_reserve(capability: ModelCapabilityOut, *, summary: bool = False) -> int:
    if capability.input_limit is None and capability.context_window is None:
        raise CodedHTTPException(
            code="MODEL_CAPABILITY_REQUIRED",
            status_code=409,
            detail="请在 AI 服务设置中配置此端点与模型的输入上限或总窗口",
        )
    limits = [capability.summary_output if summary else capability.answer_output]
    if capability.max_output is not None:
        limits.append(capability.max_output)
    if capability.context_window is not None:
        limits.append(capability.context_window - 1)
    reserve = min(limits)
    if reserve < 1:
        raise CodedHTTPException(
            code="MODEL_INPUT_BUDGET_EXCEEDED",
            status_code=409,
            detail="模型窗口无法容纳输入和输出，请调整模型能力配置",
        )
    return reserve
