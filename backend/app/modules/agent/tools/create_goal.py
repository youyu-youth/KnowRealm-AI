"""创建学习目标薄工具（通用 Agent 第三阶段工单 01）：create_goal 动作的工具壳。

工具语义恒为「创建目标提案」，是否需要用户确认由后端档位决定；参数 schema
由注册项 payload schema（agent.schemas.GoalCreatePayload）经
registry.lenient_tool_args_schema 派生，必填校验在提案创建时执法（缺失 →
结构化缺失项 → 模型转述追问）。
"""

import json
from typing import Any

from langchain_core.tools import tool

from app.modules.agent.operations.goal_create import CREATE_GOAL_ACTION
from app.modules.agent.operations.registry import (
    lenient_tool_args_schema,
    submit_operation,
)
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.schemas import GoalCreatePayload

# 工具名（langchain @tool 注册名 = 函数名）。
CREATE_GOAL_TOOL_NAME = "create_goal"


@tool(args_schema=lenient_tool_args_schema(GoalCreatePayload))
async def create_goal(**kwargs: Any) -> str:
    """当用户想为某门课程（知识空间）制定学习目标时使用：创建一条待用户确认的目标提案。

    必填信息：目标课程 id（course_id，可先用 search_courses 查找）、目标类型
    （goal_type：SKILL 技能掌握 / EXAM 考试备考 / PROJECT 项目实战 / READING
    阅读计划 / CUSTOM 自定义）与目标标题（title，一句话概括要达成什么）。
    可选信息：期限（target_date，YYYY-MM-DD）与每日投入分钟数（daily_minutes）、
    目标分数（target_score）。用户没说期限或每日投入时先追问，明确表示没有才
    省略；用户想定目标但还没有课程时，先与其确认新建课程（create_course）
    再回来定目标。同一课程同时只有一个进行中目标：已有进行中目标时工具会
    返回明确提示，请转告用户先完成或归档旧目标。信息齐全前不要调用本工具；
    调用成功只是创建了待确认提案，用户在确认卡确认后目标才生效。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps(
            {"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "proposals": []},
            ensure_ascii=False,
        )
    payload = await submit_operation(
        runtime,
        CREATE_GOAL_ACTION,
        {key: value for key, value in kwargs.items() if value is not None},
    )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
