"""工具调用身份绑定中间件（切换会话不中断任务，票 02，规格 §9）。

副作用幂等执行的逻辑调用身份来源：模型 tool_call id（``ToolCallRequest.
tool_call``）。图续跑重放同一 pending 工具调用时 id 稳定，与执行归属
（turn_id）、checkpoint namespace（中间件构建时注入的 thread id）共同构成
来源键；模型节点重生成产生的新调用 id 即新逻辑调用，不误去重。身份经
ContextVar 单对绑定／重置（先例 ``agent/runtime.py``），仅
``turns/effects.py`` 的幂等入口消费，只读工具无感。
"""

from collections.abc import Awaitable, Callable
from typing import Any, cast

from langchain.agents.middleware.types import (  # pyright: ignore[reportMissingTypeStubs]
    AgentMiddleware,
    ToolCallRequest,
)

from app.modules.agent.turns.effects import (
    ToolCallIdentity,
    bind_tool_call_identity,
    reset_tool_call_identity,
)


class ToolCallIdentityMiddleware(
    AgentMiddleware[Any, Any, Any]  # pyright: ignore[reportMissingTypeStubs]
):
    """工具执行期绑定稳定逻辑调用身份（供副作用幂等框架消费）。"""

    def __init__(self, namespace: str) -> None:
        self._namespace = namespace

    @property
    def name(self) -> str:
        return "ToolCallIdentityMiddleware"

    async def awrap_tool_call(  # pyright: ignore[reportMissingTypeStubs]
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        raw_id = cast(dict[str, Any], request.tool_call).get("id")
        if not isinstance(raw_id, str) or not raw_id:
            return await handler(request)
        token = bind_tool_call_identity(
            ToolCallIdentity(namespace=self._namespace, logical_call_id=raw_id)
        )
        try:
            return await handler(request)
        finally:
            reset_tool_call_identity(token)
