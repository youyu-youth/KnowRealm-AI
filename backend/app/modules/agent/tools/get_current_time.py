"""当前时间只读工具（Agent 时间能力 v1）。

可选 IANA 时区参数查任意时区的当前时间；缺省用用户时区（运行时上下文
user_timezone，偏好 timezone 未设置回退系统本地）。恒挂载全部会话类型，
计入统一每轮预算。system prompt 的时间提示行已注入组装时刻快照——本工具
用于用户明确询问时间、需要组装时刻之后的当下时间或换算其他时区的场合。
"""

import json
from datetime import UTC, datetime

from langchain_core.tools import tool

from app.modules.agent.budget.service import budgeted, mark_output
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.tools.time_utils import resolve_timezone_arg, time_payload


def _payload(body: dict[str, object], *, ok: bool = True, message: str = "") -> str:
    body["ok"] = ok
    if message:
        body["message"] = message
    payload = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    return payload


def _budget_rejection() -> str:
    return _payload(
        {"current": None},
        message="本轮查询次数已达上限，请基于已获得的结果直接回答。",
    )


@tool
@budgeted(_budget_rejection)
async def get_current_time(timezone: str | None = None) -> str:
    """获取当前日期与时间（精确到秒），可选目标时区。

    用户问「现在几点」「今天几号」「星期几」「东京/纽约现在几点」等时间
    问题时使用。timezone 传 IANA 时区名（如 Asia/Tokyo、America/New_York），
    省略则用用户本地时区；时区名无效会返回错误说明。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return _payload(
            {"current": None}, ok=False, message="当前对话未绑定运行时上下文，无法获取时间。"
        )
    try:
        tz = resolve_timezone_arg(timezone) if timezone else (runtime.user_timezone or UTC)
        payload = _payload({"current": time_payload(datetime.now(tz))})
    except ValueError as exc:
        return _payload({"current": None}, ok=False, message=str(exc))
    mark_output(payload)
    return payload
