"""学习目标列表只读工具（通用 Agent 第三阶段工单 01）。

按 course_id 列出课程全部学习目标（复用 GoalService.list_for_course）；
课程不存在 = 结构化未找到并指引回 search_courses（禁猜 id 纪律）。恒挂载
全部会话类型，计入统一每轮预算与字符累计；limit 统一形态（省略=全部受硬
上限 100 保护，超限 total+truncated 如实透出）。
"""

import json

from langchain_core.tools import tool

from app.modules.agent.runtime import MAX_TOOL_CALLS_PER_TURN, current_agent_runtime
from app.modules.agent.tools.listing import (
    dump_payload,
    invalid_limit_message,
    resolve_list_limit,
    truncated_notice,
)
from app.modules.learning_plan.service import GoalService


@tool
async def list_goals(course_id: str, limit: int | None = None) -> str:
    """列出一门课程（知识空间）的全部学习目标（id、标题、类型、状态、期限、每日投入、更新时间）。

    用户想知道某门课的学习目标、或要修改/完成目标前需要先看到目标清单时
    使用：必须传 course_id（可先用 search_courses 查找确认）。进行中
    （ACTIVE）的目标排在最前。limit 是返回条数：用户要全部时省略，明确要
    N 条时传 N；省略时最多返回 100 条，超出时载荷带 total 与 truncated，
    请如实转述总数。课程不存在时工具会明确说明，此时先用 search_courses
    重新确认课程 id，不要猜测。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps(
            {"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "goals": []}, ensure_ascii=False
        )
    shown_limit = resolve_list_limit(limit)
    if shown_limit is None:
        return dump_payload("goals", ok=False, message=invalid_limit_message())
    if runtime.budget.calls_used >= MAX_TOOL_CALLS_PER_TURN:
        return dump_payload(
            "goals", message="本轮查询次数已达上限，请基于已获得的查询结果直接回答。"
        )
    runtime.budget.calls_used += 1
    try:
        async with runtime.session_factory() as session:
            goals = await GoalService.list_for_course(session, course_id)
    except Exception:
        return dump_payload("goals", ok=False, message="目标查询暂时失败，请稍后重试。")
    if goals is None:
        return dump_payload(
            "goals",
            ok=False,
            message="课程不存在或已删除；请先用 search_courses 确认课程 id，不要猜测。",
        )
    total = len(goals)
    truncated = total > shown_limit
    payload = dump_payload(
        "goals",
        [
            {
                "id": goal.id,
                "title": goal.title,
                "goal_type": goal.goal_type,
                "status": goal.status,
                "target_date": goal.target_date,
                "daily_minutes": goal.daily_minutes,
                "updated_at": goal.updated_at.strftime("%Y-%m-%d %H:%M"),
            }
            for goal in goals[:shown_limit]
        ],
        truncated_notice(total, shown_limit) if truncated else "",
        total=total,
        truncated=truncated,
    )
    runtime.budget.chars_fed += len(payload)
    return payload
