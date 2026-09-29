"""计划确认工具（通用 Agent 第三阶段工单 02）：confirm_plan 动作的工具壳。

工具语义恒为「把草案提交给用户确认」（L2 批量创建）：默认档落 OP_PLAN_CONFIRM
提案＝草案确认卡（只读预览），AUTO_APPROVE 档仍落确认卡（草案卡即确认闸门）、
FULL_ACCESS 直执行；参数 schema 由注册项 payload schema 经
registry.lenient_tool_args_schema 派生，字段级与条件校验在提交时执法。
"""

import json
from typing import Any

from langchain_core.tools import tool

from app.modules.agent.operations.plan_confirm import CONFIRM_PLAN_ACTION
from app.modules.agent.operations.registry import (
    lenient_tool_args_schema,
    submit_operation,
)
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.schemas import PlanConfirmPayload

CONFIRM_PLAN_TOOL_NAME = "confirm_plan"


@tool(args_schema=lenient_tool_args_schema(PlanConfirmPayload))
async def confirm_plan(**kwargs: Any) -> str:
    """把学习计划草案提交用户确认（草案此刻仍未保存）。

    参数 = generate_learning_plan 返回的 plan 字段原样：goal_id 与 phases
    （每项含 action_type / content / estimated_minutes / reason / record_id /
    scheduled_date）。必须逐字段照抄草案、不加改动不删项——确认卡展示的与
    落库写入的是同一份载荷，改动会破坏一致性。草案 JSON 只通过本工具的参数
    传递，不要在回复正文输出 JSON 或代码块。用户在确认卡确认后计划才生效；
    排期与目标不符时工具会返回期望日期，按其修正后重交。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps(
            {"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "proposals": []},
            ensure_ascii=False,
        )
    payload = await submit_operation(
        runtime,
        CONFIRM_PLAN_ACTION,
        {key: value for key, value in kwargs.items() if value is not None},
    )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
