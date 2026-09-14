"""learning 域：learning_evidence 迁移结构与约束行为（event_id 唯一、weight/confidence 0~1）。"""

import sqlite3
from pathlib import Path
from typing import cast

import aiosqlite
import pytest

from app.db.migrations import run_migrations


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


def evidence_row(
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
        await connection.execute(evidence_row(event_id="event-1", weight="0.9"))
        await connection.commit()

        with pytest.raises(sqlite3.IntegrityError):
            await connection.execute(evidence_row(event_id="event-2", weight="1.5"))
        with pytest.raises(sqlite3.IntegrityError):
            await connection.execute(evidence_row(event_id="event-3", weight="-0.1"))
        # event_id 唯一：重放同键再插被数据库拒绝。
        with pytest.raises(sqlite3.IntegrityError):
            await connection.execute(evidence_row(event_id="event-1", weight="0.9"))
