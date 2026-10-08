"""轮次取消闸门（切换会话不中断任务，票 01）。

持久取消的运行时拦截层：模型调用前与工具执行前检查取消标记（规格 §2/
§14——观察器负责打断在途等待，本闸门负责在下一个副作用开始前中止）。
标记源自执行侧观察器对 cancel_requested 的周期轮询（0.4s），存在观察
延迟窗口，故本闸门只是尽力拦截；「取消先落库后禁止新增副作用」的原子
最终校验由业务提交事务内的 runtime.turn_write_allowed 承担（agent/
runtime.py）——取消先落库则该次提交被拒，业务事务先提交则真实结果保留。
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
