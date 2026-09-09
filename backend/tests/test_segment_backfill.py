"""启动幂等回填（票 04）：存量无分片转写 → 启动补建无时间戳分片；重复启动零副作用。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.main import create_app

TOKEN = "test-launch-token"
NOW = "2026-09-09T08:00:00.000000Z"


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


async def seed_legacy_data(db_path: Path) -> dict[str, str]:
    """升级前快照：无分片的存量转写（音频）、粘贴记录（无文件）、已有分片的记录。"""
    ids = {
        "legacy_record": str(uuid4()),
        "legacy_file": str(uuid4()),
        "legacy_transcript": str(uuid4()),
        "note_record": str(uuid4()),
        "note_transcript": str(uuid4()),
        "segmented_record": str(uuid4()),
        "segmented_file": str(uuid4()),
        "segmented_transcript": str(uuid4()),
        "kept_segment": str(uuid4()),
    }
    async with aiosqlite.connect(db_path) as connection:
        await connection.execute("PRAGMA foreign_keys=ON")
        await connection.execute(
            "INSERT INTO records (id, course_id, capture_type, title, status, duration_ms, "
            "summary_confirmed_at, created_at, updated_at, deleted_at) "
            "VALUES (:id, NULL, 'AUDIO_IMPORT', '存量音频', 'COMPLETED', 60000, "
            ":now, :now, :now, NULL)",
            {"id": ids["legacy_record"], "now": NOW},
        )
        await connection.execute(
            "INSERT INTO record_files (id, record_id, file_type, source_type, file_path, "
            "original_name, mime_type, file_size, duration_ms, sequence_no, content_hash, "
            "created_at, updated_at, deleted_at) "
            "VALUES (:id, :record_id, 'AUDIO', 'RECORDED', 'p.ogg', 'p.ogg', 'audio/ogg', "
            "1, 60000, 0, 'h', :now, :now, NULL)",
            {"id": ids["legacy_file"], "record_id": ids["legacy_record"], "now": NOW},
        )
        await connection.execute(
            "INSERT INTO transcripts (id, record_id, language, content, source_version, "
            "edited_by_user, created_at, updated_at, deleted_at) "
            "VALUES (:id, :record_id, 'zh-CN', '第一行\n第二行\n\n第三行', 1, 0, "
            ":now, :now, NULL)",
            {"id": ids["legacy_transcript"], "record_id": ids["legacy_record"], "now": NOW},
        )
        await connection.execute(
            "INSERT INTO records (id, course_id, capture_type, title, status, duration_ms, "
            "summary_confirmed_at, created_at, updated_at, deleted_at) "
            "VALUES (:id, NULL, 'PASTE', '粘贴', 'NOTE', 0, :now, :now, :now, NULL)",
            {"id": ids["note_record"], "now": NOW},
        )
        await connection.execute(
            "INSERT INTO transcripts (id, record_id, language, content, source_version, "
            "edited_by_user, created_at, updated_at, deleted_at) "
            "VALUES (:id, :record_id, 'zh-CN', '粘贴正文', 1, 0, :now, :now, NULL)",
            {"id": ids["note_transcript"], "record_id": ids["note_record"], "now": NOW},
        )
        await connection.execute(
            "INSERT INTO records (id, course_id, capture_type, title, status, duration_ms, "
            "summary_confirmed_at, created_at, updated_at, deleted_at) "
            "VALUES (:id, NULL, 'AUDIO_IMPORT', '已有分片', 'COMPLETED', 60000, "
            ":now, :now, :now, NULL)",
            {"id": ids["segmented_record"], "now": NOW},
        )
        await connection.execute(
            "INSERT INTO record_files (id, record_id, file_type, source_type, file_path, "
            "original_name, mime_type, file_size, duration_ms, sequence_no, content_hash, "
            "created_at, updated_at, deleted_at) "
            "VALUES (:id, :record_id, 'AUDIO', 'RECORDED', 'q.ogg', 'q.ogg', 'audio/ogg', "
            "1, 60000, 0, 'h', :now, :now, NULL)",
            {"id": ids["segmented_file"], "record_id": ids["segmented_record"], "now": NOW},
        )
        await connection.execute(
            "INSERT INTO transcripts (id, record_id, language, content, source_version, "
            "edited_by_user, created_at, updated_at, deleted_at) "
            "VALUES (:id, :record_id, 'zh-CN', '已有分片正文', 1, 0, :now, :now, NULL)",
            {"id": ids["segmented_transcript"], "record_id": ids["segmented_record"], "now": NOW},
        )
        await connection.execute(
            "INSERT INTO transcript_segments (id, transcript_id, record_id, file_id, "
            "sequence_no, record_start_ms, record_end_ms, file_start_ms, file_end_ms, "
            "speaker, content, content_hash) "
            "VALUES (:id, :tid, :rid, :fid, 0, 0, 100, 0, 100, NULL, '已有分片正文', 'h')",
            {
                "id": ids["kept_segment"],
                "tid": ids["segmented_transcript"],
                "rid": ids["segmented_record"],
                "fid": ids["segmented_file"],
            },
        )
        await connection.commit()
    return ids


async def fetch_segments(client: httpx.AsyncClient, record_id: str) -> list[dict[str, object]]:
    response = await client.get(f"/api/records/{record_id}/transcript/segments")
    assert response.status_code == 200
    return list(response.json())


@pytest.mark.anyio
async def test_startup_backfills_legacy_transcripts_idempotently(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    db_path = data_dir / "knowrealm.db"
    data_dir.mkdir()
    from app.db.migrations import run_migrations

    await run_migrations(db_path)
    ids = await seed_legacy_data(db_path)

    async with running_app(data_dir) as (_app, client):
        legacy = await fetch_segments(client, ids["legacy_record"])
        note = await fetch_segments(client, ids["note_record"])
        kept = await fetch_segments(client, ids["segmented_record"])

    assert [(row["content"], row["sequence_no"]) for row in legacy] == [
        ("第一行", 0),
        ("第二行", 1),
        ("第三行", 2),
    ]
    assert all(
        row["record_start_ms"] is None
        and row["record_end_ms"] is None
        and row["file_start_ms"] is None
        and row["file_end_ms"] is None
        and row["speaker"] is None
        for row in legacy
    )
    assert note == []
    assert [row["id"] for row in kept] == [ids["kept_segment"]]

    async with aiosqlite.connect(db_path) as connection:
        rows = await (
            await connection.execute(
                "SELECT file_id, content_hash FROM transcript_segments "
                "WHERE record_id = :rid ORDER BY sequence_no",
                {"rid": ids["legacy_record"]},
            )
        ).fetchall()
    assert {row[0] for row in rows} == {ids["legacy_file"]}

    # 再启动：重复回填零副作用。
    async with running_app(data_dir) as (_app, client):
        legacy_again = await fetch_segments(client, ids["legacy_record"])
        note_again = await fetch_segments(client, ids["note_record"])
        kept_again = await fetch_segments(client, ids["segmented_record"])

    assert legacy_again == legacy
    assert note_again == []
    assert kept_again == kept


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
