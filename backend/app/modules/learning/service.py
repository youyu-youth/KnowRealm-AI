"""Mastery Engine（唯一写入口）与课程 Mastery 只读查询。

确定性全量重算：从有效 Quiz Evidence 重建 Concept 快照，失败重试后记录结构化
错误、不影响上游 Event/Evidence 与其余概念；查询只聚合活跃 CONFIRMED Concept。
本模块不调用 LLM、不读墙钟时间（除写入 updated_at）。
"""

import asyncio
import json
from collections.abc import Callable, Collection
from typing import NamedTuple, cast
from uuid import uuid4

from loguru import logger
from sqlalchemy import event, select, update
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
    window_evidence,
)
from app.modules.learning.models import LearningEvidence, UserConceptMastery
from app.modules.learning.schemas import (
    ConceptMasteryDetailOut,
    ConceptMasteryOut,
    CourseMasteryOut,
    MasteryEvidenceOut,
    MasteryQuizSourceOut,
    MasteryStatusCountsOut,
    MasteryTestSourceOut,
)
from app.modules.record.models import LearningEvent, Record
from app.shared.errors import CodedHTTPException

MAX_RECOMPUTE_ATTEMPTS = 3
QUIZ_EVIDENCE_TYPE = "QUIZ"
# 重算彻底失败时钉在快照 algorithm_version 上的哨兵值：重启恢复按「版本不匹配」
# 重建；重算成功会重写真实版本号，自愈自清。快照尚不存在时无需标记（缺失即锚点）。
STALE_VERSION_MARKER = "stale"

# 默认排序优先级：需要关注的状态在前，稳定项靠后（spec Desktop 体验）。
_STATUS_PRIORITY = {
    MasteryStatus.WEAK: 0,
    MasteryStatus.LEARNING: 1,
    MasteryStatus.NOT_ENOUGH_DATA: 2,
    MasteryStatus.STABLE: 3,
}


class EffectiveEvidenceRow(NamedTuple):
    """有效集合单行：Evidence + 固化归属的 Event + 宿主 Record 标题（无宿主为 None）。"""

    evidence: LearningEvidence
    event: LearningEvent
    record_title: str | None


async def _load_effective_evidence_rows(
    session: AsyncSession, concept: Concept
) -> list[EffectiveEvidenceRow]:
    """有效集合原始行（重算与详情共用同一过滤）：同课程、带分数、类型为 QUIZ。

    Record 走 LEFT JOIN：模拟测试逐题事件无 Record 归属，照样参与；宿主 Record
    已软删除的才被排除（spec：历史行保留，只退出有效集合）。
    """
    rows = (
        await session.execute(
            select(LearningEvidence, LearningEvent, Record.title)
            .join(LearningEvent, LearningEvidence.event_id == LearningEvent.id)
            .outerjoin(Record, Record.id == LearningEvent.record_id)
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
        EffectiveEvidenceRow(evidence=row, event=event, record_title=title)
        for row, event, title in rows
    ]


def _to_mastery_evidence(row: LearningEvidence) -> MasteryEvidence:
    return MasteryEvidence(
        evidence_id=row.id,
        score=cast(float, row.score),
        weight=row.weight,
        confidence=row.confidence,
        result=row.result,
        occurred_at=row.occurred_at,
    )


async def _load_effective_evidence(
    session: AsyncSession, concept: Concept
) -> list[MasteryEvidence]:
    """有效集合的算法输入形式。"""
    return [
        _to_mastery_evidence(item.evidence)
        for item in await _load_effective_evidence_rows(session, concept)
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


def _evidence_source(
    event: LearningEvent, record_title: str | None
) -> MasteryQuizSourceOut | MasteryTestSourceOut | None:
    """业务来源定位：metadata 带 test_id 为模拟测试逐题，否则按宿主 Record 定位。

    两类事件 source_type 均为 QUIZ_QUESTION（quiz 域写入口径），区分只能靠
    Event 固化的 metadata；定位能力不足时返回 None，前端只展示时间。
    """
    metadata: dict[str, object] = json.loads(event.metadata_json) if event.metadata_json else {}
    test_id = metadata.get("test_id")
    if isinstance(test_id, str) and test_id:
        sequence_no = metadata.get("sequence_no")
        return MasteryTestSourceOut(
            source_type="QUIZ_TEST",
            test_id=test_id,
            sequence_no=sequence_no if isinstance(sequence_no, int) else None,
        )
    if event.record_id is not None and record_title is not None:
        return MasteryQuizSourceOut(
            source_type="QUIZ",
            record_id=event.record_id,
            record_title=record_title,
            quiz_id=event.source_id,
        )
    return None


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


async def _mark_snapshot_stale(
    session_factory: async_sessionmaker[AsyncSession], concept_id: str
) -> None:
    """把既有快照钉上 stale 哨兵（best-effort）：标记写失败只记日志，不影响主流程。"""
    try:
        async with session_factory() as session, session.begin():
            await session.execute(
                update(UserConceptMastery)
                .where(UserConceptMastery.concept_id == concept_id)
                .values(algorithm_version=STALE_VERSION_MARKER)
            )
    except Exception as exc:
        logger.error(
            "mastery_stale_mark_failed",
            error_code="MASTERY_STALE_MARK_FAILED",
            concept_id=concept_id,
            error=repr(exc),
        )


class MasteryService:
    @staticmethod
    async def recompute_concepts(
        session_factory: async_sessionmaker[AsyncSession], concept_ids: Collection[str]
    ) -> set[str]:
        """按 Concept 全量重算；单点失败重试后记错误、标 stale 哨兵并收入返回的失败集合。

        失败集合交调用方安排重试（如 consumer 的内存 pending）；不阻塞其余概念。
        """
        failed: set[str] = set()
        for concept_id in sorted(set(concept_ids)):
            last_error: Exception | None = None
            for _attempt in range(MAX_RECOMPUTE_ATTEMPTS):
                try:
                    await _recompute_concept(session_factory, concept_id)
                    break
                except Exception as exc:
                    last_error = exc
            else:
                failed.add(concept_id)
                logger.error(
                    "mastery_recompute_failed",
                    error_code="MASTERY_RECOMPUTE_FAILED",
                    concept_id=concept_id,
                    error=repr(last_error),
                )
                await _mark_snapshot_stale(session_factory, concept_id)
        return failed

    @staticmethod
    def schedule_recompute_after_commit(
        session: AsyncSession,
        concept_ids: Collection[str],
        *,
        schedule_retry: Callable[[Collection[str]], None] | None = None,
    ) -> "list[asyncio.Task[None]]":
        """把掌握度重算登记为事务提交后动作（删除路径共用，工单 04，spec 决策 15）。

        重算必须读已提交状态：删除事务持写锁时并发新会话会读到旧态（或撞
        SQLITE_BUSY），经 after_commit 挂钩在提交时调度后台任务——回滚则不触发
        （未发生＝无需重算），闭包标志位保证同一会话后续提交不重复触发。
        重算会话由 session.bind 派生（同引擎连接池；Agent 确认路径无 app.state
        句柄）。schedule_retry 为 None 时（Agent 路径）失败概念由重算内置的
        stale 哨兵交启动恢复闭环；HTTP 路径传 consumer.schedule_recompute
        获得 ≤30s 进程内自愈。

        返回任务接收容器（提交后由挂钩填入）：需要同步等待重算完成的调用方
        （HTTP 删除路由的既有语义）在事务提交后 await 容器元素；后台执行的
        调用方（Agent 确认路径）忽略即可。
        """
        if not concept_ids:
            return []
        recompute_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=session.bind, expire_on_commit=False
        )
        retry = schedule_retry
        tasks: list[asyncio.Task[None]] = []

        async def _run() -> None:
            failed = await MasteryService.recompute_concepts(recompute_factory, set(concept_ids))
            if failed and retry is not None:
                retry(failed)

        scheduled = False

        def _fire(_: object) -> None:
            nonlocal scheduled
            if scheduled:
                return
            scheduled = True
            tasks.append(asyncio.get_running_loop().create_task(_run()))

        event.listen(session.sync_session, "after_commit", _fire)
        return tasks

    @staticmethod
    async def recover_snapshots(
        session_factory: async_sessionmaker[AsyncSession],
    ) -> set[str]:
        """启动恢复：快照缺失、算法版本过期或失败标记（stale）的 CONFIRMED 概念全量重算（幂等）。

        版本一致且已有快照的概念直接跳过——重复调用、应用重启零写入；
        版本升级因此只需要 bump ``ALGORITHM_VERSION``，启动即全量重建。
        返回仍失败的概念集合，交调用方安排重试。
        """
        async with session_factory() as session:
            concept_ids = list(
                (
                    await session.scalars(
                        select(Concept.id).where(Concept.status == ConceptStatus.CONFIRMED.value)
                    )
                ).all()
            )
            snapshots = {
                snapshot.concept_id: snapshot.algorithm_version
                for snapshot in (await session.scalars(select(UserConceptMastery))).all()
            }
        stale = [
            concept_id
            for concept_id in concept_ids
            if snapshots.get(concept_id) != ALGORITHM_VERSION
        ]
        return await MasteryService.recompute_concepts(session_factory, stale)

    @staticmethod
    async def get_concept_mastery(
        session: AsyncSession, course_id: str, concept_id: str
    ) -> ConceptMasteryDetailOut:
        """Concept Mastery 只读详情：快照 + 窗口内有效 Evidence（无快照不 404）。"""
        await _get_course(session, course_id)
        concept = (
            await session.scalars(
                select(Concept).where(Concept.id == concept_id, Concept.course_id == course_id)
            )
        ).one_or_none()
        # 仅活跃 CONFIRMED 可查（spec：归档退出活跃查询，历史快照保留在库供审计）。
        if concept is None or concept.status != ConceptStatus.CONFIRMED.value:
            raise CodedHTTPException(
                code="COURSE_BRAIN_CONCEPT_NOT_FOUND", status_code=404, detail="概念不存在"
            )
        snapshot = (
            await session.scalars(
                select(UserConceptMastery).where(UserConceptMastery.concept_id == concept_id)
            )
        ).one_or_none()
        rows = await _load_effective_evidence_rows(session, concept)
        windowed = window_evidence([_to_mastery_evidence(item.evidence) for item in rows])
        rows_by_id = {item.evidence.id: item for item in rows}
        evidences: list[MasteryEvidenceOut] = []
        for item in windowed:
            row = rows_by_id[item.evidence_id]
            evidences.append(
                MasteryEvidenceOut(
                    evidence_id=item.evidence_id,
                    score=item.score,
                    result=item.result,
                    occurred_at=item.occurred_at,
                    source=_evidence_source(row.event, row.record_title),
                )
            )
        return ConceptMasteryDetailOut(
            snapshot=_concept_mastery_out(concept, snapshot),
            algorithm_version=(
                snapshot.algorithm_version if snapshot is not None else ALGORITHM_VERSION
            ),
            evidences=evidences,
        )

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
