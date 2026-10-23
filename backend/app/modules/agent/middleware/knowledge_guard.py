"""Knowledge 的执行白名单同时拦截模型猜测的骨架内置工具。"""

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import (  # pyright: ignore[reportMissingTypeStubs]
    AgentMiddleware,
    ToolCallRequest,
)
from langchain_core.messages import ToolMessage

from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.tools.finish_knowledge_report import finish_knowledge_report


class KnowledgeToolGuardMiddleware(
    AgentMiddleware[Any, Any, Any]  # pyright: ignore[reportMissingTypeStubs]
):
    def __init__(self, retrieval: bool) -> None:
        self._retrieval = retrieval

    async def awrap_tool_call(  # pyright: ignore[reportMissingTypeStubs]
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        runtime = current_agent_runtime()
        report_only = (
            runtime is not None
            and runtime.execution_id is not None
            and request.tool_call["name"] == finish_knowledge_report.name
        )
        if report_only or (self._retrieval and request.tool_call["name"] == "search_library"):
            return await handler(request)
        return ToolMessage(
            content="本地知识助手仅可检索当前挂载资料，不支持写操作、联网或委派。",
            tool_call_id=request.tool_call["id"],
            name=request.tool_call["name"],
            status="error",
        )
