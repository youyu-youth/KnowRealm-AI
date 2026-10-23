"""工具声明的预算策略；业务提交预算仍独立。"""

from collections.abc import Callable
from dataclasses import dataclass

POLICY_VERSION = 2
MAX_TOOL_CALLS_PER_TURN = 6
MAX_ROOT_TOOL_CALLS = 18
MAX_EXECUTION_OUTPUT_CHARS = 12_000
MAX_ROOT_OUTPUT_CHARS = 36_000


@dataclass
class ToolCallBudget:
    calls_used: int = 0
    chars_fed: int = 0
    operations_created: int = 0
    root_calls_used: int = 0
    root_chars_fed: int = 0


def budget_snapshot(budget: ToolCallBudget) -> dict[str, object]:
    return {
        "limit": MAX_TOOL_CALLS_PER_TURN,
        "used": budget.calls_used,
        "remaining": max(0, MAX_TOOL_CALLS_PER_TURN - budget.calls_used),
        "root": {
            "limit": MAX_ROOT_TOOL_CALLS,
            "used": budget.root_calls_used,
            "remaining": max(0, MAX_ROOT_TOOL_CALLS - budget.root_calls_used),
        },
    }


def calls_remaining(budget: ToolCallBudget) -> int:
    return max(
        0,
        min(
            MAX_TOOL_CALLS_PER_TURN - budget.calls_used,
            MAX_ROOT_TOOL_CALLS - budget.root_calls_used,
        ),
    )


def output_remaining(budget: ToolCallBudget) -> int:
    return max(
        0,
        min(
            MAX_EXECUTION_OUTPUT_CHARS - budget.chars_fed,
            MAX_ROOT_OUTPUT_CHARS - budget.root_chars_fed,
        ),
    )


# 由工具装饰器声明一次；挂载仍由 AgentConfig 决定。
POLICIES: dict[str, Callable[[], str]] = {}
