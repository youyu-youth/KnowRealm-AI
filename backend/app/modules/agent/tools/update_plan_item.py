"""修改计划项薄工具（通用 Agent 第三阶段工单 03）：update_plan_item 的工具壳。

就地修改当前生效版本的计划项（日期 / 时长 / 内容）；确认卡展示 before/after
预览；确认后即时生效并置 user_locked（重生成原样保留）。
"""

import json
from typing import Any

from langchain_core.tools import tool

from app.modules.agent.operations.plan_item import UPDATE_PLAN_ITEM_ACTION
from app.modules.agent.operations.registry import (
    lenient_tool_args_schema,
    submit_operation,
)
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.schemas import PlanItemUpdatePayload

# 工具名（langchain @tool 注册名 = 函数名）。
UPDATE_PLAN_ITEM_TOOL_NAME = "update_plan_item"


@tool(args_schema=lenient_tool_args_schema(PlanItemUpdatePayload))
async def update_plan_item(**kwargs: Any) -> str:
    """当用户想调整某条计划项时使用：创建一条待确认的计划项修改提案。

    需要 item_id（先用 get_plan 查计划项列表取得）与至少一项变更：排期日期
    （scheduled_date，YYYY-MM-DD）、预估时长（estimated_minutes，分钟）或
    内容（content）。只有当前生效版本的计划项可以修改；确认前请向用户复述
    改动；用户确认后修改立即生效，且该项会被标记为用户锁定——重新生成计划
    时原样保留不被 AI 重排。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps(
            {"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "proposals": []},
            ensure_ascii=False,
        )
    payload = await submit_operation(
        runtime,
        UPDATE_PLAN_ITEM_ACTION,
        {key: value for key, value in kwargs.items() if value is not None},
    )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
