"""计划练习要求、状态与受控准备工具。"""

import json
from dataclasses import replace
from typing import Any

from langchain_core.tools import tool

from app.modules.agent.budget.service import budgeted, mark_output
from app.modules.agent.operations.practice import (
    PracticeCancelPayload,
    PracticePreparePayload,
    PracticeRequirementsPayload,
)
from app.modules.agent.operations.registry import lenient_tool_args_schema, submit_operation
from app.modules.agent.runs.schemas import AuthMode
from app.modules.agent.runtime import current_agent_runtime
from app.modules.learning_plan.practice import state
from app.shared.errors import CodedHTTPException


@tool
@budgeted(lambda: json.dumps({"ok": False, "error": "TOOL_CALL_LIMIT"}))
async def get_plan_practice(item_id: str) -> str:
    """查询计划项练习要求、准备进度、实际检索范围、题量缺口和本课程补源建议，不返回答案。

    item_id 先用 get_plan 获取。要求没有明确题量、题型或资料集合时向用户追问；
    不猜题量，不把模型或匹配失败说成缺题。来源建议需要用户明确确认后才可使用。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps({"ok": False, "error": "AGENT_CONTEXT_UNBOUND"})
    try:
        async with runtime.session_factory() as session:
            result = await state(session, item_id)
    except CodedHTTPException as exc:
        return json.dumps({"ok": False, "error": exc.code})
    output = json.dumps(
        {"ok": True, "practice": result.model_dump(mode="json")}, ensure_ascii=False
    )
    mark_output(output)
    return output


@tool(args_schema=lenient_tool_args_schema(PracticeRequirementsPayload))
async def confirm_practice_requirements(**kwargs: Any) -> str:
    """合并确认主题、精确正整数题量、题型和真实资料集合，保存新的练习要求修订。

    首次及扩源均须人工确认卡，不以任何执行授权代替业务确认。
    先 get_plan_practice 获取 plan_content 和 expected_revision；必须复述完整主题、
    数量、题型及 record_ids 实际对象，缺失或冲突先追问。仅本课程归属资料可用。
    扩源传新的完整资料集合与当前修订，拒绝建议无需修改原要求或放弃已有练习。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps({"ok": False, "error": "AGENT_CONTEXT_UNBOUND"})
    result = await submit_operation(
        replace(runtime, auth_mode=AuthMode.REQUEST_APPROVAL),
        "confirm_practice_requirements",
        kwargs,
    )
    return json.dumps(result, ensure_ascii=False)


@tool(args_schema=lenient_tool_args_schema(PracticePreparePayload))
async def prepare_plan_practice(**kwargs: Any) -> str:
    """按已确认要求准备恰好 N 道相关真实题，返回持久准备任务，尚不开始作答。

    requirements_revision 来自 get_plan_practice，request_id 使用新的 UUID；请求重放
    使用原 UUID。失败后显式重试使用新 UUID，要求不丢失，不随机取题或降低题量。
    受理后可离开，用 get_plan_practice 查询完成、缺口或失败；新增来源先确认要求。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps({"ok": False, "error": "AGENT_CONTEXT_UNBOUND"})
    return json.dumps(
        await submit_operation(runtime, "prepare_plan_practice", kwargs), ensure_ascii=False
    )


@tool(args_schema=lenient_tool_args_schema(PracticeCancelPayload))
async def cancel_practice_preparation(**kwargs: Any) -> str:
    """明确取消一项进行中的计划练习匹配；要求、已有练习和历史准备结果保留。

    preparation_id 从 get_plan_practice 获取，不能用离开页面或切换聊天代替取消。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps({"ok": False, "error": "AGENT_CONTEXT_UNBOUND"})
    return json.dumps(
        await submit_operation(runtime, "cancel_practice_preparation", kwargs), ensure_ascii=False
    )
