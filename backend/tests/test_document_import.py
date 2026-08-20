from pathlib import Path

import aiosqlite
import pytest

from app.db.migrations import MIGRATIONS_DIR, run_migrations


async def assert_document_import_schema(db_path: Path) -> None:
    async with aiosqlite.connect(db_path) as connection:
        version = await (await connection.execute("PRAGMA user_version")).fetchone()
        tables = {
            row[0]
            for row in await (
                await connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            ).fetchall()
        }
        record_file_columns = await (
            await connection.execute("PRAGMA table_info(record_files)")
        ).fetchall()
        processing_job_indexes = await (
            await connection.execute("PRAGMA index_list(processing_jobs)")
        ).fetchall()

    assert version == (3,)
    assert {"record_files", "transcripts", "processing_jobs"} <= tables
    assert "processing_status" not in {column[1] for column in record_file_columns}
    assert {index[1] for index in processing_job_indexes} >= {
        "idx_processing_jobs_record",
        "idx_processing_jobs_claim",
    }


@pytest.mark.anyio
async def test_document_import_migration_initializes_new_database_and_upgrades_v2(
    tmp_path: Path,
) -> None:
    fresh_db = tmp_path / "fresh.db"
    upgraded_db = tmp_path / "upgraded.db"

    await run_migrations(fresh_db)
    async with aiosqlite.connect(upgraded_db) as connection:
        for migration in ("0001_courses.sql", "0002_records.sql"):
            await connection.executescript(
                (MIGRATIONS_DIR / migration).read_text(encoding="utf-8")
            )
        await connection.execute("PRAGMA user_version=2")
        await connection.commit()
    await run_migrations(upgraded_db)

    await assert_document_import_schema(fresh_db)
    await assert_document_import_schema(upgraded_db)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
