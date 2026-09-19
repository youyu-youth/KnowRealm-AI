"""迁移 0019 四表结构与 source_anchor 模块：schema/CHECK/索引/NULL 语义与锚点列表端点。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.db.migrations import MIGRATIONS_DIR, run_migrations, supported_user_version
from app.main import create_app
from app.modules.record.models import Record

TOKEN = "test-launch-token"

COURSE_ID = "c1000000-0000-4000-8000-000000000001"
RECORD_ID = "c1000000-0000-4000-8000-000000000002"
FILE_ID = "c1000000-0000-4000-8000-000000000003"
TRANSCRIPT_ID = "c1000000-0000-4000-8000-000000000004"

PARENT_ROWS_SQL = (
    "INSERT INTO courses (id, name, learning_context, depth, status, created_at, updated_at) "
    f"VALUES ('{COURSE_ID}', '测试课程', 'INTEREST', 'BEGINNER', 'ACTIVE', "
    "'2026-09-09T00:00:00.000000Z', '2026-09-09T00:00:00.000000Z');\n"
    "INSERT INTO records (id, course_id, capture_type, title, status, duration_ms, "
    "created_at, updated_at) "
    f"VALUES ('{RECORD_ID}', '{COURSE_ID}', 'RECORDING', '测试记录', 'NOTE', 0, "
    "'2026-09-09T00:00:00.000000Z', '2026-09-09T00:00:00.000000Z');\n"
    "INSERT INTO record_files (id, record_id, file_type, source_type, file_path, "
    "original_name, mime_type, file_size, duration_ms, sequence_no, content_hash, "
    "created_at, updated_at) "
    f"VALUES ('{FILE_ID}', '{RECORD_ID}', 'AUDIO', 'RECORDED', 'files/a.m4a', "
    "'a.m4a', 'audio/mp4', 0, 0, 0, 'hash', "
    "'2026-09-09T00:00:00.000000Z', '2026-09-09T00:00:00.000000Z');\n"
    "INSERT INTO transcripts (id, record_id, language, content, source_version, "
    "edited_by_user, created_at, updated_at) "
    f"VALUES ('{TRANSCRIPT_ID}', '{RECORD_ID}', 'zh', '正文', 1, 0, "
    "'2026-09-09T00:00:00.000000Z', '2026-09-09T00:00:00.000000Z');"
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@asynccontextmanager
async def running_anchor_app(
    data_dir: Path,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(data_dir=data_dir, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client


async def _columns(connection: aiosqlite.Connection, table: str) -> dict[str, int]:
    rows = await (await connection.execute(f"PRAGMA table_info({table})")).fetchall()
    return {row[1]: int(row[3]) for row in rows}


async def assert_segment_tables_schema(db_path: Path) -> None:
    async with aiosqlite.connect(db_path) as connection:
        version = await (await connection.execute("PRAGMA user_version")).fetchone()
        transcript_columns = await _columns(connection, "transcript_segments")
        document_columns = await _columns(connection, "document_segments")
        anchor_columns = await _columns(connection, "source_anchors")
        link_columns = await _columns(connection, "source_anchor_links")
        transcript_indexes = await (
            await connection.execute("PRAGMA index_list(transcript_segments)")
        ).fetchall()
        link_indexes = await (
            await connection.execute("PRAGMA index_list(source_anchor_links)")
        ).fetchall()

    assert version == (supported_user_version(),)
    assert list(transcript_columns) == [
        "id",
        "transcript_id",
        "record_id",
        "file_id",
        "sequence_no",
        "record_start_ms",
        "record_end_ms",
        "file_start_ms",
        "file_end_ms",
        "speaker",
        "content",
        "content_hash",
    ]
    nullable_timestamps = ["record_start_ms", "record_end_ms", "file_start_ms", "file_end_ms"]
    assert all(transcript_columns[column] == 0 for column in nullable_timestamps + ["speaker"])
    # id 为 TEXT PRIMARY KEY（SQLite notnull 位恒 0），不在必填断言内。
    required = ["transcript_id", "record_id", "file_id", "sequence_no", "content", "content_hash"]
    assert all(transcript_columns[column] == 1 for column in required)

    assert list(document_columns) == [
        "id",
        "course_id",
        "record_id",
        "record_file_id",
        "library_item_id",
        "sequence_no",
        "page_no",
        "section_title",
        "content",
        "start_offset",
        "end_offset",
        "content_hash",
    ]
    assert all(
        document_columns[column] == 0
        for column in [
            "course_id",
            "record_id",
            "record_file_id",
            "library_item_id",
            "page_no",
            "section_title",
            "start_offset",
            "end_offset",
        ]
    )

    assert list(anchor_columns) == [
        "id",
        "course_id",
        "source_type",
        "source_id",
        "record_id",
        "record_file_id",
        "library_item_id",
        "transcript_segment_id",
        "document_segment_id",
        "start_offset",
        "end_offset",
        "page_no",
    ]

    assert list(link_columns) == [
        "id",
        "resource_type",
        "resource_id",
        "source_anchor_id",
        "relation_type",
    ]

    assert {index[1] for index in transcript_indexes} >= {
        "idx_transcript_segments_record_sequence",
        "idx_transcript_segments_file_start",
        "idx_transcript_segments_record_start",
    }
    assert any(index[2] == 1 for index in link_indexes), "四元组唯一约束必须生成唯一索引"


@pytest.mark.anyio
async def test_migration_0019_creates_segment_tables_on_fresh_and_upgraded_databases(
    tmp_path: Path,
) -> None:
    fresh_db = tmp_path / "fresh.db"
    upgraded_db = tmp_path / "upgraded.db"

    await run_migrations(fresh_db)
    migrations = sorted(MIGRATIONS_DIR.glob("*.sql"))
    async with aiosqlite.connect(upgraded_db) as connection:
        for path in migrations[:-1]:
            await connection.executescript(path.read_text(encoding="utf-8"))
        await connection.execute(f"PRAGMA user_version={len(migrations) - 1}")
        await connection.commit()
    await run_migrations(upgraded_db)

    await assert_segment_tables_schema(fresh_db)
    await assert_segment_tables_schema(upgraded_db)


@pytest.mark.anyio
async def test_transcript_segments_accept_null_timestamps_and_speaker(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    async with aiosqlite.connect(db_path) as connection:
        await connection.executescript(PARENT_ROWS_SQL)
        await connection.execute(
            "INSERT INTO transcript_segments (id, transcript_id, record_id, file_id, "
            "sequence_no, record_start_ms, record_end_ms, file_start_ms, file_end_ms, "
            "speaker, content, content_hash) "
            f"VALUES ('seg-1', '{TRANSCRIPT_ID}', '{RECORD_ID}', '{FILE_ID}', "
            "0, NULL, NULL, NULL, NULL, NULL, '第一句', 'hash-1')"
        )
        row = await (
            await connection.execute(
                "SELECT record_start_ms, record_end_ms, file_start_ms, file_end_ms, speaker "
                "FROM transcript_segments WHERE id = 'seg-1'"
            )
        ).fetchone()
        await connection.commit()

    assert row == (None, None, None, None, None)


@pytest.mark.anyio
async def test_document_segments_require_exactly_one_source(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    async with aiosqlite.connect(db_path) as connection:
        await connection.executescript(PARENT_ROWS_SQL)
        insert = (
            "INSERT INTO document_segments (id, course_id, record_id, record_file_id, "
            "library_item_id, sequence_no, page_no, section_title, content, "
            "start_offset, end_offset, content_hash) "
            f"VALUES ('ds-1', '{COURSE_ID}', '{RECORD_ID}', :record_file_id, "
            ":library_item_id, 0, 1, NULL, '第一页', 0, 100, 'hash-1')"
        )
        with pytest.raises(aiosqlite.IntegrityError):
            await connection.execute(insert, {"record_file_id": None, "library_item_id": None})
        with pytest.raises(aiosqlite.IntegrityError):
            await connection.execute(
                insert,
                {"record_file_id": FILE_ID, "library_item_id": "material-1"},
            )
        await connection.execute(insert, {"record_file_id": FILE_ID, "library_item_id": None})
        await connection.commit()


@pytest.mark.anyio
async def test_source_anchors_require_segment_for_audio_and_document_sources(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    async with aiosqlite.connect(db_path) as connection:
        await connection.executescript(PARENT_ROWS_SQL)
        await connection.execute(
            "INSERT INTO transcript_segments (id, transcript_id, record_id, file_id, "
            "sequence_no, content, content_hash) "
            f"VALUES ('seg-1', '{TRANSCRIPT_ID}', '{RECORD_ID}', '{FILE_ID}', 0, '句', 'h')"
        )
        await connection.execute(
            "INSERT INTO document_segments (id, course_id, record_file_id, sequence_no, "
            "content, content_hash) "
            f"VALUES ('ds-1', '{COURSE_ID}', '{FILE_ID}', 0, '页', 'h')"
        )
        insert = (
            "INSERT INTO source_anchors (id, course_id, source_type, source_id, record_id, "
            "transcript_segment_id, document_segment_id) "
            f"VALUES (:id, '{COURSE_ID}', :source_type, :source_id, '{RECORD_ID}', "
            ":transcript_segment_id, :document_segment_id)"
        )
        with pytest.raises(aiosqlite.IntegrityError):
            await connection.execute(
                insert,
                {
                    "id": "anchor-audio",
                    "source_type": "AUDIO_SEGMENT",
                    "source_id": "seg-1",
                    "transcript_segment_id": None,
                    "document_segment_id": None,
                },
            )
        with pytest.raises(aiosqlite.IntegrityError):
            await connection.execute(
                insert,
                {
                    "id": "anchor-doc",
                    "source_type": "DOCUMENT_SEGMENT",
                    "source_id": "ds-1",
                    "transcript_segment_id": None,
                    "document_segment_id": None,
                },
            )
        # AUDIO 来源跨挂 document_segment_id 同样被拒：必须关联对应类型的具体分片。
        with pytest.raises(aiosqlite.IntegrityError):
            await connection.execute(
                insert,
                {
                    "id": "anchor-cross",
                    "source_type": "AUDIO_SEGMENT",
                    "source_id": "ds-1",
                    "transcript_segment_id": None,
                    "document_segment_id": "ds-1",
                },
            )
        await connection.execute(
            insert,
            {
                "id": "anchor-audio-ok",
                "source_type": "AUDIO_SEGMENT",
                "source_id": "seg-1",
                "transcript_segment_id": "seg-1",
                "document_segment_id": None,
            },
        )
        await connection.execute(
            insert,
            {
                "id": "anchor-note-ok",
                "source_type": "USER_NOTE",
                "source_id": "note-1",
                "transcript_segment_id": None,
                "document_segment_id": None,
            },
        )
        await connection.commit()


@pytest.mark.anyio
async def test_source_anchor_links_unique_per_resource_and_relation(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    async with aiosqlite.connect(db_path) as connection:
        await connection.executescript(PARENT_ROWS_SQL)
        await connection.execute(
            "INSERT INTO source_anchors (id, course_id, source_type, source_id) "
            f"VALUES ('anchor-1', '{COURSE_ID}', 'USER_NOTE', 'note-1')"
        )
        insert = (
            "INSERT INTO source_anchor_links (id, resource_type, resource_id, "
            "source_anchor_id, relation_type) "
            "VALUES (:id, :resource_type, :resource_id, 'anchor-1', :relation_type)"
        )
        await connection.execute(
            insert,
            {
                "id": "link-1",
                "resource_type": "SUMMARY",
                "resource_id": "summary-1",
                "relation_type": "SUPPORTS",
            },
        )
        with pytest.raises(aiosqlite.IntegrityError):
            await connection.execute(
                insert,
                {
                    "id": "link-2",
                    "resource_type": "SUMMARY",
                    "resource_id": "summary-1",
                    "relation_type": "SUPPORTS",
                },
            )
        await connection.execute(
            insert,
            {
                "id": "link-3",
                "resource_type": "SUMMARY",
                "resource_id": "summary-1",
                "relation_type": "REFERENCES",
            },
        )
        await connection.commit()


@pytest.mark.anyio
async def test_list_source_anchors_returns_empty_for_existing_record(tmp_path: Path) -> None:
    async with running_anchor_app(tmp_path / "KnowRealm") as (app, client):
        async with app.state.session_factory() as session, session.begin():
            record = Record(
                course_id=None,
                capture_type="QUICK_NOTE",
                title="",
                status="NOTE",
                duration_ms=0,
            )
            session.add(record)
            await session.flush()
            record_id = record.id

        response = await client.get(f"/api/records/{record_id}/source-anchors")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.anyio
async def test_list_source_anchors_returns_rows_for_record(tmp_path: Path) -> None:
    async with running_anchor_app(tmp_path / "KnowRealm") as (app, client):
        from app.modules.course.models import Course
        from app.modules.source_anchor.models import SourceAnchor

        async with app.state.session_factory() as session, session.begin():
            course = Course(name="测试课程", learning_context="INTEREST", depth="BEGINNER")
            record = Record(
                course_id=None,
                capture_type="QUICK_NOTE",
                title="",
                status="NOTE",
                duration_ms=0,
            )
            session.add(course)
            session.add(record)
            await session.flush()
            record_id = record.id
            session.add(
                SourceAnchor(
                    course_id=course.id,
                    source_type="USER_NOTE",
                    source_id="note-1",
                    record_id=record_id,
                )
            )

        response = await client.get(f"/api/records/{record_id}/source-anchors")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["source_type"] == "USER_NOTE"
    assert body[0]["source_id"] == "note-1"
    assert body[0]["record_id"] == record_id


@pytest.mark.anyio
async def test_list_source_anchors_404_for_missing_record(tmp_path: Path) -> None:
    async with running_anchor_app(tmp_path / "KnowRealm") as (_app, client):
        response = await client.get(
            "/api/records/c1000000-0000-4000-8000-000000000099/source-anchors"
        )

    assert response.status_code == 404
    assert response.json()["code"] == "RECORD_NOT_FOUND"
