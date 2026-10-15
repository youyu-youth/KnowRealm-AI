from uuid import UUID

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
from app.modules.today.asset_schemas import AssetType
from app.modules.today.recent_assets import RecentAssetService


@tool
@budgeted(lambda: dump_payload("assets", ok=False, message="本轮查询次数已达上限。"))
async def list_recent_assets(
    asset_type: AssetType | None = None,
    course_id: UUID | None = None,
    limit: int | None = None,
) -> str:
    """查询近期已可用的学习产出，按记录和类型合并，时间倒序，不限日期。

    用户问最近整理出什么、有哪些总结/知识点/习题/复习资料时调用。
    只含 CONFIRMED 总结/复习资料及 ACTIVE 知识点/习题，不含待确认草稿。
    asset_type 可选 summary/knowledge_point/quiz/review_material，省略查询全部类型。
    course_id 省略查询全部课程；指定课程前用 search_courses 消歧，禁止猜 id。
    limit 为分组数量，省略返回全部并受列表硬上限保护。
    time_basis 为 confirmed 时表示确认时间，为 created 时表示创建时间，不能混称采纳时间。
    使用 href 提供来源链接；结果不含正文，查询不代表学习完成或实际投入时长。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return dump_payload("assets", ok=False, message="AGENT_CONTEXT_UNBOUND")
    shown = resolve_list_limit(limit)
    if shown is None:
        return dump_payload("assets", ok=False, message=invalid_limit_message())
    try:
        async with runtime.session_factory() as session:
            result = await RecentAssetService.list_recent(
                session,
                asset_type=asset_type,
                course_id=str(course_id) if course_id is not None else None,
                limit=shown,
            )
    except Exception:
        logger.exception("recent_assets_query_failed", session_id=runtime.session_id)
        return dump_payload("assets", ok=False, message="近期学习产出查询失败，请稍后重试。")
    truncated = result.total > len(result.items)
    payload = dump_payload(
        "assets",
        [item.model_dump(mode="json") for item in result.items],
        truncated_notice(result.total, shown) if truncated else "",
        total=result.total,
        truncated=truncated,
    )
    mark_output(payload)
    return payload
