"""轮次取消闸门（切换会话不中断任务，票 01）。

持久取消落实的「副作用前最后一道闸」：模型调用前与工具执行前检查取消
标记（规格 §2/§14——观察器负责打断在途等待，本闸门负责在下一个副作用
开始前中止）。业务提交的原子性由各工具自身事务保证：闸门命中时工具整体
不执行；取消落在工具执行中途则事务要么原子提交（保留真实结果）要么回滚。
"""

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import (  # pyright: ignore[reportMissingTypeStubs]
    AgentMiddleware,
    ToolCallRequest,
)


class TurnCancelledError(Exception):
    """轮次的持久取消已受理：中止图执行（由轮次 worker 转取消收口）。"""


class TurnCancelGuardMiddleware(
    AgentMiddleware[Any, Any, Any]  # pyright: ignore[reportMissingTypeStubs]
):
    """模型调用前 / 工具执行前的取消检查点（cancelled 回调由执行侧提供）。"""

    def __init__(self, cancelled: Callable[[], bool]) -> None:
        self._cancelled = cancelled

    @property
    def name(self) -> str:
        return "TurnCancelGuardMiddleware"

    async def abefore_model(  # pyright: ignore[reportMissingTypeStubs]
        self, state: Any, runtime: Any
    ) -> None:
        if self._cancelled():
            raise TurnCancelledError

    async def awrap_tool_call(  # pyright: ignore[reportMissingTypeStubs]
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        if self._cancelled():
            raise TurnCancelledError
        return await handler(request)
