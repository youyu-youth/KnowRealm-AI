"""学习事件消费循环（ADR-0021）：独立 asyncio 后台任务，单调水位扫描把
learning_events 确定性转换为 learning_evidence。零 LLM、不入 processing_jobs
（毫秒级纯函数转换，领取三态协议对其是过度设计）；证据可由事件流重放再生。
"""

import asyncio
from dataclasses import dataclass
from typing import cast

from loguru import logger
from sqlalchemy import ColumnElement, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.learning.models import LearningEvidence
from app.modules.learning.service import MasteryService
from app.modules.record.models import LearningEvent

MAX_CONVERSION_ATTEMPTS = 3


@dataclass(frozen=True)
class EvidenceMapping:
    evidence_type: str
    weight: float
    confidence: float


# 映射规则集中声明（spec Q3）：数值为 Mastery 域调参初值，非产品语义承诺。
# QUIZ_TEST_COMPLETED 不产证据：逐题已产，双计规避（ADR-0021）；
# 未收录的事件类型一律静默跳过、水位照常推进。
EVIDENCE_MAPPINGS: dict[str, EvidenceMapping] = {
    "QUIZ_ANSWERED": EvidenceMapping(evidence_type="QUIZ", weight=0.9, confidence=0.8),
    "SUMMARY_CONFIRMED": EvidenceMapping(
        evidence_type="USER_CONFIRMATION", weight=0.3, confidence=0.7
    ),
    "KNOWLEDGE_CONFIRMED": EvidenceMapping(
        evidence_type="USER_CONFIRMATION", weight=0.4, confidence=0.7
    ),
}


class EvidenceConsumer:
    """learning_events → learning_evidence 的独立水位消费循环。

    learning_events.id 是 uuid4（非单调），水位落在追加型表的隐式 rowid 上
    （严格递增、走表 b-tree，ADR-0021「单调 id 走索引」）；水位仅存内存，
    崩溃重启从头全量补扫，event_id 唯一约束天然去重。
    """

    POLL_INTERVAL_SECONDS = 30.0

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._stopped = asyncio.Event()
        self._watermark = 0
        self.failed_conversion_count = 0

    def stop(self) -> None:
        self._stopped.set()

    async def run(self) -> None:
        while not self._stopped.is_set():
            try:
                await self.run_once()
            except Exception:
                # 整轮失败（如库暂不可用）不杀死循环：下轮重扫，行级失败在行内消化。
                logger.error(
                    "evidence_consumption_cycle_failed", error_code="EVIDENCE_CONSUME_FAILED"
                )
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self.POLL_INTERVAL_SECONDS)
            except TimeoutError:
                pass

    async def run_once(self) -> int:
        """单轮执行（测试接缝）：水位之上逐条转换落证据，返回本轮处理事件条数。

        计数含不产证据的未映射事件——它们同样被消费（推进水位）。证据成功
        持久化后收拢受影响 Concept，由 Mastery Engine 异步全量重算（票 02）。
        """
        # rowid 是追加型表的单调键；literal_column 收窄为整型列以供 select 类型解析。
        rowid_column = cast("ColumnElement[int]", literal_column("rowid"))
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(LearningEvent, rowid_column)
                    .where(rowid_column > self._watermark)
                    .order_by(rowid_column)
                )
            ).all()
        processed = 0
        affected_concepts: set[str] = set()
        for event, rowid in rows:
            affected = await self._convert_with_retry(event)
            if affected is not None:
                affected_concepts.add(affected)
            self._watermark = rowid
            processed += 1
        if affected_concepts:
            # 派生快照单独重算与重试：失败不回滚已落证据，也不阻塞下一轮水位。
            await MasteryService.recompute_concepts(self._session_factory, affected_concepts)
        return processed

    async def _convert_with_retry(self, event: LearningEvent) -> str | None:
        mapping = EVIDENCE_MAPPINGS.get(event.event_type)
        if mapping is None:
            return None
        last_error: Exception | None = None
        for _attempt in range(MAX_CONVERSION_ATTEMPTS):
            try:
                return await self._insert_evidence(event, mapping)
            except Exception as exc:
                last_error = exc
        # 不建死信表、不阻塞水位：个别行缺失非灾难，清空证据表全量重放即修复。
        self.failed_conversion_count += 1
        logger.error(
            "evidence_conversion_failed",
            error_code="EVIDENCE_CONVERSION_FAILED",
            event_id=event.id,
            error=repr(last_error),
        )
        return None

    async def _insert_evidence(self, event: LearningEvent, mapping: EvidenceMapping) -> str | None:
        """落一条证据并返回其 Concept 归属（未归属/已存在时为 None）。"""
        async with self._session_factory() as session, session.begin():
            existing = await session.scalar(
                select(LearningEvidence.id).where(LearningEvidence.event_id == event.id)
            )
            if existing is not None:
                return None
            session.add(
                LearningEvidence(
                    course_id=event.course_id,
                    # Event 中已固化的 Concept 原样复制；禁止重放时回查 record_concepts 推导。
                    concept_id=event.concept_id,
                    event_id=event.id,
                    evidence_type=mapping.evidence_type,
                    result=event.result,
                    score=event.score,
                    difficulty=event.difficulty,
                    weight=mapping.weight,
                    confidence=mapping.confidence,
                    source_anchor_id=None,
                    metadata_json=event.metadata_json,
                    occurred_at=event.occurred_at,
                )
            )
        return event.concept_id
