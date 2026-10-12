"""工具声明的预算策略；业务提交预算仍独立。"""

from collections.abc import Callable
from dataclasses import dataclass

POLICY_VERSION = 1
MAX_TOOL_CALLS_PER_TURN = 6


@dataclass
class ToolCallBudget:
    calls_used: int = 0
    chars_fed: int = 0
    operations_created: int = 0


# 由工具装饰器声明一次；挂载仍由 AgentConfig 决定。
POLICIES: dict[str, Callable[[], str]] = {}
