"""计划练习要求、状态与受控准备工具。"""

import json
from dataclasses import replace
from typing import Any

from langchain_core.tools import tool

from app.modules.agent.budget.service import budgeted, mark_output
from app.modules.agent.operations.practice import (
    PracticeCancelPayload,
    PracticeGradingRetryPayload,
    PracticePreparePayload,
    PracticeRequirementsPayload,
    PracticeRoundStartPayload,
)
from app.modules.agent.operations.registry import lenient_tool_args_schema, submit_operation
from app.modules.agent.runs.schemas import AuthMode
from app.modules.agent.runtime import current_agent_runtime
from app.modules.learning_plan.practice import state
from app.shared.errors import CodedHTTPException


@tool
@budgeted(lambda: json.dumps({"ok": False, "error": "TOOL_CALL_LIMIT"}))
async def get_plan_practice(item_id: str) -> str:
    """查询练习要求、准备进度、最近轮次及各历史轮次进度、分母、成绩、评分错误和站内入口，不返回答案。

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
    用户明确要求重练时传 expected_round_id/version（来自当前 round 的 test_id/version）；
    未交卷旧轮须先复述 answered_count/total_count 及放弃影响，abandon_confirmed=true
    经人工确认卡确认。只准备新题，随后用 preparation_id 调 start_plan_practice 原子切轮。
    新题优先，不足可复用且返回 reused_count；失败或取消保留旧轮，不自动扩源。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps({"ok": False, "error": "AGENT_CONTEXT_UNBOUND"})
    # 宽松工具 schema 将缺省字段传成 None，交回业务 schema 使用 False 默认值。
    if kwargs.get("abandon_confirmed") is None:
        kwargs.pop("abandon_confirmed", None)
    if kwargs.get("expected_round_id"):
        runtime = replace(runtime, auth_mode=AuthMode.REQUEST_APPROVAL)
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


@tool(args_schema=lenient_tool_args_schema(PracticeRoundStartPayload))
async def start_plan_practice(**kwargs: Any) -> str:
    """准备完成后开始（或继续）一轮计划练习，返回轮次状态与作答入口；不代替用户作答。

    requirements_revision 来自 get_plan_practice；request_id 用新 UUID，重试沿用原 UUID。
    已有轮次时返回该轮（评分中返回评分状态，不建新轮）。用户须在返回的 paper_path
    页面自己作答；完成后由用户用 complete_plan_item 明确确认，不能代答或自动完成。
    仅明确重练并完成准备后传该准备的 preparation_id，安全启动下一轮；历史结果保留。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps({"ok": False, "error": "AGENT_CONTEXT_UNBOUND"})
    return json.dumps(
        await submit_operation(runtime, "start_plan_practice", kwargs), ensure_ascii=False
    )


@tool(args_schema=lenient_tool_args_schema(PracticeGradingRetryPayload))
async def retry_plan_practice_grading(**kwargs: Any) -> str:
    """用户明确要求时重试已交卷计划练习的未评分题，成功题与答案保持不变。

    item_id/test_id 来自 get_plan_practice 的最近或历史轮次；新请求使用新 UUID，
    重放沿用原 request_id。已有评分任务返回同一任务；历史计划、完结目标及跳过项只读。
    可离开并用 get_plan_practice 查询任务与实际分母；评分不自动完成计划项。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps({"ok": False, "error": "AGENT_CONTEXT_UNBOUND"})
    return json.dumps(
        await submit_operation(runtime, "retry_plan_practice_grading", kwargs), ensure_ascii=False
    )
