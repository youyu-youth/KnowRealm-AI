"""learning 域：learning_evidence 迁移结构与约束行为、统一事件写入幂等跳过、薄只读查询。"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import cast

import aiosqlite
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.db.engine import create_database
from app.db.migrations import run_migrations
from app.modules.learning.consumer import EvidenceConsumer
from app.modules.learning.events import write_learning_event
from app.modules.learning.queries import list_evidence_by_course, list_evidence_by_record
from app.modules.record.models import LearningEvent


@pytest.mark.anyio
async def test_migration_0021_creates_learning_evidence_table(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"

    await run_migrations(db_path)

    async with aiosqlite.connect(db_path) as connection:
        version = await (await connection.execute("PRAGMA user_version")).fetchone()
        columns = {
            cast(str, row[1])
            for row in await (
                await connection.execute("PRAGMA table_info(learning_evidence)")
            ).fetchall()
        }
        indexes = {
            cast(str, row[1])
            for row in await (
                await connection.execute("PRAGMA index_list(learning_evidence)")
            ).fetchall()
        }

    assert version == (25,)
    assert columns == {
        "id",
        "course_id",
        "concept_id",
        "event_id",
        "evidence_type",
        "result",
        "score",
        "difficulty",
        "weight",
        "confidence",
        "source_anchor_id",
        "metadata_json",
        "occurred_at",
        "created_at",
    }
    # 证据是可再生派生数据：追加型不软删。
    assert "deleted_at" not in columns
    assert "idx_learning_evidence_concept_occurred" in indexes
    # event_id 唯一约束（内联 UNIQUE 产出 sqlite 自动索引）。
    assert "sqlite_autoindex_learning_evidence_1" in indexes


def evidence_insert_sql(
    *,
    event_id: str,
    weight: str,
) -> str:
    return (
        "INSERT INTO learning_evidence "
        "(id, course_id, event_id, evidence_type, weight, confidence, "
        "metadata_json, occurred_at, created_at) "
        "VALUES "
        f"('evidence-1', 'course-1', '{event_id}', 'QUIZ', {weight}, 0.8, "
        "'{}', '2026-09-14T00:00:00.000000Z', '2026-09-14T00:00:00.000000Z')"
    )


@pytest.mark.anyio
async def test_learning_evidence_rejects_out_of_range_weight(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)

    async with aiosqlite.connect(db_path) as connection:
        await connection.execute(evidence_insert_sql(event_id="event-1", weight="0.9"))
        await connection.commit()

        with pytest.raises(sqlite3.IntegrityError):
            await connection.execute(evidence_insert_sql(event_id="event-2", weight="1.5"))
        with pytest.raises(sqlite3.IntegrityError):
            await connection.execute(evidence_insert_sql(event_id="event-3", weight="-0.1"))
        # event_id 唯一：重放同键再插被数据库拒绝。
        with pytest.raises(sqlite3.IntegrityError):
            await connection.execute(evidence_insert_sql(event_id="event-1", weight="0.9"))


@pytest.mark.anyio
async def test_write_learning_event_skips_duplicate_idempotency_key(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    _engine, session_factory = create_database(db_path)

    async with session_factory() as session, session.begin():
        await write_learning_event(
            session,
            course_id="course-1",
            event_type="QUIZ_ANSWERED",
            source_type="QUIZ_QUESTION",
            source_id="quiz-1",
            idempotency_key="quiz-answered:quiz-1",
            occurred_at=utcnow(),
            metadata={"question_type": "MULTIPLE_CHOICE"},
        )

    # 同键重放（崩溃恢复/重复触发场景）：静默跳过、不抛错、不重复落行。
    async with session_factory() as session, session.begin():
        await write_learning_event(
            session,
            course_id="course-1",
            event_type="QUIZ_ANSWERED",
            source_type="QUIZ_QUESTION",
            source_id="quiz-1",
            idempotency_key="quiz-answered:quiz-1",
            occurred_at=utcnow(),
            metadata={"question_type": "MULTIPLE_CHOICE"},
        )
        count = await session.scalar(select(func.count()).select_from(LearningEvent))

    assert count == 1


async def seed_evidence_source(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    idempotency_key: str,
    event_type: str,
    occurred_at: datetime,
    record_id: str | None = None,
    course_id: str = "course-1",
) -> None:
    """落一条事件并经消费循环转为证据（查询测试的真实数据来源）。"""
    async with session_factory() as session, session.begin():
        await write_learning_event(
            session,
            course_id=course_id,
            event_type=event_type,
            source_type="TEST_SOURCE",
            source_id=idempotency_key,
            idempotency_key=idempotency_key,
            occurred_at=occurred_at,
            metadata={},
            record_id=record_id,
        )


@pytest.mark.anyio
async def test_list_evidence_by_record_joins_through_events(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    _engine, session_factory = create_database(db_path)
    await seed_evidence_source(
        session_factory,
        idempotency_key="summary-confirmed:s1",
        event_type="SUMMARY_CONFIRMED",
        occurred_at=datetime(2026, 9, 14, 9, 0, 0),
        record_id="record-a",
    )
    await seed_evidence_source(
        session_factory,
        idempotency_key="quiz-answered:q1",
        event_type="QUIZ_ANSWERED",
        occurred_at=datetime(2026, 9, 14, 8, 0, 0),
        record_id="record-a",
    )
    await seed_evidence_source(
        session_factory,
        idempotency_key="quiz-answered:q2",
        event_type="QUIZ_ANSWERED",
        occurred_at=datetime(2026, 9, 14, 8, 30, 0),
        record_id="record-b",
    )
    # 交卷事件不产证据：经同一 record 的查询也不应出现。
    await seed_evidence_source(
        session_factory,
        idempotency_key="quiz-test-completed:t1",
        event_type="QUIZ_TEST_COMPLETED",
        occurred_at=datetime(2026, 9, 14, 8, 45, 0),
        record_id="record-a",
    )
    consumer = EvidenceConsumer(session_factory)
    await consumer.run_once()

    async with session_factory() as session:
        evidence_a = await list_evidence_by_record(session, record_id="record-a")
        evidence_b = await list_evidence_by_record(session, record_id="record-b")
        evidence_x = await list_evidence_by_record(session, record_id="record-x")

    assert [row.occurred_at for row in evidence_a] == [
        datetime(2026, 9, 14, 8, 0, 0),
        datetime(2026, 9, 14, 9, 0, 0),
    ]
    assert [row.evidence_type for row in evidence_a] == ["QUIZ", "USER_CONFIRMATION"]
    assert [row.occurred_at for row in evidence_b] == [datetime(2026, 9, 14, 8, 30, 0)]
    assert evidence_x == []


@pytest.mark.anyio
async def test_list_evidence_by_course_filters_and_orders(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    _engine, session_factory = create_database(db_path)
    await seed_evidence_source(
        session_factory,
        idempotency_key="quiz-answered:q1",
        event_type="QUIZ_ANSWERED",
        occurred_at=datetime(2026, 9, 14, 8, 0, 0),
        record_id="record-a",
        course_id="course-1",
    )
    await seed_evidence_source(
        session_factory,
        idempotency_key="knowledge-confirmed:b1",
        event_type="KNOWLEDGE_CONFIRMED",
        occurred_at=datetime(2026, 9, 14, 8, 30, 0),
        record_id="record-b",
        course_id="course-1",
    )
    await seed_evidence_source(
        session_factory,
        idempotency_key="summary-confirmed:s2",
        event_type="SUMMARY_CONFIRMED",
        occurred_at=datetime(2026, 9, 14, 8, 15, 0),
        record_id="record-c",
        course_id="course-2",
    )
    consumer = EvidenceConsumer(session_factory)
    await consumer.run_once()

    async with session_factory() as session:
        evidence = await list_evidence_by_course(session, course_id="course-1")
        other = await list_evidence_by_course(session, course_id="course-2")

    assert [row.occurred_at for row in evidence] == [
        datetime(2026, 9, 14, 8, 0, 0),
        datetime(2026, 9, 14, 8, 30, 0),
    ]
    assert {row.course_id for row in evidence} == {"course-1"}
    assert [row.evidence_type for row in other] == ["USER_CONFIRMATION"]
