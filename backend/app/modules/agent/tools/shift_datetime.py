"""日期时间平移只读工具（Agent 时间能力 v1）。

在给定时间上加减天 / 周 / 小时 / 分钟（参数可正可负），返回平移后的
结果时刻。按日历钟点平移（同一时区内的墙上时间加法），跨夏令时切换的
钟点语义由 zoneinfo 求值。恒挂载全部会话类型，计入统一每轮预算。
"""

import json
from datetime import UTC, timedelta

from langchain_core.tools import tool

from app.modules.agent.budget.service import budgeted, mark_output
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.tools.time_utils import parse_datetime_arg, time_payload


def _payload(body: dict[str, object], *, ok: bool = True, message: str = "") -> str:
    body["ok"] = ok
    if message:
        body["message"] = message
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


def _budget_rejection() -> str:
    return _payload(
        {"result": None},
        message="本轮查询次数已达上限，请基于已获得的结果直接回答。",
    )


@tool
@budgeted(_budget_rejection)
async def shift_datetime(
    datetime_value: str,
    days: int = 0,
    weeks: int = 0,
    hours: int = 0,
    minutes: int = 0,
) -> str:
    """在给定时间上加减一段时间，返回结果日期与时间（跨月/跨年/闰年自动处理）。

    用户问「3 天后是几号」「两周前是星期几」「再加 90 分钟是什么时间」等
    日期推算时使用——这类推算容易算错，优先用本工具而不是心算。
    datetime_value 传 ISO 8601 时间（如 2026-10-01T09:00:00，不带时区时按
    用户本地时区解释）；days / weeks / hours / minutes 传整数，可正可负，
    至少传一个非零值。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return _payload(
            {"result": None}, ok=False, message="当前对话未绑定运行时上下文，无法推算时间。"
        )
    if days == 0 and weeks == 0 and hours == 0 and minutes == 0:
        return _payload(
            {"result": None},
            ok=False,
            message="至少提供一个非零的平移量（days/weeks/hours/minutes）。",
        )
    try:
        base = parse_datetime_arg(datetime_value, runtime.user_timezone or UTC)
    except ValueError as exc:
        return _payload({"result": None}, ok=False, message=str(exc))
    shifted = base + timedelta(days=days, weeks=weeks, hours=hours, minutes=minutes)
    payload = _payload({"base": time_payload(base), "result": time_payload(shifted)})
    mark_output(payload)
    return payload
