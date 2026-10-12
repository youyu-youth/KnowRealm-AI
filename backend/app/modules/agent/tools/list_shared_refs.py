"""共享引用清单只读工具（通用 Agent 第三阶段工单 05）。

按 course_id 列出知识空间引用的外部资料（复用 SharedRefService.list_for_course）；
课程不存在 = 结构化未找到并指引回 search_courses（禁猜 id 纪律）。恒挂载
全部会话类型，计入统一每轮预算与字符累计；limit 统一形态（省略=全部受硬
上限 100 保护，超限 total+truncated 如实透出）。
"""

import json

from langchain_core.tools import tool

from app.modules.agent.budget.service import budgeted, mark_output
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.tools.listing import (
    dump_payload,
    invalid_limit_message,
    resolve_list_limit,
    truncated_notice,
)
from app.modules.library.shared_refs import SharedRefService


def _budget_rejection() -> str:
    return dump_payload(
        "shared_refs", message="本轮查询次数已达上限，请基于已获得的查询结果直接回答。"
    )


@tool
@budgeted(_budget_rejection)
async def list_shared_refs(course_id: str, limit: int | None = None) -> str:
    """列出一门课程（知识空间）引用的外部共享资料（条目 id、标题、来源类型、
    归属空间、是否可用、引用时间）。

    用户想知道某门课引用了哪些外部资料、或要添加/移除引用前需要先看到引用
    清单时使用：必须传 course_id（可先用 search_courses 查找确认）。已被
    软删的资料 available 为 false（来源已删除，内容不再进入问答检索）。
    limit 是返回条数：用户要全部时省略，明确要 N 条时传 N；省略时最多返回
    100 条，超出时载荷带 total 与 truncated，请如实转述总数。课程不存在时
    工具会明确说明，此时先用 search_courses 重新确认课程 id，不要猜测。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps(
            {"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "shared_refs": []}, ensure_ascii=False
        )
    shown_limit = resolve_list_limit(limit)
    if shown_limit is None:
        return dump_payload("shared_refs", ok=False, message=invalid_limit_message())
    try:
        async with runtime.session_factory() as session:
            refs = await SharedRefService.list_for_course(session, course_id)
    except Exception:
        return dump_payload("shared_refs", ok=False, message="引用清单查询暂时失败，请稍后重试。")
    if refs is None:
        return dump_payload(
            "shared_refs",
            ok=False,
            message="课程不存在或已删除；请先用 search_courses 确认课程 id，不要猜测。",
        )
    total = len(refs)
    truncated = total > shown_limit
    payload = dump_payload(
        "shared_refs",
        [
            {
                "library_item_id": ref.library_item_id,
                "title": ref.title,
                "source_type": ref.source_type,
                "owner_course_name": ref.owner_course_name,
                "available": ref.available,
                "created_at": ref.created_at.strftime("%Y-%m-%d %H:%M"),
            }
            for ref in refs[:shown_limit]
        ],
        truncated_notice(total, shown_limit) if truncated else "",
        total=total,
        truncated=truncated,
    )
    mark_output(payload)
    return payload
