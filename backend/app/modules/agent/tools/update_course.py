"""修改课程薄工具（通用 Agent 第二阶段工单 03）：update_course 动作的工具壳。

工具语义恒为「完成这件事」（修改课程信息），是否需要用户确认由后端档位
决定（spec 用户故事 39）；参数 schema 由注册项 payload schema 经
registry.lenient_tool_args_schema 派生，字段级与条件校验在提交时执法。
确认卡展示 before/after 预览（快照由后端提交时同事务固化，模型不提供）。
"""

import json
from typing import Any

from langchain_core.tools import tool

from app.modules.agent.operations.course_update import UPDATE_COURSE_ACTION
from app.modules.agent.operations.registry import (
    lenient_tool_args_schema,
    submit_operation,
)
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.schemas import CourseUpdatePayload

# 工具名（langchain @tool 注册名 = 函数名）。
UPDATE_COURSE_TOOL_NAME = "update_course"


@tool(args_schema=lenient_tool_args_schema(CourseUpdatePayload))
async def update_course(**kwargs: Any) -> str:
    """当用户想修改已有课程的信息时使用：创建一条待确认的课程修改提案。

    需要目标课程 id（course_id，可先用 search_courses 查找）与至少一个修改
    字段：名称（name）、学习场景（learning_context：SCHOOL 校园 / CAREER 职业 /
    INTEREST 兴趣）、教育阶段（education_stage，学业场景）、学习深度（depth，
    职业或兴趣场景）、课程类型（course_type）或说明（description）。场景切换
    时按目标场景补齐阶段或深度。确认前请向用户复述改动（改什么、从什么值改
    成什么值）；用户在确认卡确认后修改才会生效，目标课程在确认前被手动改过
    时提案会失效并需要重新确认。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps(
            {"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "proposals": []},
            ensure_ascii=False,
        )
    payload = await submit_operation(
        runtime,
        UPDATE_COURSE_ACTION,
        {key: value for key, value in kwargs.items() if value is not None},
    )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
