"""learning 域：learning_evidence 迁移结构与约束行为、统一事件写入幂等跳过。"""

import sqlite3
from pathlib import Path
from typing import cast

import aiosqlite
import pytest
from sqlalchemy import func, select

from app.db.base import utcnow
from app.db.engine import create_database
from app.db.migrations import run_migrations
from app.modules.learning.events import write_learning_event
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

    assert version == (21,)
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
