"""计划草案的确定性排期器（工单 02，spec「生成、确认与版本语义」）。

日期铺排与预算一致性由确定性校验与修正承担（不超期限、每日总量与
daily_minutes 相容）——脚本优先、LLM 次之：LLM 只产出阶段 / 项序 / 时长 /
理由，日期一律由本排期器按顺序贪心铺排；提交时重算比对，模型转述漂移即
结构化拒绝。纯函数无 IO，黄金样本手算测试（mastery 先例）。
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

# 目标未填每日投入时的默认日预算（文档化常量：排期仍需一个确定性预算值）。
DEFAULT_DAILY_MINUTES = 120


def local_today() -> date:
    """学习计划日期语义的本地锚点：系统本地日期。

    铺排（生成 / 重生成）、提交校验与今日待学查询（scheduled_date ≤ 今天）
    统一经本函数取锚点保证同源自洽——今日端点在 today 模块（agent/today 均
    下游），锚点落领域侧供两侧共用；默认用户（timezone=null）与偏好时区两
    口径一致，显式设置跨时区的差异为已知边界。
    """
    return datetime.now().astimezone().date()


class ScheduleInfeasible(Exception):
    """草案在期限与预算约束下铺不开（总量超期限容量 / 单项超每日预算）。"""

    def __init__(
        self,
        *,
        required_minutes: int,
        capacity_minutes: int,
        deadline: date,
        detail: str | None = None,
    ) -> None:
        super().__init__(
            detail or f"计划总量 {required_minutes} 分钟超出期限容量 {capacity_minutes} 分钟"
        )
        self.required_minutes = required_minutes
        self.capacity_minutes = capacity_minutes
        self.deadline = deadline


@dataclass(frozen=True)
class ScheduleConstraints:
    """排期约束：起点（今日）、期限（可空）、每日预算（目标值或默认值）。"""

    start_date: date
    deadline: date | None = None
    daily_minutes: int = DEFAULT_DAILY_MINUTES


def pack_schedule(minutes: list[int], constraints: ScheduleConstraints) -> list[date]:
    """按顺序贪心铺排（无锁定占用的薄包装，行为与工单 02 逐位一致）。"""
    return pack_schedule_with_fixed(minutes, [], constraints)


def pack_schedule_with_fixed(
    minutes: list[int],
    fixed: list[tuple[date, int]],
    constraints: ScheduleConstraints,
) -> list[date]:
    """带锁定占用的顺序贪心铺排（工单 03 重生成）：fixed 是原样带入的锁定项
    （日期 + 时长），草案项在「每日预算 − 当日锁定占用」的剩余容量内按顺序
    铺排；翻过期限即不可行（锁定项自身不受期限约束——已定事实原样保留）。

    单项时长超过每日预算时直接判不可行：计划项不跨日拆分，任何铺排都无法
    让当日总量与 daily_minutes 相容（spec「每日总量与 daily_minutes 相容」）。
    返回与入参 minutes 同序的排期日期。
    """
    if constraints.daily_minutes < 1:
        raise ValueError("每日预算必须是正整数")
    if any(value < 1 for value in minutes):
        raise ValueError("计划项时长必须是正整数")
    over = next((value for value in minutes if value > constraints.daily_minutes), None)
    if over is not None:
        raise ScheduleInfeasible(
            required_minutes=over,
            capacity_minutes=constraints.daily_minutes,
            deadline=constraints.deadline or constraints.start_date,
            detail=(
                f"单项时长 {over} 分钟超过每日预算 {constraints.daily_minutes} 分钟"
                "（计划项不跨日拆分），请拆分计划项或调整时长"
            ),
        )
    usage: dict[date, int] = {}
    locked_total = 0
    for day, value in fixed:
        usage[day] = usage.get(day, 0) + value
        locked_total += value
    dates: list[date] = []
    day = constraints.start_date
    for value in minutes:
        while value > constraints.daily_minutes - usage.get(day, 0):
            day = day + timedelta(days=1)
            if constraints.deadline is not None and day > constraints.deadline:
                # 容量诊断只扣锁定占用（草案已放置部分不是容量减项）。
                raise ScheduleInfeasible(
                    required_minutes=sum(minutes),
                    capacity_minutes=capacity_minutes(constraints) - locked_total,
                    deadline=constraints.deadline,
                )
        dates.append(day)
        usage[day] = usage.get(day, 0) + value
    return dates


def capacity_minutes(constraints: ScheduleConstraints) -> int:
    """期限容量 = 起点到期限（含两端）的天数 × 每日预算；无期限无上限（-1 表意）。"""
    if constraints.deadline is None:
        return -1
    days = (constraints.deadline - constraints.start_date).days + 1
    return max(0, days) * constraints.daily_minutes
