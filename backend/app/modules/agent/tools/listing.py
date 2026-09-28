"""对象查询工具族共享的列表形态（插队票 08）。

三工具（search_courses 枚举分支 / list_course_records / list_library_items）
统一 limit 形态（grill Q29/Q30）：数量由用户话术决定——要全部给全部、要 N
给 N；limit 省略 = 返回全部、受硬上限保护，指定照传、同受硬上限；超限在
载荷透出 total 与 truncated，模型如实转述，不静默丢弃。固定上限仅保留在
关键词消歧分支（SEARCH_COURSES_LIMIT=8，行为不变）。
"""

import json

# 列表硬上限：省略 limit 时的「全部」语义受此保护（每条约 100 字符，100 条
# ≈ 10k 贴每轮 12k 字符预算，grill Q29）。
LIST_HARD_LIMIT = 100


def invalid_limit_message() -> str:
    """limit 非法值的结构化拒绝文案（三工具逐字一致；引用常量防漂移）。"""
    return f"limit 必须是正整数；省略表示返回全部（最多 {LIST_HARD_LIMIT} 条）。"


def resolve_list_limit(limit: int | None) -> int | None:
    """limit 统一解析：省略 = 硬上限；指定照传且同受硬上限；非正数 = None
    （非法值，由调用方结构化拒绝，不静默改写语义）。"""
    if limit is None:
        return LIST_HARD_LIMIT
    if limit < 1:
        return None
    return min(limit, LIST_HARD_LIMIT)


def truncated_notice(total: int, shown: int) -> str:
    """超限截断的明示文案：三工具逐字一致，模型学一次规则用三处。"""
    return f"共 {total} 条，仅列前 {shown} 条；请如实向用户说明总数与已列数量，不要谎称已全部列出。"


def dump_payload(
    collection_key: str,
    rows: list[dict[str, object]] | None = None,
    message: str = "",
    *,
    ok: bool = True,
    total: int | None = None,
    truncated: bool = False,
) -> str:
    """对象查询工具族统一 JSON 载荷（collection_key = courses/records/items）。"""
    body: dict[str, object] = {"ok": ok, collection_key: rows or []}
    if message:
        body["message"] = message
    if total is not None:
        body["total"] = total
    if truncated:
        body["truncated"] = True
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))
