"""归档 / 恢复课程薄工具（通用 Agent 第二阶段工单 03）。

两个动作语义（归档＝退出日常使用但保留全部数据、恢复＝回到正常状态），
共用本文件；工具名 = 注册项 action（流式分发按名识别）。归档后课程不再
接受新资料（既有读取护栏），确认卡由后端快照提供 before/after 预览。
"""

import json
from typing import Any

from langchain_core.tools import tool

from app.modules.agent.operations.course_archive import (
    ARCHIVE_COURSE_ACTION,
    RESTORE_COURSE_ACTION,
)
from app.modules.agent.operations.registry import (
    lenient_tool_args_schema,
    submit_operation,
)
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.schemas import CourseArchivePayload

# 工具名（langchain @tool 注册名 = 函数名）。
ARCHIVE_COURSE_TOOL_NAME = "archive_course"
RESTORE_COURSE_TOOL_NAME = "restore_course"


async def _submit_course_status(action: str, kwargs: dict[str, Any]) -> str:
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


@tool(args_schema=lenient_tool_args_schema(CourseArchivePayload))
async def archive_course(**kwargs: Any) -> str:
    """当用户想归档课程时使用：创建一条待确认的课程归档提案。

    需要目标课程 id（course_id，可先用 search_courses 查找）。归档后课程保留
    全部数据（记录、总结、知识点等），但不再接受新资料；之后可随时恢复。
    用户在确认卡确认后归档才会生效。
    """
    return await _submit_course_status(ARCHIVE_COURSE_ACTION, kwargs)


@tool(args_schema=lenient_tool_args_schema(CourseArchivePayload))
async def restore_course(**kwargs: Any) -> str:
    """当用户想恢复已归档的课程时使用：创建一条待确认的课程恢复提案。

    需要目标课程 id（course_id，可先用 search_courses 查找）。恢复后课程回到
    正常状态、可继续接受新资料。用户在确认卡确认后恢复才会生效。
    """
    return await _submit_course_status(RESTORE_COURSE_ACTION, kwargs)
