"""课程查询只读工具（通用 Agent 第一阶段工单 01；插队票 08 扩展枚举语义）。

两条分支：关键词（名称子串 → 候选，供同名消歧与目标确认，固定上限 8，
行为不变）与枚举（query 省略 = 全部课程按更新时间降序，limit 统一形态：
省略=全部受硬上限 100 保护，超限 total+truncated 如实透出）。恒挂载全部
会话类型（操作工具组成员，02/03 写工具加入同组）；计入统一工具调用预算
（spec 实施决策 16：与 search_library 共用调用数与字符数累计）。
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
from app.modules.course.models import Course
from app.modules.course.service import CourseService

# 候选上限：同名课程超过上限时截断并明示（按更新时间降序取最近）。
SEARCH_COURSES_LIMIT = 8


def _course_row(course: Course) -> dict[str, object]:
    """候选 / 枚举共用的课程行（spec 实施决策 14 契约字段）。"""
    return {
        "id": course.id,
        "name": course.name,
        "status": course.status,
        "learning_context": course.learning_context,
        "stage_or_depth": course.education_stage or course.depth,
        "updated_at": course.updated_at.strftime("%Y-%m-%d %H:%M"),
    }


@tool
async def search_courses(query: str | None = None, limit: int | None = None) -> str:
    """查找用户的课程：给名称时按名称查找候选，省略名称时列出全部课程。

    两种用法：①用户提到某个课程、需要确定目标或区分同名课程时，传课程名称
    或名称片段，返回候选列表（id、名称、状态、学习场景、阶段或深度、更新
    时间）；多个同名候选时原样列出让用户选择，用户确认前不要使用任何候选
    的 id；唯一匹配才可直接使用。②用户想看自己有哪些课程时，省略 query，
    按更新时间降序列出全部。
    limit 是列出全部时的返回条数：用户要全部时省略，明确要 N 条时传 N；
    省略时最多返回 100 条，超出时载荷带 total 与 truncated，请如实转述
    总数（按名称查找时 limit 不生效，固定最多返回 8 个候选）。
    未找到时如实告知并与用户确认名称，不要猜测或编造课程 id，也不要未经
    用户明确要求擅自新建课程。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps(
            {"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "courses": []}, ensure_ascii=False
        )
    needle = (query or "").strip()
    # 展示上限：枚举分支 = limit 统一形态；关键词分支 = 固定候选上限 8。
    if not needle:
        resolved = resolve_list_limit(limit)
        if resolved is None:
            return dump_payload("courses", ok=False, message=invalid_limit_message())
        shown_limit = resolved
    else:
        shown_limit = SEARCH_COURSES_LIMIT
    if runtime.budget.calls_used >= MAX_TOOL_CALLS_PER_TURN:
        return dump_payload(
            "courses", message="本轮查询次数已达上限，请基于已获得的查询结果直接回答。"
        )
    runtime.budget.calls_used += 1
    # 查询异常不炸整轮流（同 search_library 先例）：错误载荷 ok=false，模型可据此说明。
    try:
        async with runtime.session_factory() as session:
            courses = await CourseService.list(session, q=needle or None)
    except Exception:
        return dump_payload("courses", ok=False, message="课程查询暂时失败，请稍后重试。")
    if not needle:
        # 枚举分支（插队票 08）：全部课程按更新时间降序 + total/truncated 透出。
        total = len(courses)
        truncated = total > shown_limit
        payload = dump_payload(
            "courses",
            [_course_row(course) for course in courses[:shown_limit]],
            truncated_notice(total, shown_limit)
            if truncated
            else ("用户还没有任何课程。" if total == 0 else ""),
            total=total,
            truncated=truncated,
        )
        runtime.budget.chars_fed += len(payload)
        return payload
    if not courses:
        return dump_payload(
            "courses", message=f"未找到名称包含「{needle}」的课程；请与用户确认课程名称。"
        )
    truncated = len(courses) > shown_limit
    payload = dump_payload(
        "courses",
        [_course_row(course) for course in courses[:shown_limit]],
        (
            f"同名课程较多，仅列最近更新的 {shown_limit} 个；"
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
