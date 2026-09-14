"""learning 域薄只读查询：按记录/课程取证据流。

无服务层抽象、无 API 暴露（spec 既定）——未来 Mastery Engine、agent 学习
上下文中间件与统计的共同底座（spec 用户故事 17/18）。
"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.learning.models import LearningEvidence
from app.modules.record.models import LearningEvent


async def list_evidence_by_record(
    session: AsyncSession, *, record_id: str
) -> Sequence[LearningEvidence]:
    """按记录取证据：证据表无 record_id 列，经 event 关联；时间升序证据流。"""
    stmt = (
        select(LearningEvidence)
        .join(LearningEvent, LearningEvidence.event_id == LearningEvent.id)
        .where(LearningEvent.record_id == record_id)
        .order_by(LearningEvidence.occurred_at, LearningEvidence.event_id)
    )
    return (await session.scalars(stmt)).all()


async def list_evidence_by_course(
    session: AsyncSession, *, course_id: str
) -> Sequence[LearningEvidence]:
    """按课程取证据：course_id 直落在证据行；时间升序证据流。"""
    stmt = (
        select(LearningEvidence)
        .where(LearningEvidence.course_id == course_id)
        .order_by(LearningEvidence.occurred_at, LearningEvidence.event_id)
    )
    return (await session.scalars(stmt)).all()
