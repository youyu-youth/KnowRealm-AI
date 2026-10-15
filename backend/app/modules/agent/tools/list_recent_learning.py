from langchain_core.tools import tool
from loguru import logger

from app.modules.agent.budget.service import budgeted, mark_output
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.tools.listing import (
    dump_payload,
    invalid_limit_message,
    resolve_list_limit,
    truncated_notice,
)
from app.modules.today.resume import LearningResumeService


@tool
@budgeted(lambda: dump_payload("recent_learning", ok=False, message="本轮查询次数已达上限。"))
async def list_recent_learning(limit: int | None = None) -> str:
    """查询用户最近打开的学习记录、未交卷测验和对话，按访问时间倒序。

    用户问上次学到哪里、继续之前的内容时调用；排除当前提问会话。
    用户要最近 N 项时传 limit，要全部时省略（最多保留 30 个对象）。
    只读，不代表已完成学习；使用返回的 href 提供 Markdown 继续链接，禁止猜测位置。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return dump_payload("recent_learning", ok=False, message="AGENT_CONTEXT_UNBOUND")
    shown_limit = resolve_list_limit(limit)
    if shown_limit is None:
        return dump_payload("recent_learning", ok=False, message=invalid_limit_message())
    try:
        async with runtime.session_factory() as session:
            entries = await LearningResumeService.list_recent(
                session, exclude_session_id=runtime.session_id
            )
    except Exception:
        logger.exception("recent_learning_query_failed", session_id=runtime.session_id)
        return dump_payload("recent_learning", ok=False, message="续学记录查询失败，请稍后重试。")
    total = len(entries)
    truncated = total > shown_limit
    payload = dump_payload(
        "recent_learning",
        [entry.model_dump(mode="json") for entry in entries[:shown_limit]],
        truncated_notice(total, shown_limit) if truncated else "",
        total=total,
        truncated=truncated,
    )
    mark_output(payload)
    return payload
