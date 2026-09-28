"""资料库条目列表只读工具（通用 Agent 插队票 08）：批量整理链路的目标枚举前置。

按 source_type / course_id / q 三维可选过滤列出资料条目（复用
LibraryService.list_items 默认视图：排除归档与软删；availability 派生过滤
不进 V1——grill Q26）。恒挂载全部会话类型，计入统一每轮预算与字符累计；
limit 统一形态（省略=全部受硬上限 100 保护，超限 total+truncated 如实透出）。
"""

import json
from uuid import UUID

from langchain_core.tools import tool

from app.modules.agent.runtime import MAX_TOOL_CALLS_PER_TURN, current_agent_runtime
from app.modules.agent.tools.listing import (
    dump_payload,
    invalid_limit_message,
    resolve_list_limit,
    truncated_notice,
)
from app.modules.library.schemas import LibraryItemListQuery, LibrarySourceType
from app.modules.library.service import LibraryService


@tool
async def list_library_items(
    source_type: str | None = None,
    course_id: str | None = None,
    q: str | None = None,
    limit: int | None = None,
) -> str:
    """列出资料库条目（id、标题、来源类型、归属课程名、更新时间，按更新时间降序）。

    用户想知道资料库里有哪些条目、或整理前需要先看到条目清单时使用。可按
    来源类型（AUDIO / DOCUMENT / WEB / BOOK / TEXT）、归属课程（course_id，
    可先用 search_courses 查找确认）或关键词（q，匹配标题、来源链接与
    元数据）过滤，全部省略 = 列全部。limit 是返回条数：用户要全部时省略，
    明确要 N 条时传 N；省略时最多返回 100 条，超出时载荷带 total 与
    truncated，请如实转述总数。默认不含已归档与回收站中的条目。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps(
            {"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "items": []}, ensure_ascii=False
        )
    shown_limit = resolve_list_limit(limit)
    if shown_limit is None:
        return dump_payload("items", ok=False, message=invalid_limit_message())
    parsed_source: LibrarySourceType | None = None
    if source_type is not None and source_type.strip():
        try:
            parsed_source = LibrarySourceType(source_type.strip())
        except ValueError:
            return dump_payload(
                "items",
                ok=False,
                message="source_type 仅支持 AUDIO / DOCUMENT / WEB / BOOK / TEXT。",
            )
    parsed_course: UUID | None = None
    if course_id is not None and course_id.strip():
        try:
            parsed_course = UUID(course_id.strip())
        except ValueError:
            return dump_payload(
                "items", ok=False, message="course_id 格式不正确；请先用 search_courses 查找确认。"
            )
    needle = (q or "").strip() or None
    if runtime.budget.calls_used >= MAX_TOOL_CALLS_PER_TURN:
        return dump_payload(
            "items", message="本轮查询次数已达上限，请基于已获得的查询结果直接回答。"
        )
    runtime.budget.calls_used += 1
    # 查询异常不炸整轮流（同 search_courses 先例）：错误载荷 ok=false，模型可据此说明。
    try:
        async with runtime.session_factory() as session:
            out = await LibraryService.list_items(
                session,
                LibraryItemListQuery(
                    limit=shown_limit,
                    source_type=parsed_source,
                    course_id=parsed_course,
                    q=needle,
                ),
            )
    except Exception:
        return dump_payload("items", ok=False, message="资料条目查询暂时失败，请稍后重试。")
    total = out.total
    truncated = total > shown_limit
    payload = dump_payload(
        "items",
        [
            {
                "id": item.id,
                "title": item.title,
                "source_type": item.source_type,
                "course_name": item.course_name,
                "updated_at": item.updated_at.strftime("%Y-%m-%d %H:%M"),
            }
            for item in out.items
        ],
        truncated_notice(total, shown_limit) if truncated else "",
        total=total,
        truncated=truncated,
    )
    runtime.budget.chars_fed += len(payload)
    return payload
