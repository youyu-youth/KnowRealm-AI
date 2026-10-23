"""复用框架工具拦截点，参数结构校验之前完成准入。"""

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import (  # pyright: ignore[reportMissingTypeStubs]
    AgentMiddleware,
    ModelRequest,
    ToolCallRequest,
)
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import BaseTool

from app.modules.agent.budget.policy import POLICIES, budget_snapshot, calls_remaining
from app.modules.agent.budget.service import BudgetRejected, execute, restore_runtime
from app.modules.agent.middleware.cancel_guard import TurnCancelledError
from app.modules.agent.runtime import current_agent_runtime


class ToolBudgetMiddleware(AgentMiddleware[Any, Any, Any]):  # pyright: ignore[reportMissingTypeStubs]
    async def awrap_model_call(  # pyright: ignore[reportMissingTypeStubs]
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], Awaitable[Any]]
    ) -> Any:
        runtime = current_agent_runtime()
        if runtime is None:
            return await handler(request)
        await restore_runtime(runtime)
        budget = budget_snapshot(runtime.budget)
        guidance = (
            f"\n本执行工具额度：上限 {budget['limit']} 次，"
            f"已用 {budget['used']} 次，剩余 {budget['remaining']} 次。"
            f"根任务总额度（含父子）：{budget['root']}。"
            "每个执行分别限额，调用同时受根总额度约束；这是并发消费快照。"
        )
        tools = request.tools
        if calls_remaining(runtime.budget) == 0:
            tools = [
                item
                for item in tools
                if (item.name if isinstance(item, BaseTool) else item.get("name")) not in POLICIES
            ]
            guidance += (
                "额度已耗尽，停止补查与同轮重试，直接基于已有证据完成报告或汇总。"
                "TOOL_CALL_LIMIT 表示本次请求未执行；不得把它当作检索无命中或资料不存在。"
                "保留已获得的证据和合规引用，整理和引用已有原文无需继续检索，"
                "不要把已取得的原文列为因额度耗尽未能核实。"
                "仅对用户所问但证据不足的内容，区分实际检索无命中和因额度耗尽未能核实；"
                "父任务汇总时保留子报告的未核实缺口，不得声称完整覆盖。"
            )
        blocks = (
            [dict(block) for block in request.system_message.content_blocks]
            if request.system_message
            else []
        )
        return await handler(
            request.override(
                tools=tools,
                system_message=SystemMessage(content=[*blocks, {"type": "text", "text": guidance}]),
            )
        )

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
