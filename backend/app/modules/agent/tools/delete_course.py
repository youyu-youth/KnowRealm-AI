"""删除课程薄工具（通用 Agent 第二阶段工单 04）。

删除是高风险操作（L3）：任何授权档位下都逐项确认，确认卡完整呈现级联影响
（课程下的记录清单与计数）；批准后、执行前课程新增记录则提案失效、需重新
预览（新增记录不会被悄悄纳入删除）。工具名 = 注册项 action（流式分发按名
识别）。
"""

import json
from typing import Any

from langchain_core.tools import tool

from app.modules.agent.operations.course_soft_delete import DELETE_COURSE_ACTION
from app.modules.agent.operations.registry import (
    lenient_tool_args_schema,
    submit_operation,
)
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.schemas import CourseSoftDeletePayload

# 工具名（langchain @tool 注册名 = 函数名）。
DELETE_COURSE_TOOL_NAME = "delete_course"


@tool(args_schema=lenient_tool_args_schema(CourseSoftDeletePayload))
async def delete_course(**kwargs: Any) -> str:
    """当用户想删除整门课程时使用：创建一条待确认的课程删除提案。

    需要目标课程 id（course_id，可先用 search_courses 查找）。删除会连同课程
    下的全部记录及其资产一并移除（确认卡会列出将删除的记录清单）；如只想让
    课程退出日常使用、保留数据，应改用归档（archive_course）。删除是高风险
    操作，即使用户已开启自动批准也需要逐项确认。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps(
            {"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "proposals": []},
            ensure_ascii=False,
        )
    payload = await submit_operation(
        runtime,
        DELETE_COURSE_ACTION,
        {key: value for key, value in kwargs.items() if value is not None},
    )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
