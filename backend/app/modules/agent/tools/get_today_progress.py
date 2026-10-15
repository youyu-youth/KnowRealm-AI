import json
from uuid import UUID

from langchain_core.tools import tool
from loguru import logger

from app.modules.agent.budget.service import budgeted, mark_output
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.tools.listing import (
    invalid_limit_message,
    resolve_list_limit,
    truncated_notice,
)
from app.modules.today.service import TodayService


def _failure(message: str) -> str:
    return json.dumps({"ok": False, "message": message}, ensure_ascii=False)


@tool
@budgeted(lambda: _failure("本轮查询次数已达上限。"))
async def get_today_progress(course_id: UUID | None = None, limit: int | None = None) -> str:
    """查询电脑本地今天的学习计划进展、待完成/逾期数量和真实完成列表。

    用户问今天完成了什么、还要学多久时按需调用。course_id 省略查询全部课程；
    指定课程时先用 search_courses 消歧，禁止猜 id。limit 省略表示全部，受列表硬上限保护。
    预估投入不是实际学习时长；完成包括历史计划，普通待办、习题和总结确认不计入。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return _failure("AGENT_CONTEXT_UNBOUND")
    shown = resolve_list_limit(limit)
    if shown is None:
        return _failure(invalid_limit_message())
    try:
        async with runtime.session_factory() as session:
            progress = await TodayService.progress(
                session, course_id=str(course_id) if course_id is not None else None, limit=shown
            )
    except Exception:
        logger.exception("today_progress_query_failed", session_id=runtime.session_id)
        return _failure("今日进展暂时无法查询，请稍后重试。")
    data = progress.model_dump(mode="json", exclude={"courses", "offset", "limit"})
    truncated = progress.completed_count > len(progress.completed_items)
    payload = json.dumps(
        {
            "ok": True,
            **data,
            "total": progress.completed_count,
            "truncated": truncated,
            "message": truncated_notice(progress.completed_count, shown) if truncated else "",
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    mark_output(payload)
    return payload
