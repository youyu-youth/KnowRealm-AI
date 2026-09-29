"""修改学习目标薄工具（通用 Agent 第三阶段工单 01）：update_goal 动作的工具壳。

编辑目标字段（标题 / 期限 / 每日投入 / 目标分数）或状态流转（完成 / 归档）。
确认卡展示 before/after 预览（快照由后端提交时同事务固化，模型不提供）。
"""

import json
from typing import Any

from langchain_core.tools import tool

from app.modules.agent.operations.goal_update import UPDATE_GOAL_ACTION
from app.modules.agent.operations.registry import (
    lenient_tool_args_schema,
    submit_operation,
)
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.schemas import GoalUpdatePayload

# 工具名（langchain @tool 注册名 = 函数名）。
UPDATE_GOAL_TOOL_NAME = "update_goal"


@tool(args_schema=lenient_tool_args_schema(GoalUpdatePayload))
async def update_goal(**kwargs: Any) -> str:
    """当用户想修改学习目标或标记目标完成/归档时使用：创建一条待确认的目标修改提案。

    需要目标 id（goal_id，可先用 list_goals 列出课程的目标查找）与至少一项
    变更：标题（title）、期限（target_date，YYYY-MM-DD）、每日投入分钟数
    （daily_minutes）、目标分数（target_score），或状态（status：COMPLETED
    完成 / ARCHIVED 归档，均为终态不可逆）。只有进行中的目标可以修改；确认前
    请向用户复述改动；用户在确认卡确认后修改才会生效，目标在确认前被手动改
    过时提案会失效并需要重新确认。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps(
            {"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "proposals": []},
            ensure_ascii=False,
        )
    payload = await submit_operation(
        runtime,
        UPDATE_GOAL_ACTION,
        {key: value for key, value in kwargs.items() if value is not None},
    )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
