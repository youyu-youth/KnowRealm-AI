"""Mastery Engine（唯一写入口）与课程 Mastery 只读查询。

确定性全量重算：从有效 Quiz Evidence 重建 Concept 快照，失败重试后记录结构化
错误、不影响上游 Event/Evidence 与其余概念；查询只聚合活跃 CONFIRMED Concept。
本模块不调用 LLM、不读墙钟时间（除写入 updated_at）。
"""

from collections.abc import Collection
from typing import cast
from uuid import uuid4

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.modules.course.models import Course
from app.modules.course_brain.models import Concept
from app.modules.course_brain.schemas import ConceptStatus
from app.modules.learning.mastery import (
    ALGORITHM_VERSION,
    MasteryEvidence,
    MasteryStatus,
    classify_status,
    compute_mastery,
    confidence_level_of,
)
from app.modules.learning.models import LearningEvidence, UserConceptMastery
from app.modules.learning.schemas import (
    ConceptMasteryOut,
    CourseMasteryOut,
    MasteryStatusCountsOut,
)
from app.modules.record.models import LearningEvent, Record
from app.shared.errors import CodedHTTPException

MAX_RECOMPUTE_ATTEMPTS = 3
QUIZ_EVIDENCE_TYPE = "QUIZ"

# 默认排序优先级：需要关注的状态在前，稳定项靠后（spec Desktop 体验）。
_STATUS_PRIORITY = {
    MasteryStatus.WEAK: 0,
    MasteryStatus.LEARNING: 1,
    MasteryStatus.NOT_ENOUGH_DATA: 2,
    MasteryStatus.STABLE: 3,
}


async def _load_effective_evidence(
    session: AsyncSession, concept: Concept
) -> list[MasteryEvidence]:
    """有效集合：同课程、带分数、类型为 QUIZ，且宿主 Record 未软删除。"""
    rows = (
        await session.scalars(
            select(LearningEvidence)
            .join(LearningEvent, LearningEvidence.event_id == LearningEvent.id)
            .join(Record, Record.id == LearningEvent.record_id)
            .where(
                LearningEvidence.concept_id == concept.id,
                LearningEvidence.course_id == concept.course_id,
                LearningEvidence.evidence_type == QUIZ_EVIDENCE_TYPE,
                LearningEvidence.score.is_not(None),
                Record.deleted_at.is_(None),
            )
        )
    ).all()
    return [
        MasteryEvidence(
            evidence_id=row.id,
            score=cast(float, row.score),
            weight=row.weight,
            confidence=row.confidence,
            result=row.result,
            occurred_at=row.occurred_at,
        )
        for row in rows
    ]


async def _recompute_concept(
    session_factory: async_sessionmaker[AsyncSession], concept_id: str
) -> None:
    """单个 Concept 全量重算（读写一个短事务）：归档/候选概念不改动历史快照。"""
    async with session_factory() as session, session.begin():
        concept = await session.get(Concept, concept_id)
        if concept is None or concept.status != ConceptStatus.CONFIRMED.value:
            return
        result = compute_mastery(await _load_effective_evidence(session, concept))
        snapshot = (
            await session.scalars(
                select(UserConceptMastery).where(UserConceptMastery.concept_id == concept_id)
            )
        ).one_or_none()
        now = utcnow()
        if snapshot is None:
            snapshot = UserConceptMastery(
                id=str(uuid4()),
                concept_id=concept_id,
                course_id=concept.course_id,
                algorithm_version=ALGORITHM_VERSION,
                updated_at=now,
            )
            session.add(snapshot)
        snapshot.course_id = concept.course_id
        snapshot.mastery_score = result.score
        snapshot.mastery_confidence = result.confidence_value
        snapshot.evidence_count = result.evidence_count
        snapshot.positive_evidence_count = result.positive_evidence_count
        snapshot.negative_evidence_count = result.negative_evidence_count
        snapshot.last_practiced_at = result.last_practiced_at
        snapshot.last_verified_at = result.last_verified_at
        snapshot.algorithm_version = ALGORITHM_VERSION
        snapshot.updated_at = now


def _concept_mastery_out(
    concept: Concept, snapshot: UserConceptMastery | None
) -> ConceptMasteryOut:
    score = snapshot.mastery_score if snapshot is not None else None
    confidence_value = snapshot.mastery_confidence if snapshot is not None else None
    return ConceptMasteryOut(
        concept_id=concept.id,
        canonical_name=concept.canonical_name,
        description=concept.description,
        concept_type=concept.concept_type,
        importance=concept.importance,
        status=classify_status(score, confidence_value),
        mastery_score=score,
        confidence=(
            confidence_level_of(confidence_value) if confidence_value is not None else None
        ),
        evidence_count=snapshot.evidence_count if snapshot is not None else 0,
        positive_evidence_count=(snapshot.positive_evidence_count if snapshot is not None else 0),
        negative_evidence_count=(snapshot.negative_evidence_count if snapshot is not None else 0),
        last_practiced_at=snapshot.last_practiced_at if snapshot is not None else None,
        last_verified_at=snapshot.last_verified_at if snapshot is not None else None,
    )


async def _get_course(session: AsyncSession, course_id: str) -> Course:
    course = (
        await session.scalars(
            select(Course).where(Course.id == course_id, Course.deleted_at.is_(None))
        )
    ).one_or_none()
    if course is None:
        raise CodedHTTPException(
            code="COURSE_NOT_FOUND", status_code=404, detail="课程不存在或已删除"
        )
    return course


class MasteryService:
    @staticmethod
    async def recompute_concepts(
        session_factory: async_sessionmaker[AsyncSession], concept_ids: Collection[str]
    ) -> int:
        """按 Concept 全量重算；单点失败重试后记结构化错误，不阻塞其余概念。"""
        succeeded = 0
        for concept_id in sorted(set(concept_ids)):
            last_error: Exception | None = None
            for _attempt in range(MAX_RECOMPUTE_ATTEMPTS):
                try:
                    await _recompute_concept(session_factory, concept_id)
                    succeeded += 1
                    break
                except Exception as exc:
                    last_error = exc
            else:
                logger.error(
                    "mastery_recompute_failed",
                    error_code="MASTERY_RECOMPUTE_FAILED",
                    concept_id=concept_id,
                    error=repr(last_error),
                )
        return succeeded

    @staticmethod
    async def list_course_mastery(
        session: AsyncSession,
        course_id: str,
        status_filter: MasteryStatus | None = None,
    ) -> CourseMasteryOut:
        await _get_course(session, course_id)
        concepts = (
            await session.scalars(
                select(Concept).where(
                    Concept.course_id == course_id,
                    Concept.status == ConceptStatus.CONFIRMED.value,
                )
            )
        ).all()
        snapshots = {
            snapshot.concept_id: snapshot
            for snapshot in (
                await session.scalars(
                    select(UserConceptMastery).where(UserConceptMastery.course_id == course_id)
                )
            ).all()
        }
        rows = [_concept_mastery_out(concept, snapshots.get(concept.id)) for concept in concepts]
        verified_count = sum(1 for row in rows if row.evidence_count > 0)
        ordered = sorted(
            rows,
            key=lambda row: (
                _STATUS_PRIORITY[row.status],
                -row.importance,
                row.canonical_name,
                row.concept_id,
            ),
        )
        return CourseMasteryOut(
            course_id=course_id,
            confirmed_concept_count=len(rows),
            verified_concept_count=verified_count,
            coverage=verified_count / len(rows) if rows else 0.0,
            status_counts=MasteryStatusCountsOut(
                not_enough_data=sum(
                    1 for row in rows if row.status is MasteryStatus.NOT_ENOUGH_DATA
                ),
                weak=sum(1 for row in rows if row.status is MasteryStatus.WEAK),
                learning=sum(1 for row in rows if row.status is MasteryStatus.LEARNING),
                stable=sum(1 for row in rows if row.status is MasteryStatus.STABLE),
            ),
            concepts=[
                row for row in ordered if status_filter is None or row.status is status_filter
            ],
        )
