"""时间差只读工具（Agent 时间能力 v1）。

计算两个时间的差（end 减 start，正负均可），返回天/时/分/秒分解与
总量（总天数/小时/分钟）。恒挂载全部会话类型，计入统一每轮预算。
"""

import json
from datetime import UTC

from langchain_core.tools import tool

from app.modules.agent.runtime import MAX_TOOL_CALLS_PER_TURN, current_agent_runtime
from app.modules.agent.tools.time_utils import parse_datetime_arg, time_payload


def _payload(body: dict[str, object], *, ok: bool = True, message: str = "") -> str:
    body["ok"] = ok
    if message:
        body["message"] = message
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


@tool
async def diff_datetime(start: str, end: str) -> str:
    """计算两个时间相差多久（end 减 start，结果可正可负）。

    用户问「距离考试还有多少天」「两个时间差几个小时」等间隔计算时使用。
    start / end 传 ISO 8601 时间（如 2026-10-01T09:00:00 或带时区的
    2026-10-01T09:00:00+08:00，不带时区时按用户本地时区解释）；两个时间
    可以用不同时区表示，差值按实际时刻计算。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return _payload(
            {"diff": None}, ok=False, message="当前对话未绑定运行时上下文，无法计算时间差。"
        )
    if runtime.budget.calls_used >= MAX_TOOL_CALLS_PER_TURN:
        return _payload(
            {"diff": None},
            message="本轮查询次数已达上限，请基于已获得的结果直接回答。",
        )
    runtime.budget.calls_used += 1
    user_tz = runtime.user_timezone or UTC
    try:
        start_dt = parse_datetime_arg(start, user_tz)
        end_dt = parse_datetime_arg(end, user_tz)
    except ValueError as exc:
        return _payload({"diff": None}, ok=False, message=str(exc))
    delta = end_dt - start_dt
    total_seconds = int(delta.total_seconds())
    sign = -1 if total_seconds < 0 else 1
    magnitude = abs(total_seconds)
    payload = _payload(
        {
            "start": time_payload(start_dt),
            "end": time_payload(end_dt),
            "diff": {
                "days": delta.days,
                "hours": sign * (magnitude // 3600 % 24),
                "minutes": sign * (magnitude // 60 % 60),
                "seconds": sign * (magnitude % 60),
                "total_days": round(delta.total_seconds() / 86400, 4),
                "total_hours": round(delta.total_seconds() / 3600, 4),
                "total_minutes": round(delta.total_seconds() / 60, 2),
            },
        }
    )
    runtime.budget.chars_fed += len(payload)
    return payload
