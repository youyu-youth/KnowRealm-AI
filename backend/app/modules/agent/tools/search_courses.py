"""课程查询只读工具（通用 Agent 第一阶段工单 01）：对象查询工具族首个成员。

名称子串 → 候选（id、名称、状态、场景、阶段或深度、更新时间），供模型完成
同名消歧与目标确认（spec 实施决策 14：禁万能 query 工具，每对象族一个类型化
只读工具）；恒挂载全部会话类型（操作工具组成员，02/03 写工具加入同组）。
计入统一工具调用预算（spec 实施决策 16：与 search_library 共用调用数与字符
数累计）；候选上限截断附 truncated 明示，不静默丢弃。
"""

import json

from langchain_core.tools import tool

from app.modules.agent.runtime import MAX_TOOL_CALLS_PER_TURN, current_agent_runtime
from app.modules.course.service import CourseService

# 候选上限：同名课程超过上限时截断并明示（按更新时间降序取最近）。
SEARCH_COURSES_LIMIT = 8


def _payload(
    courses: list[dict[str, object]] | None = None,
    message: str = "",
    *,
    ok: bool = True,
    truncated: bool = False,
) -> str:
    body: dict[str, object] = {"ok": ok, "courses": courses or []}
    if message:
        body["message"] = message
    if truncated:
        body["truncated"] = True
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


@tool
async def search_courses(query: str) -> str:
    """按名称查找用户的课程，返回候选列表（id、名称、状态、学习场景、阶段或深度、更新时间）。

    当用户提到某个课程、需要确定目标课程或区分同名课程时使用：输入课程名称
    或名称片段。多个同名候选时原样列出让用户选择，用户确认前不要使用任何
    候选的 id；唯一匹配才可直接使用；未找到时如实告知并与用户确认名称，
    不要猜测或编造课程 id，也不要未经用户明确要求擅自新建课程。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps(
            {"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "courses": []}, ensure_ascii=False
        )
    needle = query.strip()
    if not needle:
        return _payload(ok=False, message="课程名称检索词不能为空。")
    if runtime.budget.calls_used >= MAX_TOOL_CALLS_PER_TURN:
        return _payload(message="本轮查询次数已达上限，请基于已获得的查询结果直接回答。")
    runtime.budget.calls_used += 1
    # 查询异常不炸整轮流（同 search_library 先例）：错误载荷 ok=false，模型可据此说明。
    try:
        async with runtime.session_factory() as session:
            courses = await CourseService.list(session, q=needle)
    except Exception:
        return _payload(ok=False, message="课程查询暂时失败，请稍后重试。")
    if not courses:
        return _payload(message=f"未找到名称包含「{needle}」的课程；请与用户确认课程名称。")
    truncated = len(courses) > SEARCH_COURSES_LIMIT
    payload = _payload(
        [
            {
                "id": course.id,
                "name": course.name,
                "status": course.status,
                "learning_context": course.learning_context,
                "stage_or_depth": course.education_stage or course.depth,
                "updated_at": course.updated_at.strftime("%Y-%m-%d %H:%M"),
            }
            for course in courses[:SEARCH_COURSES_LIMIT]
        ],
        (
            f"同名课程较多，仅列最近更新的 {SEARCH_COURSES_LIMIT} 个；"
            "目标不在其中时请让用户提供更准确的名称。"
            if truncated
            else ""
        ),
        truncated=truncated,
    )
    # 字符数累计进统一预算；载荷天然有界（候选 ≤SEARCH_COURSES_LIMIT × 各字段
    # 上限），无需单工具截断，累计值由 search_library 的截断逻辑统一执法。
    runtime.budget.chars_fed += len(payload)
    return payload
