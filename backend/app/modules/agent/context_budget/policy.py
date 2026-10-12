import json
from collections.abc import Sequence
from hashlib import sha256
from math import ceil
from typing import Any

from langchain_core.messages import AnyMessage, convert_to_openai_messages
from langchain_core.utils.function_calling import convert_to_openai_tool

from app.modules.agent.context_budget.schemas import ContextPolicy, InputEstimate
from app.modules.settings.config import LlmProviderConfig
from app.modules.settings.model_budget import output_reserve, resolve_capability


def policy_for(provider: LlmProviderConfig) -> ContextPolicy:
    capability = resolve_capability(provider.base_url, provider.model, provider.model_budget)
    output_reserve(capability)
    return ContextPolicy(base_url=provider.base_url, model=provider.model, capability=capability)


def _encoded(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def estimate_input(
    policy: ContextPolicy, messages: Sequence[AnyMessage], tools: Sequence[Any]
) -> InputEstimate:
    wire_messages = convert_to_openai_messages(list(messages))
    wire_tools = [convert_to_openai_tool(tool) for tool in tools]
    system = [item for item in wire_messages if item["role"] == "system"]
    other = [item for item in wire_messages if item["role"] != "system"]
    # shortcut: 未具备供应商完整 tokenizer 适配；UTF-8 每两字节估一 token，
    # 包含 schema/协议并保留 20% 余量，接入可靠完整请求计数器后改为 10%。
    components = {
        "system": ceil(len(_encoded(system).encode("utf-8")) / 2),
        "messages": ceil(len(_encoded(other).encode("utf-8")) / 2),
        "tools": ceil(len(_encoded(wire_tools).encode("utf-8")) / 2),
        "protocol": 64 + 16 * len(messages) + 64 * len(tools),
    }
    reserve = output_reserve(policy.capability)
    limits: list[int] = []
    if policy.capability.input_limit is not None:
        limits.append(policy.capability.input_limit)
    if policy.capability.context_window is not None:
        limits.append(policy.capability.context_window - reserve)
    capacity = min(limits)
    margin = ceil(capacity * 0.2)
    budget = capacity - margin
    tokens = sum(components.values())
    return InputEstimate(
        policy=policy,
        input_tokens=tokens,
        components=components,
        output_reserve=reserve,
        input_capacity=capacity,
        safety_margin=margin,
        usable_budget=budget,
        remaining=budget - tokens,
        message_count=len(messages),
        tool_count=len(tools),
        input_fingerprint=sha256(
            _encoded({"messages": wire_messages, "tools": wire_tools}).encode()
        ).hexdigest(),
        error_code="MODEL_INPUT_BUDGET_EXCEEDED" if tokens > budget else None,
    )
