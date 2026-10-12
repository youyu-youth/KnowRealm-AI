"""单个学习目标只读工具（通用 Agent 第三阶段工单 01）。

按 goal_id 取目标完整字段（id 经 list_goals 取得）；目标不存在或课程已
软删 = 结构化未找到并指引回 list_goals（禁猜 id 纪律）。恒挂载全部会话
类型，计入统一每轮预算与字符累计。
"""

import json

from langchain_core.tools import tool

from app.modules.agent.budget.service import budgeted, mark_output
from app.modules.agent.runtime import current_agent_runtime
from app.modules.learning_plan.service import GoalService


def _payload(goal: dict[str, object] | None, *, ok: bool = True, message: str = "") -> str:
    body: dict[str, object] = {"ok": ok, "goal": goal}
    if message:
        body["message"] = message
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


def _budget_rejection() -> str:
    return _payload(None, message="本轮查询次数已达上限，请基于已获得的查询结果直接回答。")


@tool
@budgeted(_budget_rejection)
async def get_goal(goal_id: str) -> str:
    """按 id 查询单个学习目标的完整信息（标题、类型、状态、期限、投入与范围确认状态）。

    用户想了解某个目标的详细情况时使用：必须传 goal_id（可先用 list_goals
    列出目标取得）。目标不存在时工具会明确说明，此时先用 list_goals 重新
    确认目标 id，不要猜测。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps(
            {"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "goal": None}, ensure_ascii=False
        )
    try:
        async with runtime.session_factory() as session:
            goal = await GoalService.get(session, goal_id)
    except Exception:
        return _payload(None, ok=False, message="目标查询暂时失败，请稍后重试。")
    if goal is None:
        return _payload(
            None,
            ok=False,
            message="目标不存在或所属课程已删除；请先用 list_goals 确认目标 id，不要猜测。",
        )
    payload = _payload(
        {
            "id": goal.id,
            "course_id": goal.course_id,
            "title": goal.title,
            "goal_type": goal.goal_type,
            "status": goal.status,
            "target_date": goal.target_date,
            "daily_minutes": goal.daily_minutes,
            "target_score": goal.target_score,
            "scope_source": goal.scope_source,
            "scope_confirmed": goal.scope_confirmed,
            "created_at": goal.created_at.strftime("%Y-%m-%d %H:%M"),
            "updated_at": goal.updated_at.strftime("%Y-%m-%d %H:%M"),
        }
    )
    mark_output(payload)
    return payload
