"""空骨架闸门（ADR-0018）：deepagents 内置工具与默认摘要件对模型不可见。"""

from collections.abc import Callable
from typing import Any

from langchain.agents.middleware.types import (  # pyright: ignore[reportMissingTypeStubs]
    AgentMiddleware,
    ModelRequest,
)

# deepagents 内置工具名（文件 / shell / 委派）。未来工单启用某个内置工具时，
# 从此集合移除对应名字，模型即可见（task 可见的前提是 subagents 非空）。
DEEPAGENT_TOOL_NAMES = frozenset(
    {
        "delete",
        "edit_file",
        "execute",
        "glob",
        "grep",
        "ls",
        "read_file",
        "task",
        "write_file",
    }
)


class ExcludeDeepAgentToolsMiddleware(
    AgentMiddleware[Any, Any, Any]  # pyright: ignore[reportMissingTypeStubs]
):
    """空骨架闸门：从模型请求中移除 deepagents 内置工具。

    模型请求的工具列表每次调用重建，此处不改图结构；FilesystemMiddleware
    默认不注入提示词、子代理信息只随 task 工具描述出现（均已核实 0.7.13），
    因此工具名移除后内置能力对模型完全不可见。
    """

    @property
    def name(self) -> str:
        return "ExcludeDeepAgentToolsMiddleware"

    def _without_builtin_tools(self, request: ModelRequest[Any]) -> ModelRequest[Any]:
        return request.override(
            tools=[
                tool
                for tool in request.tools
                if getattr(tool, "name", None) not in DEEPAGENT_TOOL_NAMES
            ]
        )

    def wrap_model_call(  # pyright: ignore[reportMissingTypeStubs]
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Any],
    ) -> Any:
        return handler(self._without_builtin_tools(request))

    async def awrap_model_call(  # pyright: ignore[reportMissingTypeStubs]
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Any],
    ) -> Any:
        return await handler(self._without_builtin_tools(request))


class NoopSummarizationMiddleware(
    AgentMiddleware[Any, Any, Any]  # pyright: ignore[reportMissingTypeStubs]
):
    """同名替换 deepagents 默认摘要件：chat 每轮从 chat_messages 显式重建上下文
    （窗口裁剪 + 预算计量），摘要卸载（逐出消息写 backend 文件）不适用，原位禁用。"""

    @property
    def name(self) -> str:
        return "SummarizationMiddleware"
