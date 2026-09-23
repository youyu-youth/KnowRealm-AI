"""归档 / 恢复资料条目薄工具（通用 Agent 第二阶段工单 03）。

归档＝条目退出默认浏览但保留数据与派生记录；恢复＝回到正常状态。归档
恢复走 lifecycle 既有核心（HTTP 路由与 Agent 应用器共用）。
"""

import json
from typing import Any

from langchain_core.tools import tool

from app.modules.agent.operations.library_item_archive import (
    ARCHIVE_LIBRARY_ITEM_ACTION,
    RESTORE_LIBRARY_ITEM_ACTION,
)
from app.modules.agent.operations.registry import (
    lenient_tool_args_schema,
    submit_operation,
)
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.schemas import LibraryItemArchivePayload

# 工具名（langchain @tool 注册名 = 函数名）。
ARCHIVE_LIBRARY_ITEM_TOOL_NAME = "archive_library_item"
RESTORE_LIBRARY_ITEM_TOOL_NAME = "restore_library_item"


async def _submit_library_item_status(action: str, kwargs: dict[str, Any]) -> str:
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps(
            {"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "proposals": []},
            ensure_ascii=False,
        )
    payload = await submit_operation(
        runtime,
        action,
        {key: value for key, value in kwargs.items() if value is not None},
    )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


@tool(args_schema=lenient_tool_args_schema(LibraryItemArchivePayload))
async def archive_library_item(**kwargs: Any) -> str:
    """当用户想归档资料条目时使用：创建一条待确认的条目归档提案。

    需要目标条目 id（item_id，可先用 search_library 查找）。归档后条目退出
    默认浏览（可在归档视图查看），已生成的学习记录与资产保留；之后可恢复。
    用户在确认卡确认后归档才会生效。
    """
    return await _submit_library_item_status(ARCHIVE_LIBRARY_ITEM_ACTION, kwargs)


@tool(args_schema=lenient_tool_args_schema(LibraryItemArchivePayload))
async def restore_library_item(**kwargs: Any) -> str:
    """当用户想恢复已归档的资料条目时使用：创建一条待确认的条目恢复提案。

    需要目标条目 id（item_id，可先用 search_library 查找）。恢复后条目回到
    默认浏览。用户在确认卡确认后恢复才会生效。
    """
    return await _submit_library_item_status(RESTORE_LIBRARY_ITEM_ACTION, kwargs)
