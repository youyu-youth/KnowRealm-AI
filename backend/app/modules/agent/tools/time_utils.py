"""时间工具族共享纯函数助手（Agent 时间能力 v1）。

get_current_time / convert_time / shift_datetime / diff_datetime 四个工具与
system prompt 时间提示行共用的解析、格式化与本地日期锚点逻辑（共享 helper
先例 = tools/listing.py）。全部为无副作用纯函数，可脱离 LLM 单独测试；
时间计算均由 Python 确定性执行，LLM 只负责理解意图与组装参数。
"""

from datetime import date, datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

WEEKDAY_LABELS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")


def timezone_label(tz: tzinfo) -> str:
    """时区展示名：IANA 名优先（ZoneInfo.key），系统本地固定偏移回退 str(tz)。"""
    key = getattr(tz, "key", None)
    if isinstance(key, str):
        return key
    return str(tz)


def local_today() -> date:
    """学习计划铺排的提交日本地锚点：系统本地日期。

    三处消费（generate_learning_plan / regenerate_plan / plan_confirm 校验）
    统一经本函数取锚点保证同源自洽——流外确认链（确认卡端点 → proposal 框架
    → submission_validator）不可达 data_dir，锚点不读偏好时区（时间提示行与
    时间工具默认时区才读，见 settings.config.resolve_user_timezone）；默认
    用户（timezone=null）两口径一致，显式设置跨时区的差异为已知边界。
    """
    return datetime.now().astimezone().date()


def parse_datetime_arg(value: str, default_tz: tzinfo) -> datetime:
    """解析工具入参的 ISO 8601 时间；naive 输入按 default_tz aware 化。

    值无效（非 ISO 格式）抛 ValueError，由工具转 ok=false 载荷。
    """
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=default_tz)
    return parsed


def resolve_timezone_arg(name: str) -> tzinfo:
    """解析 IANA 时区名入参；无效名抛 ValueError（工具转 ok=false 载荷）。"""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"无法识别的时区名：{name}（须为 IANA 名，如 Asia/Shanghai）") from exc


def weekday_label(value: date) -> str:
    return WEEKDAY_LABELS[value.weekday()]


def format_time_hint(now: datetime) -> str:
    """时间提示行：随消息每轮重建注入 system prompt（页面提示同款，不落库）。"""
    return (
        "时间提示：当前时间 "
        f"{now.strftime('%Y-%m-%d %H:%M:%S')}"
        f"（{weekday_label(now.date())}，{timezone_label(now.tzinfo)}）。"
        "本行是本轮消息组装时刻的快照；回答需要当下精确时间或时区换算时，"
        "调用 get_current_time 等时间工具获取。"
    )


def time_payload(dt: datetime) -> dict[str, object]:
    """时间工具统一返回的单时刻投影（aware datetime）。"""
    offset = dt.strftime("%z")
    return {
        "datetime": dt.isoformat(timespec="seconds"),
        "date": dt.strftime("%Y-%m-%d"),
        "time": dt.strftime("%H:%M:%S"),
        "weekday": weekday_label(dt.date()),
        "timezone": timezone_label(dt.tzinfo),
        "utc_offset": f"{offset[:3]}:{offset[3:]}" if offset else "+00:00",
    }
