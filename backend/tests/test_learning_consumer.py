"""学习事件消费循环（票 03）：水位扫描逐条转换、确定性映射表、重扫幂等去重、
全量重放重建、失败 3 次跳过与水位推进、lifespan 接线。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import create_database
from app.db.migrations import run_migrations
from app.main import create_app
from app.modules.learning.consumer import EvidenceConsumer, EvidenceMapping
from app.modules.learning.events import write_learning_event
from app.modules.record.models import LearningEvent

TOKEN = "test-launch-token"
OCCURRED = datetime(2026, 9, 14, 8, 0, 0)
OCCURRED_TEXT = "2026-09-14T08:00:00.000000Z"


async def seed_event(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    idempotency_key: str,
    event_type: str,
    result: str | None = None,
    score: float | None = None,
    difficulty: str | None = None,
    metadata: dict[str, object] | None = None,
    record_id: str | None = None,
    concept_id: str | None = None,
) -> str:
    """经统一写入函数落一条学习事件，返回事件 id（消费断言坐标）。"""
    async with session_factory() as session, session.begin():
        await write_learning_event(
            session,
            course_id="course-1",
            event_type=event_type,
            source_type="TEST_SOURCE",
            source_id=idempotency_key,
            idempotency_key=idempotency_key,
            occurred_at=OCCURRED,
            metadata=metadata if metadata is not None else {},
            result=result,
            score=score,
            difficulty=difficulty,
            record_id=record_id,
            concept_id=concept_id,
        )
        event_id = await session.scalar(
            select(LearningEvent.id).where(LearningEvent.idempotency_key == idempotency_key)
        )
    return cast(str, event_id)


async def seed_mastery_subject(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    course_id: str = "course-1",
    record_id: str = "record-1",
    concept_id: str = "concept-1",
) -> None:
    """种课程 / 未删除记录 / 已确认概念：Mastery 重算的完整前置。"""
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO courses (id, name, learning_context, education_stage, depth, "
                "course_type, description, hot_words, status, created_at, updated_at, deleted_at) "
                "VALUES (:course_id, '操作系统', 'SCHOOL', 'UNDERGRADUATE', NULL, NULL, NULL, "
                "'[]', 'ACTIVE', :now, :now, NULL)"
            ),
            {"course_id": course_id, "now": OCCURRED_TEXT},
        )
        await session.execute(
            text(
                "INSERT INTO records (id, course_id, capture_type, title, status, duration_ms, "
                "summary_confirmed_at, created_at, updated_at, deleted_at) "
                "VALUES (:record_id, :course_id, 'DOCUMENT_IMPORT', '进程调度', 'COMPLETED', 0, "
                ":now, :now, :now, NULL)"
            ),
            {"record_id": record_id, "course_id": course_id, "now": OCCURRED_TEXT},
        )
        await session.execute(
            text(
                "INSERT INTO concepts (id, course_id, canonical_name, normalized_name, "
                "description, concept_type, importance, status, source, created_at, updated_at) "
                "VALUES (:concept_id, :course_id, '进程调度', '进程调度', '', 'TERM', 3, "
                "'CONFIRMED', 'AI_EXTRACTED', :now, :now)"
            ),
            {"concept_id": concept_id, "course_id": course_id, "now": OCCURRED_TEXT},
        )


async def fetch_mastery(
    session_factory: async_sessionmaker[AsyncSession], concept_id: str
) -> dict[str, object] | None:
    async with session_factory() as session:
        row = (
            (
                await session.execute(
                    text(
                        "SELECT mastery_score, mastery_confidence, evidence_count, "
                        "algorithm_version FROM user_concept_mastery "
                        "WHERE concept_id = :concept_id"
                    ),
                    {"concept_id": concept_id},
                )
            )
            .mappings()
            .one_or_none()
        )
    return None if row is None else dict(row)


async def fetch_evidence(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[dict[str, object]]:
    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT event_id, evidence_type, result, score, difficulty, weight, "
                        "confidence, course_id, concept_id, source_anchor_id, metadata_json, "
                        "occurred_at FROM learning_evidence ORDER BY event_id"
                    )
                )
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


@pytest.mark.anyio
async def test_run_once_maps_events_per_mapping_table(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    _engine, session_factory = create_database(db_path)
    quiz_id = await seed_event(
        session_factory,
        idempotency_key="quiz-answered:quiz-1",
        event_type="QUIZ_ANSWERED",
        result="CORRECT",
        score=1.0,
        difficulty="HARD",
        metadata={"question_type": "MULTIPLE_CHOICE", "batch_id": "batch-1"},
    )
    test_item_id = await seed_event(
        session_factory,
        idempotency_key="quiz-answered:test:item-1",
        event_type="QUIZ_ANSWERED",
        result="PARTIAL",
        score=0.6,
        difficulty="MEDIUM",
        metadata={"test_id": "test-1", "sequence_no": 2},
    )
    summary_id = await seed_event(
        session_factory,
        idempotency_key="summary-confirmed:s-1",
        event_type="SUMMARY_CONFIRMED",
        metadata={"summary_version_no": 1},
    )
    batch_id = await seed_event(
        session_factory,
        idempotency_key="knowledge-confirmed:b-1",
        event_type="KNOWLEDGE_CONFIRMED",
        metadata={"batch_id": "b-1", "confirmed_count": 3},
    )
    completed_id = await seed_event(
        session_factory,
        idempotency_key="quiz-test-completed:t-1",
        event_type="QUIZ_TEST_COMPLETED",
        score=0.5,
        metadata={"question_count": 2},
    )
    # 未知事件类型同 QUIZ_TEST_COMPLETED：不产证据、不报错，水位照常推进。
    await seed_event(
        session_factory,
        idempotency_key="teach-back:x-1",
        event_type="TEACH_BACK_COMPLETED",
    )

    consumer = EvidenceConsumer(session_factory)
    processed = await consumer.run_once()

    assert processed == 6
    assert consumer.failed_conversion_count == 0
    evidence = await fetch_evidence(session_factory)
    assert len(evidence) == 4
    by_event = {cast(str, row["event_id"]): row for row in evidence}

    quiz = by_event[quiz_id]
    assert quiz["evidence_type"] == "QUIZ"
    assert quiz["weight"] == 0.9
    assert quiz["confidence"] == 0.8
    assert quiz["result"] == "CORRECT"
    assert quiz["score"] == 1.0
    assert quiz["difficulty"] == "HARD"
    # 测验键位与逐题键位共存不串：同为 QUIZ 映射，各字段按事件透传。
    test_item = by_event[test_item_id]
    assert test_item["evidence_type"] == "QUIZ"
    assert test_item["weight"] == 0.9
    assert test_item["confidence"] == 0.8
    assert test_item["result"] == "PARTIAL"
    assert test_item["score"] == 0.6
    assert test_item["difficulty"] == "MEDIUM"

    summary = by_event[summary_id]
    assert summary["evidence_type"] == "USER_CONFIRMATION"
    assert summary["weight"] == 0.3
    assert summary["confidence"] == 0.7
    assert summary["result"] is None
    assert summary["score"] is None
    assert summary["difficulty"] is None
    knowledge = by_event[batch_id]
    assert knowledge["evidence_type"] == "USER_CONFIRMATION"
    assert knowledge["weight"] == 0.4
    assert knowledge["confidence"] == 0.7

    # 交卷不产证据（双计规避）；未映射类型不产证据。
    assert completed_id not in by_event
    # Event 未带 Concept 时证据归属保持为空；source_anchor 未回填；行为时刻透传。
    for row in evidence:
        assert row["course_id"] == "course-1"
        assert row["concept_id"] is None
        assert row["source_anchor_id"] is None
        assert row["occurred_at"] == OCCURRED_TEXT


@pytest.mark.anyio
async def test_event_concept_is_copied_verbatim_and_triggers_mastery_recompute(
    tmp_path: Path,
) -> None:
    """票 02：证据复制 Event 已固化的 concept_id，并由消费轮触发全量重算。"""
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    _engine, session_factory = create_database(db_path)
    await seed_mastery_subject(session_factory)
    event_id = await seed_event(
        session_factory,
        idempotency_key="quiz-answered:quiz-1",
        event_type="QUIZ_ANSWERED",
        result="CORRECT",
        score=1.0,
        record_id="record-1",
        concept_id="concept-1",
    )

    consumer = EvidenceConsumer(session_factory)
    await consumer.run_once()

    evidence = await fetch_evidence(session_factory)
    assert len(evidence) == 1
    assert evidence[0]["event_id"] == event_id
    assert evidence[0]["concept_id"] == "concept-1"
    snapshot = await fetch_mastery(session_factory, "concept-1")
    assert snapshot is not None
    assert snapshot["evidence_count"] == 1
    assert snapshot["mastery_score"] is None
    assert snapshot["algorithm_version"] == "mastery_v1"


@pytest.mark.anyio
async def test_mastery_recompute_failure_keeps_persisted_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """重算失败不回滚已落证据：按概念有限重试后吞错记日志，主流程与证据完整。"""
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    _engine, session_factory = create_database(db_path)
    await seed_mastery_subject(session_factory)
    await seed_event(
        session_factory,
        idempotency_key="quiz-answered:quiz-1",
        event_type="QUIZ_ANSWERED",
        result="CORRECT",
        score=1.0,
        record_id="record-1",
        concept_id="concept-1",
    )
    attempts = 0

    async def failing_recompute(*_args: object, **_kwargs: object) -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("mastery boom")

    monkeypatch.setattr("app.modules.learning.service._recompute_concept", failing_recompute)
    consumer = EvidenceConsumer(session_factory)

    processed = await consumer.run_once()

    # 概念级失败被 MasteryService 重试并吞掉：证据照常保留，快照缺席等待恢复。
    assert processed == 1
    assert consumer.failed_conversion_count == 0
    assert attempts == 3
    evidence = await fetch_evidence(session_factory)
    assert [row["concept_id"] for row in evidence] == ["concept-1"]
    assert await fetch_mastery(session_factory, "concept-1") is None


@pytest.mark.anyio
async def test_fresh_consumer_rescan_over_same_events_dedupes(tmp_path: Path) -> None:
    """崩溃重启等价：水位归零全量重扫，event_id 唯一去重不重复落行。"""
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    _engine, session_factory = create_database(db_path)
    await seed_event(
        session_factory,
        idempotency_key="quiz-answered:quiz-1",
        event_type="QUIZ_ANSWERED",
        score=1.0,
    )
    await seed_event(
        session_factory,
        idempotency_key="summary-confirmed:s-1",
        event_type="SUMMARY_CONFIRMED",
    )
    first = EvidenceConsumer(session_factory)
    await first.run_once()
    assert len(await fetch_evidence(session_factory)) == 2

    restarted = EvidenceConsumer(session_factory)
    processed = await restarted.run_once()

    assert processed == 2
    assert len(await fetch_evidence(session_factory)) == 2


@pytest.mark.anyio
async def test_events_after_a_round_are_consumed_next_round(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    _engine, session_factory = create_database(db_path)
    first_id = await seed_event(
        session_factory,
        idempotency_key="quiz-answered:quiz-1",
        event_type="QUIZ_ANSWERED",
        score=1.0,
    )
    consumer = EvidenceConsumer(session_factory)
    await consumer.run_once()

    second_id = await seed_event(
        session_factory,
        idempotency_key="summary-confirmed:s-1",
        event_type="SUMMARY_CONFIRMED",
    )
    await consumer.run_once()

    evidence = await fetch_evidence(session_factory)
    assert {cast(str, row["event_id"]) for row in evidence} == {first_id, second_id}


@pytest.mark.anyio
async def test_full_replay_rebuilds_evidence_consistently(tmp_path: Path) -> None:
    """清空派生表后由事件流全量重放，重建结果与首建一致（spec 用户故事 20）。"""
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    _engine, session_factory = create_database(db_path)
    await seed_event(
        session_factory,
        idempotency_key="quiz-answered:quiz-1",
        event_type="QUIZ_ANSWERED",
        result="WRONG",
        score=0.0,
        difficulty="EASY",
        metadata={"question_type": "TRUE_FALSE"},
    )
    await seed_event(
        session_factory,
        idempotency_key="summary-confirmed:s-1",
        event_type="SUMMARY_CONFIRMED",
        metadata={"summary_version_no": 2},
    )
    await seed_event(
        session_factory,
        idempotency_key="knowledge-confirmed:b-1",
        event_type="KNOWLEDGE_CONFIRMED",
        metadata={"batch_id": "b-1", "confirmed_count": 1},
    )
    consumer = EvidenceConsumer(session_factory)
    await consumer.run_once()
    before = await fetch_evidence(session_factory)
    assert len(before) == 3

    async with session_factory() as session, session.begin():
        await session.execute(text("DELETE FROM learning_evidence"))
    replay = EvidenceConsumer(session_factory)
    await replay.run_once()

    assert await fetch_evidence(session_factory) == before


class FlakyConversionConsumer(EvidenceConsumer):
    """失败注入子类（仅测试）：指定事件的每次落证据尝试都抛错。"""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        fail_event_ids: set[str],
    ) -> None:
        super().__init__(session_factory)
        self._fail_event_ids = fail_event_ids
        self.attempts: list[str] = []

    async def _insert_evidence(self, event: LearningEvent, mapping: EvidenceMapping) -> None:
        self.attempts.append(event.id)
        if event.id in self._fail_event_ids:
            raise RuntimeError("conversion boom")
        await super()._insert_evidence(event, mapping)


@pytest.mark.anyio
async def test_conversion_failure_retries_three_times_skips_and_advances_watermark(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    _engine, session_factory = create_database(db_path)
    ok_quiz_id = await seed_event(
        session_factory,
        idempotency_key="quiz-answered:quiz-1",
        event_type="QUIZ_ANSWERED",
        score=1.0,
    )
    bad_id = await seed_event(
        session_factory,
        idempotency_key="quiz-answered:quiz-2",
        event_type="QUIZ_ANSWERED",
        score=0.0,
    )
    ok_summary_id = await seed_event(
        session_factory,
        idempotency_key="summary-confirmed:s-1",
        event_type="SUMMARY_CONFIRMED",
    )

    consumer = FlakyConversionConsumer(session_factory, fail_event_ids={bad_id})
    await consumer.run_once()

    # 单条重试 3 次后跳过：error 语义由内存计数承载，不阻塞其余事件消费。
    assert consumer.attempts.count(bad_id) == 3
    assert consumer.failed_conversion_count == 1
    evidence = await fetch_evidence(session_factory)
    assert {cast(str, row["event_id"]) for row in evidence} == {ok_quiz_id, ok_summary_id}

    # 不建死信表、不阻塞水位：下轮不再重试失败行。
    await consumer.run_once()
    assert consumer.attempts.count(bad_id) == 3
    assert consumer.failed_conversion_count == 1
    assert len(await fetch_evidence(session_factory)) == 2


@asynccontextmanager
async def running_app(data_dir: Path) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(data_dir=data_dir, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client


@pytest.mark.anyio
async def test_app_lifespan_starts_consumer_and_shuts_down_cleanly(tmp_path: Path) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, _client):
        consumer = app.state.evidence_consumer
        assert isinstance(consumer, EvidenceConsumer)
        event_id = await seed_event(
            app.state.session_factory,
            idempotency_key="quiz-answered:quiz-1",
            event_type="QUIZ_ANSWERED",
            score=1.0,
        )
        processed = await consumer.run_once()
        evidence = await fetch_evidence(app.state.session_factory)

    assert processed == 1
    assert [cast(str, row["event_id"]) for row in evidence] == [event_id]
