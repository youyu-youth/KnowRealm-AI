"""复用框架工具拦截点，参数结构校验之前完成准入。"""

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import (  # pyright: ignore[reportMissingTypeStubs]
    AgentMiddleware,
    ToolCallRequest,
)
from langchain_core.messages import ToolMessage

from app.modules.agent.budget.policy import POLICIES
from app.modules.agent.budget.service import BudgetRejected, execute
from app.modules.agent.middleware.cancel_guard import TurnCancelledError


class ToolBudgetMiddleware(AgentMiddleware[Any, Any, Any]):  # pyright: ignore[reportMissingTypeStubs]
    async def awrap_tool_call(  # pyright: ignore[reportMissingTypeStubs]
        self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], Awaitable[Any]]
    ) -> Any:
        call = request.tool_call
        if request.tool is None or call["name"] not in POLICIES:
            return await handler(request)
        try:
            result = await execute(call["name"], call["args"], lambda: handler(request))
        except BudgetRejected as exc:
            if exc.code == "CHAT_TURN_CANCELLED":
                raise TurnCancelledError from exc
            raise
        if isinstance(result, str):
            return ToolMessage(content=result, tool_call_id=call["id"], name=call["name"])
        return result
