"""学习事件统一写入入口：业务事务内落行，幂等键冲突静默跳过。"""

import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.record.models import LearningEvent

EVENT_SCHEMA_VERSION = 1


async def write_learning_event(
    session: AsyncSession,
    *,
    course_id: str,
    event_type: str,
    source_type: str,
    source_id: str,
    idempotency_key: str,
    occurred_at: datetime,
    metadata: dict[str, object],
    record_id: str | None = None,
    result: str | None = None,
    score: float | None = None,
    difficulty: str | None = None,
    duration_ms: int | None = None,
    created_at: datetime | None = None,
) -> None:
    """在调用方的业务事务会话内写入一条学习事件；幂等键已存在时静默跳过。

    会话复用红线（spec）：必须传入业务动作所在的同一事务会话，禁止独立
    连接写事件——否则崩溃窗口会出现动作成功而事件丢失。
    """
    existing = await session.scalar(
        select(LearningEvent.id).where(LearningEvent.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return
    session.add(
        LearningEvent(
            id=str(uuid4()),
            course_id=course_id,
            record_id=record_id,
            concept_id=None,
            event_type=event_type,
            source_type=source_type,
            source_id=source_id,
            result=result,
            score=score,
            difficulty=difficulty,
            duration_ms=duration_ms,
            metadata_json=json.dumps(metadata, separators=(",", ":")),
            idempotency_key=idempotency_key,
            schema_version=EVENT_SCHEMA_VERSION,
            occurred_at=occurred_at,
            created_at=created_at or occurred_at,
        )
    )
    await session.flush()
