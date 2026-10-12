"""时区换算只读工具（Agent 时间能力 v1）。

把一个具体时间在时区之间换算（如「2026-10-01 09:00 的东京时间对应纽约
几点」）；查询任意时区「现在几点」用 get_current_time。恒挂载全部会话
类型，计入统一每轮预算。
"""

import json
from datetime import UTC

from langchain_core.tools import tool

from app.modules.agent.budget.service import budgeted, mark_output
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.tools.time_utils import (
    parse_datetime_arg,
    resolve_timezone_arg,
    time_payload,
)


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
async def convert_time(
    datetime_value: str, to_timezone: str, from_timezone: str | None = None
) -> str:
    """把一个时间从源时区换算到目标时区（夏令时自动处理）。

    用户问「某个时间对应另一个时区几点」（如「东京 9 点是纽约几点」）时
    使用。datetime_value 传 ISO 8601 时间（如 2026-10-01T09:00:00，不带
    时区时按 from_timezone 或用户本地时区解释）；to_timezone / from_timezone
    传 IANA 时区名（如 Asia/Tokyo、America/New_York），from_timezone 可省略。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return _payload(
            {"result": None}, ok=False, message="当前对话未绑定运行时上下文，无法换算时间。"
        )
    user_tz = runtime.user_timezone or UTC
    try:
        target_tz = resolve_timezone_arg(to_timezone)
        source_tz = resolve_timezone_arg(from_timezone) if from_timezone else user_tz
        source = parse_datetime_arg(datetime_value, source_tz)
    except ValueError as exc:
        return _payload({"result": None}, ok=False, message=str(exc))
    payload = _payload(
        {
            "source": time_payload(source),
            "result": time_payload(source.astimezone(target_tz)),
        }
    )
    mark_output(payload)
    return payload
