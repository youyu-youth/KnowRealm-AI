"""完成计划项薄工具（通用 Agent 第三阶段工单 03）：complete_plan_item 的工具壳。

勾选完成当前生效版本的计划项：DONE + 完成时间戳（学习时长统计口径，不产
learning_event、不直接提高概念掌握度）。
"""

import json
from typing import Any

from langchain_core.tools import tool

from app.modules.agent.operations.plan_item import COMPLETE_PLAN_ITEM_ACTION
from app.modules.agent.operations.registry import (
    lenient_tool_args_schema,
    submit_operation,
)
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.schemas import PlanItemCompletePayload

# 工具名（langchain @tool 注册名 = 函数名）。
COMPLETE_PLAN_ITEM_TOOL_NAME = "complete_plan_item"


@tool(args_schema=lenient_tool_args_schema(PlanItemCompletePayload))
async def complete_plan_item(**kwargs: Any) -> str:
    """当用户说「这条计划完成了 / 学完这条了」时使用：创建一条待确认的计划项完成提案。

    需要 item_id（先用 get_plan 查计划项列表取得）。只有当前生效版本的
    计划项可以完成；用户确认后该项标记为已完成并记录完成时间。完成只记录
    执行事实，不会直接提高概念掌握度。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps(
            {"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "proposals": []},
            ensure_ascii=False,
        )
    payload = await submit_operation(
        runtime,
        COMPLETE_PLAN_ITEM_ACTION,
        {key: value for key, value in kwargs.items() if value is not None},
    )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
