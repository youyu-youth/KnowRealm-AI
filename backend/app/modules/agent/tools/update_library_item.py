"""修改资料条目薄工具（通用 Agent 第二阶段工单 03）：update_library_item。

标题 / 归类修改（收藏不接入，spec 决策 14）；确认卡 before/after 预览由
后端提交时同事务固化的快照承载。
"""

import json
from typing import Any

from langchain_core.tools import tool

from app.modules.agent.operations.library_item_update import UPDATE_LIBRARY_ITEM_ACTION
from app.modules.agent.operations.registry import (
    lenient_tool_args_schema,
    submit_operation,
)
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.schemas import LibraryItemUpdatePayload

# 工具名（langchain @tool 注册名 = 函数名）。
UPDATE_LIBRARY_ITEM_TOOL_NAME = "update_library_item"


@tool(args_schema=lenient_tool_args_schema(LibraryItemUpdatePayload))
async def update_library_item(**kwargs: Any) -> str:
    """当用户想重命名资料条目或修改其课程归类时使用：创建一条待确认的修改提案。

    需要目标条目 id（item_id，可先用 search_library 查找）与至少一个修改字段：
    标题（title）或归类目标课程 id（course_id，课程须存在且未归档）。只传要
    修改的字段，未传的字段保持不变。用户在确认卡确认后修改才会生效，条目在
    确认前被手动改过时提案会失效并需要重新确认。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps(
            {"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "proposals": []},
            ensure_ascii=False,
        )
    payload = await submit_operation(
        runtime,
        UPDATE_LIBRARY_ITEM_ACTION,
        {key: value for key, value in kwargs.items() if value is not None},
    )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
