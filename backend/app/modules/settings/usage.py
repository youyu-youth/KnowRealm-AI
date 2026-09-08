"""llm_call_logs 近 30 天只读聚合（设置页"服务与用量"分区数据源）。

覆盖全部埋点调用方（总结 / 知识点 / 习题 / 评分 / Todo / 复习资料 / chat）；
失败行 token_usage 为空 JSON，各 token 口径补 0 但计入调用与失败数。
"""

from datetime import timedelta
from typing import cast

from sqlalchemy import ColumnElement, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.modules.llm.models import LlmCallLog
from app.modules.settings.schemas import (
    LlmUsageDailyPointOut,
    LlmUsageItemOut,
    LlmUsageOut,
)

USAGE_WINDOW_DAYS = 30


def _sum_tokens(path: str) -> ColumnElement[int]:
    # json_extract 无 SQLAlchemy 存根，cast 收口为列表达式，避免 Unknown 污染行类型。
    return cast(
        "ColumnElement[int]",
        func.coalesce(func.sum(func.json_extract(LlmCallLog.token_usage_json, path)), 0),
    )


async def llm_usage(session_factory: async_sessionmaker[AsyncSession]) -> LlmUsageOut:
    # 统计日 = date(created_at)（UTC 存储，与 today 趋势同口径）；缺天后端补零，序列连续无空洞。
    start = utcnow().date() - timedelta(days=USAGE_WINDOW_DAYS - 1)
    total_expr = _sum_tokens("$.total_tokens").label("total_tokens")
    async with session_factory() as session:
        item_rows = (
            await session.execute(
                select(
                    LlmCallLog.model,
                    func.count(),
                    _sum_tokens("$.input_tokens"),
                    _sum_tokens("$.output_tokens"),
                    total_expr,
                    func.count(LlmCallLog.error_code),
                )
                .where(func.date(LlmCallLog.created_at) >= start.isoformat())
                .group_by(LlmCallLog.model)
                .order_by(desc("total_tokens"))
            )
        ).all()
        daily_rows = (
            await session.execute(
                select(
                    func.date(LlmCallLog.created_at),
                    func.count(),
                    _sum_tokens("$.total_tokens"),
                )
                .where(func.date(LlmCallLog.created_at) >= start.isoformat())
                .group_by(func.date(LlmCallLog.created_at))
            )
        ).all()

    items = [
        LlmUsageItemOut(
            model=str(row[0]),
            call_count=int(row[1]),
            input_tokens=int(row[2]),
            output_tokens=int(row[3]),
            total_tokens=int(row[4]),
            error_count=int(row[5]),
        )
        for row in item_rows
    ]
    totals_by_day = {str(day): int(total) for day, _count, total in daily_rows}
    counts_by_day = {str(day): int(count) for day, count, _total in daily_rows}
    daily = [
        LlmUsageDailyPointOut(
            date=(start + timedelta(days=offset)).isoformat(),
            total_tokens=totals_by_day.get((start + timedelta(days=offset)).isoformat(), 0),
            call_count=counts_by_day.get((start + timedelta(days=offset)).isoformat(), 0),
        )
        for offset in range(USAGE_WINDOW_DAYS)
    ]
    return LlmUsageOut(items=items, daily=daily)
