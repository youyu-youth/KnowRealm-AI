"""跨课迁移记录薄工具（通用 Agent 第二阶段工单 04）。

记录内容与记录级资产随记录移动到目标课程；原课程的概念、历史作答与学习
证据保留历史归属。记录有正在进行的处理任务（如总结生成中）时迁移会被拒绝
并提示等待。工具名 = 注册项 action（流式分发按名识别）。
"""

import json
from typing import Any

from langchain_core.tools import tool

from app.modules.agent.operations.record_move_course import MOVE_RECORD_COURSE_ACTION
from app.modules.agent.operations.registry import (
    lenient_tool_args_schema,
    submit_operation,
)
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.schemas import RecordMoveCoursePayload

# 工具名（langchain @tool 注册名 = 函数名）。
MOVE_RECORD_COURSE_TOOL_NAME = "move_record_course"


@tool(args_schema=lenient_tool_args_schema(RecordMoveCoursePayload))
async def move_record_course(**kwargs: Any) -> str:
    """当用户想把一条学习记录移动到另一门课程时使用：创建一条待确认的迁移提案。

    需要 record_id（可先用 search_library 查找）与 target_course_id（可先用
    search_courses 查找）。记录的总结、知识点、Todo 与复习资料会随记录出现在
    目标课程；原课程的历史测试与学习证据保留历史归属。记录有处理任务进行中
    时会被拒绝，需等待处理完成。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps(
            {"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "proposals": []},
            ensure_ascii=False,
        )
    payload = await submit_operation(
        runtime,
        MOVE_RECORD_COURSE_ACTION,
        {key: value for key, value in kwargs.items() if value is not None},
    )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
