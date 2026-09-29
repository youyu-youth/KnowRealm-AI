"""计划草案的确定性排期器（工单 02，spec「生成、确认与版本语义」）。

日期铺排与预算一致性由确定性校验与修正承担（不超期限、每日总量与
daily_minutes 相容）——脚本优先、LLM 次之：LLM 只产出阶段 / 项序 / 时长 /
理由，日期一律由本排期器按顺序贪心铺排；提交时重算比对，模型转述漂移即
结构化拒绝。纯函数无 IO，黄金样本手算测试（mastery 先例）。
"""

from dataclasses import dataclass
from datetime import date, timedelta

# 目标未填每日投入时的默认日预算（文档化常量：排期仍需一个确定性预算值）。
DEFAULT_DAILY_MINUTES = 120


class ScheduleInfeasible(Exception):
    """草案在期限与预算约束下铺不开（总量超过期限容量）。"""

    def __init__(self, *, required_minutes: int, capacity_minutes: int, deadline: date) -> None:
        super().__init__(f"计划总量 {required_minutes} 分钟超出期限容量 {capacity_minutes} 分钟")
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
    """按顺序贪心铺排：逐项累计当日用量，超出预算即翻日；翻过期限即不可行。

    单项时长超过整日预算时独占一天（项级最小粒度，不拆项）；此时当日总量
    大于预算是显式豁免，下一项从新的一天开始。返回与入参同序的排期日期。
    """
    if constraints.daily_minutes < 1:
        raise ValueError("每日预算必须是正整数")
    if any(value < 1 for value in minutes):
        raise ValueError("计划项时长必须是正整数")
    dates: list[date] = []
    day = constraints.start_date
    used = 0
    for value in minutes:
        if used > 0 and used + value > constraints.daily_minutes:
            day = day + timedelta(days=1)
            used = 0
        if constraints.deadline is not None and day > constraints.deadline:
            raise ScheduleInfeasible(
                required_minutes=sum(minutes),
                capacity_minutes=capacity_minutes(constraints),
                deadline=constraints.deadline,
            )
        dates.append(day)
        used += value
    return dates


def capacity_minutes(constraints: ScheduleConstraints) -> int:
    """期限容量 = 起点到期限（含两端）的天数 × 每日预算；无期限无上限（-1 表意）。"""
    if constraints.deadline is None:
        return -1
    days = (constraints.deadline - constraints.start_date).days + 1
    return max(0, days) * constraints.daily_minutes
