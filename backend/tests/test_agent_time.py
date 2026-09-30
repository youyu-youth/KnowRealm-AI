"""Agent 时间能力 v1：共享 helper、四只读工具、时间提示行注入与时区解析。

时间计算全部由 Python 确定性执行（脚本优先、LLM 次之）；测试用固定时刻与
固定时区断言，不依赖真实当前时间（DST 边界用美东 2026 年切换日固定样例，
中国无夏令时）。锚点口径 local_today 与偏好时区解析各自独立断言。
"""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from datetime import timezone as fixed_timezone
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import create_database
from app.db.migrations import run_migrations
from app.modules.agent.context import ContextRow, build_context_messages
from app.modules.agent.models import ChatRole
from app.modules.agent.runtime import (
    MAX_TOOL_CALLS_PER_TURN,
    AgentRuntimeContext,
    bind_agent_runtime_context,
    reset_agent_runtime_context,
)
from app.modules.agent.tools.convert_time import convert_time
from app.modules.agent.tools.diff_datetime import diff_datetime
from app.modules.agent.tools.get_current_time import get_current_time
from app.modules.agent.tools.shift_datetime import shift_datetime
from app.modules.agent.tools.time_utils import (
    format_time_hint,
    parse_datetime_arg,
    resolve_timezone_arg,
    time_payload,
    timezone_label,
    weekday_label,
)
from app.modules.learning_plan.scheduling import local_today
from app.modules.settings.config import resolve_user_timezone

SHANGHAI = ZoneInfo("Asia/Shanghai")
TOKYO = ZoneInfo("Asia/Tokyo")
NEW_YORK = ZoneInfo("America/New_York")


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@asynccontextmanager
async def bare_db(tmp_path: Path) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    _engine, session_factory = create_database(db_path)
    try:
        yield session_factory
    finally:
        await _engine.dispose()


async def invoke_time_tool(
    tool_obj: Any,
    args: dict[str, Any],
    tmp_path: Path,
    *,
    user_timezone: Any = SHANGHAI,
) -> dict[str, Any]:
    """时间工具族共用调用壳：绑定运行时（含用户时区）后 ainvoke 并解析载荷。

    时间工具不触碰数据库，session_factory 仅为满足运行时上下文的构造要求。"""
    async with bare_db(tmp_path) as session_factory:
        token = bind_agent_runtime_context(
            AgentRuntimeContext(
                session_factory=session_factory,
                session_id="sess-time",
                user_timezone=user_timezone,
            )
        )
        try:
            return cast("dict[str, Any]", json.loads(await tool_obj.ainvoke(args)))
        finally:
            reset_agent_runtime_context(token)


# ---------------------------------------------------------------------------
# 共享纯函数（time_utils）
# ---------------------------------------------------------------------------


def test_timezone_label_prefers_iana_key() -> None:
    assert timezone_label(SHANGHAI) == "Asia/Shanghai"
    assert timezone_label(fixed_timezone(timedelta(hours=8))) == "UTC+08:00"


def test_local_today_matches_system_local_date() -> None:
    assert local_today() == datetime.now().astimezone().date()


def test_parse_datetime_arg_naive_uses_default_timezone() -> None:
    parsed = parse_datetime_arg("2026-10-01T09:00:00", SHANGHAI)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timedelta(hours=8)
    # aware 输入保留自身 offset，不被 default_tz 改写。
    aware = parse_datetime_arg("2026-10-01T09:00:00+09:00", SHANGHAI)
    assert aware.utcoffset() == timedelta(hours=9)
    with pytest.raises(ValueError, match="Invalid isoformat string"):
        parse_datetime_arg("not-a-datetime", SHANGHAI)


def test_resolve_timezone_arg_rejects_unknown_names() -> None:
    assert resolve_timezone_arg("Asia/Tokyo") is not None
    with pytest.raises(ValueError, match="无法识别的时区名"):
        resolve_timezone_arg("北京时间")
    with pytest.raises(ValueError, match="无法识别的时区名"):
        resolve_timezone_arg("Not/AZone")


def test_format_time_hint_renders_seconds_and_weekday() -> None:
    now = datetime(2026, 9, 30, 14, 23, 5, tzinfo=SHANGHAI)
    hint = format_time_hint(now)
    assert hint.startswith("时间提示：当前时间 2026-09-30 14:23:05（星期三，Asia/Shanghai）")
    assert "get_current_time" in hint


def test_time_payload_projection_fields() -> None:
    body = time_payload(datetime(2026, 9, 30, 14, 23, 5, tzinfo=SHANGHAI))
    assert body == {
        "datetime": "2026-09-30T14:23:05+08:00",
        "date": "2026-09-30",
        "time": "14:23:05",
        "weekday": "星期三",
        "timezone": "Asia/Shanghai",
        "utc_offset": "+08:00",
    }


def test_weekday_label_covers_week() -> None:
    assert weekday_label(datetime(2026, 9, 28).date()) == "星期一"
    assert weekday_label(datetime(2026, 10, 4).date()) == "星期日"


# ---------------------------------------------------------------------------
# get_current_time：默认用户时区 / 显式时区 / 无效名 / 未绑定
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_get_current_time_defaults_to_user_timezone(tmp_path: Path) -> None:
    payload = await invoke_time_tool(get_current_time, {}, tmp_path)
    assert payload["ok"] is True
    current = cast("dict[str, Any]", payload["current"])
    assert current["timezone"] == "Asia/Shanghai"
    assert datetime.now(SHANGHAI).date().isoformat() == current["date"]


@pytest.mark.anyio
async def test_get_current_time_explicit_timezone(tmp_path: Path) -> None:
    payload = await invoke_time_tool(get_current_time, {"timezone": "America/New_York"}, tmp_path)
    current = cast("dict[str, Any]", payload["current"])
    assert current["timezone"] == "America/New_York"
    assert current["datetime"].endswith(("-04:00", "-05:00"))


@pytest.mark.anyio
async def test_get_current_time_rejects_invalid_timezone(tmp_path: Path) -> None:
    payload = await invoke_time_tool(get_current_time, {"timezone": "Mars/Olympus"}, tmp_path)
    assert payload["ok"] is False
    assert "无法识别的时区名" in cast("str", payload["message"])


@pytest.mark.anyio
async def test_get_current_time_unbound_returns_structured_error() -> None:
    payload = cast("dict[str, Any]", json.loads(await get_current_time.ainvoke({})))
    assert payload["ok"] is False


@pytest.mark.anyio
async def test_time_tools_share_call_budget(tmp_path: Path) -> None:
    """时间工具计入统一每轮预算：超限软引导（ok=True + 引导语，检索先例）。"""
    async with bare_db(tmp_path) as session_factory:
        runtime = AgentRuntimeContext(
            session_factory=session_factory, session_id="sess-time", user_timezone=SHANGHAI
        )
        runtime.budget.calls_used = MAX_TOOL_CALLS_PER_TURN
        token = bind_agent_runtime_context(runtime)
        try:
            payload = cast("dict[str, Any]", json.loads(await get_current_time.ainvoke({})))
        finally:
            reset_agent_runtime_context(token)
    assert payload["ok"] is True
    assert payload["current"] is None
    assert "上限" in cast("str", payload["message"])


# ---------------------------------------------------------------------------
# convert_time：时区换算 + DST 两态固定样例
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_convert_time_tokyo_to_new_york_before_dst_end(tmp_path: Path) -> None:
    """东京 10-01 09:00（EDT 期内）= 纽约 09-30 20:00（UTC-4）。"""
    payload = await invoke_time_tool(
        convert_time,
        {
            "datetime_value": "2026-10-01T09:00:00",
            "to_timezone": "America/New_York",
            "from_timezone": "Asia/Tokyo",
        },
        tmp_path,
    )
    assert payload["ok"] is True
    assert cast("dict[str, Any]", payload["result"])["datetime"] == "2026-09-30T20:00:00-04:00"


@pytest.mark.anyio
async def test_convert_time_after_dst_switch(tmp_path: Path) -> None:
    """美东 DST 2026-11-01 02:00 本地才切 EST：东京 09:00（UTC 00:00）仍在 EDT，
    = 纽约 10-31 20:00（UTC-4）。"""
    payload = await invoke_time_tool(
        convert_time,
        {
            "datetime_value": "2026-11-01T09:00:00",
            "to_timezone": "America/New_York",
            "from_timezone": "Asia/Tokyo",
        },
        tmp_path,
    )
    assert payload["ok"] is True
    assert cast("dict[str, Any]", payload["result"])["datetime"] == "2026-10-31T20:00:00-04:00"


@pytest.mark.anyio
async def test_convert_time_aware_input_ignores_from_timezone(tmp_path: Path) -> None:
    payload = await invoke_time_tool(
        convert_time,
        {
            "datetime_value": "2026-10-01T09:00:00+08:00",
            "to_timezone": "Asia/Tokyo",
            "from_timezone": "America/New_York",
        },
        tmp_path,
    )
    assert cast("dict[str, Any]", payload["result"])["datetime"] == "2026-10-01T10:00:00+09:00"


@pytest.mark.anyio
async def test_convert_time_rejects_invalid_target(tmp_path: Path) -> None:
    payload = await invoke_time_tool(
        convert_time, {"datetime_value": "2026-10-01T09:00:00", "to_timezone": "No/Where"}, tmp_path
    )
    assert payload["ok"] is False


# ---------------------------------------------------------------------------
# shift_datetime：跨月 / 负数 / 闰年 / DST wall 语义
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_shift_datetime_cross_month(tmp_path: Path) -> None:
    payload = await invoke_time_tool(
        shift_datetime, {"datetime_value": "2026-09-30T14:00:00", "days": 3}, tmp_path
    )
    assert cast("dict[str, Any]", payload["result"])["datetime"] == "2026-10-03T14:00:00+08:00"
    assert cast("dict[str, Any]", payload["result"])["weekday"] == "星期六"


@pytest.mark.anyio
async def test_shift_datetime_negative_weeks(tmp_path: Path) -> None:
    payload = await invoke_time_tool(
        shift_datetime, {"datetime_value": "2026-10-10T09:00:00", "weeks": -2}, tmp_path
    )
    assert cast("dict[str, Any]", payload["result"])["datetime"] == "2026-09-26T09:00:00+08:00"


@pytest.mark.anyio
async def test_shift_datetime_leap_year(tmp_path: Path) -> None:
    payload = await invoke_time_tool(
        shift_datetime, {"datetime_value": "2028-02-28T00:00:00", "days": 1}, tmp_path
    )
    assert cast("dict[str, Any]", payload["result"])["date"] == "2028-02-29"


@pytest.mark.anyio
async def test_shift_datetime_dst_wall_semantics(tmp_path: Path) -> None:
    """美东 2026-03-08 02:00 切 EDT（02:00~03:00 为不存在钟点）：墙上钟点加法
    后 02:30 落进 gap，PEP 495 fold=0 按切换前偏移（EST -5）求值。"""
    payload = await invoke_time_tool(
        shift_datetime,
        {"datetime_value": "2026-03-08T00:30:00", "hours": 2, "minutes": 0},
        tmp_path,
        user_timezone=NEW_YORK,
    )
    assert cast("dict[str, Any]", payload["result"])["datetime"] == "2026-03-08T02:30:00-05:00"


@pytest.mark.anyio
async def test_shift_datetime_requires_nonzero_delta(tmp_path: Path) -> None:
    payload = await invoke_time_tool(
        shift_datetime, {"datetime_value": "2026-10-01T09:00:00"}, tmp_path
    )
    assert payload["ok"] is False
    assert "非零" in cast("str", payload["message"])


# ---------------------------------------------------------------------------
# diff_datetime：正负差 / 跨时区 / 无效输入
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_diff_datetime_positive(tmp_path: Path) -> None:
    payload = await invoke_time_tool(
        diff_datetime,
        {"start": "2026-09-30T09:00:00", "end": "2026-10-03T09:30:00"},
        tmp_path,
    )
    diff = cast("dict[str, Any]", payload["diff"])
    assert diff["days"] == 3
    assert diff["minutes"] == 30
    assert diff["total_hours"] == 72.5


@pytest.mark.anyio
async def test_diff_datetime_negative(tmp_path: Path) -> None:
    payload = await invoke_time_tool(
        diff_datetime,
        {"start": "2026-10-03T09:00:00", "end": "2026-10-02T09:00:00"},
        tmp_path,
    )
    diff = cast("dict[str, Any]", payload["diff"])
    assert diff["days"] == -1
    assert diff["total_minutes"] == -1440.0


@pytest.mark.anyio
async def test_diff_datetime_mixed_timezones_by_instant(tmp_path: Path) -> None:
    """两输入不同时区表示：按实际时刻算差（09:00+08:00 与 02:00Z 差 1 小时）。"""
    payload = await invoke_time_tool(
        diff_datetime,
        {"start": "2026-10-01T09:00:00+08:00", "end": "2026-10-01T02:00:00+00:00"},
        tmp_path,
    )
    diff = cast("dict[str, Any]", payload["diff"])
    assert diff["hours"] == 1
    assert diff["days"] == 0


@pytest.mark.anyio
async def test_diff_datetime_invalid_input(tmp_path: Path) -> None:
    payload = await invoke_time_tool(
        diff_datetime, {"start": "yesterday", "end": "2026-10-01T09:00:00"}, tmp_path
    )
    assert payload["ok"] is False


# ---------------------------------------------------------------------------
# 时间提示行注入（页面提示同款动态段）
# ---------------------------------------------------------------------------


def test_time_hint_injection_appends_to_system_before_guidance() -> None:
    rows = [
        ContextRow(id="sys", role=ChatRole.SYSTEM, content="角色快照"),
        ContextRow(id="u1", role=ChatRole.USER, content="现在几点"),
    ]
    messages = build_context_messages(rows, time_hint=format_time_hint(datetime.now(SHANGHAI)))
    system = str(messages[0].content)
    assert system.startswith("角色快照\n时间提示：当前时间")
    assert "get_current_time" in system
    # 未提供时区（测试上下文缺省）：零注入，既有提示面不变（行为回归锚）。
    baseline = build_context_messages(rows)
    assert "时间提示" not in str(baseline[0].content)


# ---------------------------------------------------------------------------
# 偏好时区解析：设置优先、未设置/坏值回退系统本地
# ---------------------------------------------------------------------------


def test_resolve_user_timezone_prefers_preference(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "settings.json").write_text('{"timezone": "Asia/Tokyo"}', encoding="utf-8")
    resolved = resolve_user_timezone(tmp_path)
    assert getattr(resolved, "key", None) == "Asia/Tokyo"


def test_resolve_user_timezone_falls_back_to_system_local(tmp_path: Path) -> None:
    resolved = resolve_user_timezone(tmp_path)
    assert resolved is not None
    assert resolved.utcoffset(None) == datetime.now().astimezone().utcoffset()
    # 坏值同样回退系统本地（不抛错）。
    config = tmp_path / "config"
    config.mkdir()
    (config / "settings.json").write_text('{"timezone": "Not/AZone"}', encoding="utf-8")
    fallback = resolve_user_timezone(tmp_path)
    assert fallback.utcoffset(None) == datetime.now().astimezone().utcoffset()
