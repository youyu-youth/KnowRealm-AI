"""学习计划只读工具（通用 Agent 第三阶段工单 02）。

按 goal_id 取目标的 ACTIVE 计划与逐项内容（阶段 / 日期 / 时长 / 状态 /
理由，投影复用 PlanService.plan_out）；无计划或目标不可达 = 结构化说明并
指引（禁猜 id 纪律）。恒挂载全部会话类型，计入统一每轮预算与字符累计。
"""

import json

from langchain_core.tools import tool
from loguru import logger

from app.modules.agent.budget.service import budgeted, mark_output
from app.modules.agent.runtime import current_agent_runtime
from app.modules.learning_plan.service import GoalService, PlanService


def _payload(plan: dict[str, object] | None, *, ok: bool = True, message: str = "") -> str:
    body: dict[str, object] = {"ok": ok, "plan": plan}
    if message:
        body["message"] = message
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


def _budget_rejection() -> str:
    return _payload(None, message="本轮查询次数已达上限，请基于已获得的查询结果直接回答。")


@tool
@budgeted(_budget_rejection)
async def get_plan(goal_id: str) -> str:
    """按目标 id 查询当前生效的学习计划（阶段、逐项内容、排期日期、时长、状态与生成理由）。

    用户想了解「我的学习计划是什么 / 接下来学什么」时使用：必须传 goal_id
    （可先用 list_goals 列出目标取得）。目标没有进行中的计划时工具会明确
    说明，可用 generate_learning_plan 生成新草案。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps(
            {"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "plan": None},
            ensure_ascii=False,
        )
    try:
        async with runtime.session_factory() as session:
            goal = await GoalService.get(session, goal_id)
            if goal is None:
                payload = _payload(
                    None,
                    ok=False,
                    message="目标不存在或所属课程已删除；请先用 list_goals 确认目标 id，不要猜测。",
                )
                mark_output(payload)
                return payload
            plan = await PlanService.get_active_for_goal(session, goal.id)
            if plan is None:
                payload = _payload(
                    None,
                    message="该目标还没有生效的学习计划；可用 generate_learning_plan 生成草案。",
                )
                mark_output(payload)
                return payload
            items = await PlanService.list_items(session, plan.id)
            projection = PlanService.plan_out(plan, items, course_id=goal.course_id)
    except Exception:
        logger.warning("get_plan_failed", error_code="PLAN_QUERY_FAILED")
        return _payload(None, ok=False, message="计划查询暂时失败，请稍后重试。")
    payload = _payload(projection.model_dump(mode="json"))
    mark_output(payload)
    return payload
