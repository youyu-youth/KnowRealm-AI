"""移除共享引用薄工具（通用 Agent 第三阶段工单 05）：remove_shared_ref 动作的工具壳。

删除引用行即解除共享（原资料不动、归属不变）。确认卡预览被移除的引用
（快照由后端提交时同事务固化，模型不提供）。
"""

import json
from typing import Any

from langchain_core.tools import tool

from app.modules.agent.operations.registry import (
    lenient_tool_args_schema,
    submit_operation,
)
from app.modules.agent.operations.shared_ref import REMOVE_SHARED_REF_ACTION
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.schemas import SharedRefPayload

# 工具名（langchain @tool 注册名 = 函数名）。
REMOVE_SHARED_REF_TOOL_NAME = "remove_shared_ref"


@tool(args_schema=lenient_tool_args_schema(SharedRefPayload))
async def remove_shared_ref(**kwargs: Any) -> str:
    """当用户想移除某课程对一份外部资料的共享引用时使用：创建一条待确认的移除引用提案。

    需要 course_id（引用所在课程）与 library_item_id（被引用资料条目，可先用
    list_shared_refs 列出课程引用查找）。移除只解除本课程的引用，原资料不受
    任何影响（内容、归属、资产都保留）。用户在确认卡确认后移除才会生效。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps(
            {"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "proposals": []},
            ensure_ascii=False,
        )
    payload = await submit_operation(
        runtime,
        REMOVE_SHARED_REF_ACTION,
        {key: value for key, value in kwargs.items() if value is not None},
    )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
