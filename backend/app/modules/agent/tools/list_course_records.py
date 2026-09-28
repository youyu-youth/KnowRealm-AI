"""课程记录列表只读工具（通用 Agent 插队票 08）：批量整理链路的目标枚举前置。

按 course_id 列出课程全部学习记录（复用 RecordService.list_for_course，
零新 SQL）；课程不存在 = 结构化未找到并指引回 search_courses（禁猜 id 纪律）。
恒挂载全部会话类型，计入统一每轮预算与字符累计；limit 统一形态（省略=全部
受硬上限 100 保护，超限 total+truncated 如实透出）。
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
from app.modules.record.service import RecordService


@tool
async def list_course_records(course_id: str, limit: int | None = None) -> str:
    """列出一门课程下的全部学习记录（id、标题、来源类型、状态、创建时间，按创建时间降序）。

    用户想知道某门课程里有哪些记录、或整理前需要先看到课程下的记录清单时
    使用：必须传 course_id（可先用 search_courses 查找确认）。limit 是返回
    条数：用户要全部时省略，明确要 N 条时传 N；省略时最多返回 100 条，超出
    时载荷带 total 与 truncated，请如实转述总数。课程不存在时工具会明确
    说明，此时先用 search_courses 重新确认课程，不要猜测课程 id。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps(
            {"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "records": []}, ensure_ascii=False
        )
    shown_limit = resolve_list_limit(limit)
    if shown_limit is None:
        return dump_payload("records", ok=False, message=invalid_limit_message())
    if runtime.budget.calls_used >= MAX_TOOL_CALLS_PER_TURN:
        return dump_payload(
            "records", message="本轮查询次数已达上限，请基于已获得的查询结果直接回答。"
        )
    runtime.budget.calls_used += 1
    # 查询异常不炸整轮流（同 search_courses 先例）：错误载荷 ok=false，模型可据此说明。
    try:
        async with runtime.session_factory() as session:
            records = await RecordService.list_for_course(session, course_id)
    except Exception:
        return dump_payload("records", ok=False, message="记录查询暂时失败，请稍后重试。")
    if records is None:
        return dump_payload(
            "records",
            ok=False,
            message="课程不存在或已删除；请先用 search_courses 确认课程 id，不要猜测。",
        )
    total = len(records)
    truncated = total > shown_limit
    payload = dump_payload(
        "records",
        [
            {
                "id": record.id,
                "title": record.title,
                "capture_type": record.capture_type,
                "status": record.status,
                "created_at": record.created_at.strftime("%Y-%m-%d %H:%M"),
            }
            for record in records[:shown_limit]
        ],
        truncated_notice(total, shown_limit) if truncated else "",
        total=total,
        truncated=truncated,
    )
    runtime.budget.chars_fed += len(payload)
    return payload
