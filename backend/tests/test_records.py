from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.db.migrations import MIGRATIONS_DIR, run_migrations
from app.main import create_app
from app.models.record import Record

TOKEN = "test-launch-token"
STATUSES = (
    "NOTE",
    "DRAFT",
    "CONTENT_PROCESSING",
    "SUMMARY_PENDING",
    "SUMMARY_PROCESSING",
    "SUMMARY_READY",
    "COMPLETED",
    "FAILED",
)


@asynccontextmanager
async def running_record_app(
    data_dir: Path,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(data_dir=data_dir, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
        ) as client:
            yield app, client


async def assert_records_schema(db_path: Path) -> None:
    async with aiosqlite.connect(db_path) as connection:
        version = await (await connection.execute("PRAGMA user_version")).fetchone()
        columns = await (await connection.execute("PRAGMA table_info(records)")).fetchall()
        foreign_keys = await (
            await connection.execute("PRAGMA foreign_key_list(records)")
        ).fetchall()
        indexes = await (await connection.execute("PRAGMA index_list(records)")).fetchall()

    assert version == (7,)
    assert [column[1] for column in columns] == [
        "id",
        "course_id",
        "capture_type",
        "title",
        "status",
        "duration_ms",
        "summary_confirmed_at",
        "created_at",
        "updated_at",
        "deleted_at",
    ]
    assert next(column for column in columns if column[1] == "status")[4] is None
    assert any(
        foreign_key[2] == "courses"
        and foreign_key[3] == "course_id"
        and foreign_key[6] == "CASCADE"
        for foreign_key in foreign_keys
    )
    assert {index[1] for index in indexes} >= {
        "idx_records_created_at",
        "idx_records_course_created_at",
        "idx_records_status",
    }


@pytest.mark.anyio
async def test_record_orm_generates_uuid_and_utc_timestamps(tmp_path: Path) -> None:
    async with running_record_app(tmp_path / "KnowRealm") as (app, _client):
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

    assert UUID(record.id).version == 4
    assert record.created_at.utcoffset() == timedelta(0)
    assert record.updated_at.utcoffset() == timedelta(0)


@pytest.mark.anyio
async def test_records_migration_initializes_new_database_and_upgrades_v1(
    tmp_path: Path,
) -> None:
    fresh_db = tmp_path / "fresh.db"
    upgraded_db = tmp_path / "upgraded.db"

    await run_migrations(fresh_db)
    async with aiosqlite.connect(upgraded_db) as connection:
        await connection.executescript(
            (MIGRATIONS_DIR / "0001_courses.sql").read_text(encoding="utf-8")
            + "\nPRAGMA user_version=1;"
        )
    await run_migrations(upgraded_db)

    await assert_records_schema(fresh_db)
    await assert_records_schema(upgraded_db)


@pytest.mark.anyio
async def test_records_constraints_allow_inbox_and_cascade_physical_course_delete(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "constraints.db"
    await run_migrations(db_path)
    insert_record = """
        INSERT INTO records (
            id, course_id, capture_type, title, status, duration_ms,
            summary_confirmed_at, created_at, updated_at, deleted_at
        ) VALUES (
            :id, :course_id, :capture_type, '', :status, :duration_ms,
            NULL, '2026-08-19T08:00:00.000000Z',
            '2026-08-19T08:00:00.000000Z', NULL
        )
    """
    async with aiosqlite.connect(db_path) as connection:
        await connection.execute("PRAGMA foreign_keys=ON")
        await connection.execute(
            """
            INSERT INTO courses (
                id, name, learning_context, education_stage, depth,
                course_type, description, hot_words, status,
                created_at, updated_at, deleted_at
            ) VALUES (
                'course-1', '课程', 'INTEREST', NULL, 'BEGINNER',
                NULL, NULL, NULL, 'ACTIVE',
                '2026-08-19T08:00:00.000000Z',
                '2026-08-19T08:00:00.000000Z', NULL
            )
            """
        )
        await connection.commit()

        invalid_rows = (
            {
                "id": "bad-status",
                "course_id": "course-1",
                "capture_type": "QUICK_NOTE",
                "status": "UNKNOWN",
                "duration_ms": 0,
            },
            {
                "id": "bad-capture",
                "course_id": "course-1",
                "capture_type": "UNKNOWN",
                "status": "NOTE",
                "duration_ms": 0,
            },
            {
                "id": "bad-duration",
                "course_id": "course-1",
                "capture_type": "AUDIO_IMPORT",
                "status": "DRAFT",
                "duration_ms": -1,
            },
            {
                "id": "bad-course",
                "course_id": "missing",
                "capture_type": "PASTE",
                "status": "NOTE",
                "duration_ms": 0,
            },
        )
        for row in invalid_rows:
            with pytest.raises(aiosqlite.IntegrityError):
                await connection.execute(insert_record, row)
            await connection.rollback()

        await connection.execute(
            insert_record,
            {
                "id": "course-record",
                "course_id": "course-1",
                "capture_type": "DOCUMENT_IMPORT",
                "status": "DRAFT",
                "duration_ms": 0,
            },
        )
        await connection.execute(
            insert_record,
            {
                "id": "inbox-record",
                "course_id": None,
                "capture_type": "QUICK_NOTE",
                "status": "NOTE",
                "duration_ms": 0,
            },
        )
        await connection.commit()
        await connection.execute("DELETE FROM courses WHERE id = 'course-1'")
        remaining = await (
            await connection.execute("SELECT id FROM records ORDER BY id")
        ).fetchall()

    assert remaining == [("inbox-record",)]


@pytest.mark.anyio
async def test_course_records_api_is_protected_sorted_and_filters_tombstones(
    tmp_path: Path,
) -> None:
    async with running_record_app(tmp_path / "KnowRealm") as (app, client):
        headers = {"X-KnowRealm-Token": TOKEN}
        created = await client.post(
            "/api/courses",
            headers=headers,
            json={
                "name": "操作系统",
                "learning_context": "SCHOOL",
                "education_stage": "UNDERGRADUATE",
            },
        )
        course_id = created.json()["id"]

        assert (await client.get(f"/api/courses/{course_id}/records", headers=headers)).json() == []

        async with app.state.session_factory() as session, session.begin():
            for index, status in enumerate(STATUSES, start=1):
                await session.execute(
                    text(
                        """
                        INSERT INTO records (
                            id, course_id, capture_type, title, status, duration_ms,
                            summary_confirmed_at, created_at, updated_at, deleted_at
                        ) VALUES (
                            :id, :course_id, :capture_type, :title, :status, :duration_ms,
                            NULL, :created_at, :created_at, NULL
                        )
                        """
                    ),
                    {
                        "id": f"record-{index}",
                        "course_id": course_id,
                        "capture_type": "RECORDING" if index == 1 else "QUICK_NOTE",
                        "title": "第一节" if index == 1 else f"记录 {index}",
                        "status": status,
                        "duration_ms": 65_000 if index == 1 else 0,
                        "created_at": f"2026-08-{index:02d}T08:00:00.000000Z",
                    },
                )
            await session.execute(
                text(
                    """
                    INSERT INTO records (
                        id, course_id, capture_type, title, status, duration_ms,
                        summary_confirmed_at, created_at, updated_at, deleted_at
                    ) VALUES (
                        'record-deleted', :course_id, 'PASTE', '墓碑', 'NOTE', 0,
                        NULL, '2026-08-31T08:00:00.000000Z',
                        '2026-08-31T08:00:00.000000Z', '2026-08-31T09:00:00.000000Z'
                    )
                    """
                ),
                {"course_id": course_id},
            )

        response = await client.get(f"/api/courses/{course_id}/records", headers=headers)

        assert response.status_code == 200
        assert [record["status"] for record in response.json()] == list(reversed(STATUSES))
        assert response.json()[-1] == {
            "id": "record-1",
            "course_id": course_id,
            "capture_type": "RECORDING",
            "title": "第一节",
            "status": "NOTE",
            "duration_ms": 65_000,
            "summary_confirmed_at": None,
            "created_at": "2026-08-01T08:00:00.000000Z",
            "updated_at": "2026-08-01T08:00:00.000000Z",
        }
        assert all("deleted_at" not in record for record in response.json())
        assert (await client.get(f"/api/courses/{course_id}/records")).status_code == 403
        assert (
            await client.get(
                f"/api/courses/{course_id}/records",
                headers={"X-KnowRealm-Token": "wrong"},
            )
        ).status_code == 403
        assert (
            await client.get(
                "/api/courses/00000000-0000-4000-8000-000000000000/records",
                headers=headers,
            )
        ).status_code == 404
        assert (
            await client.get("/api/courses/not-a-uuid/records", headers=headers)
        ).status_code == 422


@pytest.mark.anyio
async def test_record_detail_api_enforces_record_and_parent_visibility(
    tmp_path: Path,
) -> None:
    async with running_record_app(tmp_path / "KnowRealm") as (app, client):
        headers = {"X-KnowRealm-Token": TOKEN}
        visible_course = await client.post(
            "/api/courses",
            headers=headers,
            json={
                "name": "可见课程",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        deleted_course = await client.post(
            "/api/courses",
            headers=headers,
            json={
                "name": "已删除课程",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        visible_course_id = visible_course.json()["id"]
        deleted_course_id = deleted_course.json()["id"]
        record_ids = {
            "visible": "22222222-2222-4222-8222-222222222222",
            "inbox": "33333333-3333-4333-8333-333333333333",
            "deleted": "44444444-4444-4444-8444-444444444444",
            "deleted_parent": "55555555-5555-4555-8555-555555555555",
        }
        async with app.state.session_factory() as session, session.begin():
            for name, record_id in record_ids.items():
                course_id = {
                    "visible": visible_course_id,
                    "inbox": None,
                    "deleted": visible_course_id,
                    "deleted_parent": deleted_course_id,
                }[name]
                await session.execute(
                    text(
                        """
                        INSERT INTO records (
                            id, course_id, capture_type, title, status, duration_ms,
                            summary_confirmed_at, created_at, updated_at, deleted_at
                        ) VALUES (
                            :id, :course_id, 'QUICK_NOTE', :title, 'NOTE', 0,
                            NULL, '2026-08-19T08:00:00.000000Z',
                            '2026-08-19T08:00:00.000000Z', :deleted_at
                        )
                        """
                    ),
                    {
                        "id": record_id,
                        "course_id": course_id,
                        "title": name,
                        "deleted_at": (
                            "2026-08-19T09:00:00.000000Z" if name == "deleted" else None
                        ),
                    },
                )
            await session.execute(
                text(
                    "UPDATE courses SET deleted_at = '2026-08-19T09:00:00.000000Z' WHERE id = :id"
                ),
                {"id": deleted_course_id},
            )

        visible = await client.get(
            f"/api/records/{record_ids['visible']}",
            headers=headers,
        )
        inbox = await client.get(
            f"/api/records/{record_ids['inbox']}",
            headers=headers,
        )

        assert visible.status_code == 200
        assert visible.json()["course_id"] == visible_course_id
        assert "deleted_at" not in visible.json()
        assert inbox.status_code == 200
        assert inbox.json()["course_id"] is None
        for record_id in (
            record_ids["deleted"],
            record_ids["deleted_parent"],
            "66666666-6666-4666-8666-666666666666",
        ):
            assert (
                await client.get(f"/api/records/{record_id}", headers=headers)
            ).status_code == 404
        assert (await client.get(f"/api/records/{record_ids['visible']}")).status_code == 403
        assert (
            await client.get(
                f"/api/records/{record_ids['visible']}",
                headers={"X-KnowRealm-Token": "wrong"},
            )
        ).status_code == 403


@pytest.mark.anyio
async def test_record_delete_soft_deletes_visible_record_and_persists_after_restart(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    headers = {"X-KnowRealm-Token": TOKEN}
    record_id = "77777777-7777-4777-8777-777777777777"
    deleted_record_id = "88888888-8888-4888-8888-888888888888"
    hidden_parent_record_id = "99999999-9999-4999-8999-999999999999"

    async with running_record_app(data_dir) as (app, client):
        visible_course = await client.post(
            "/api/courses",
            headers=headers,
            json={
                "name": "可见课程",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        hidden_course = await client.post(
            "/api/courses",
            headers=headers,
            json={
                "name": "已删除课程",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        visible_course_id = visible_course.json()["id"]
        hidden_course_id = hidden_course.json()["id"]
        async with app.state.session_factory() as session, session.begin():
            for seeded_id, course_id, deleted_at in (
                (record_id, visible_course_id, None),
                (
                    deleted_record_id,
                    visible_course_id,
                    "2026-08-19T09:00:00.000000Z",
                ),
                (hidden_parent_record_id, hidden_course_id, None),
            ):
                await session.execute(
                    text(
                        """
                        INSERT INTO records (
                            id, course_id, capture_type, title, status, duration_ms,
                            summary_confirmed_at, created_at, updated_at, deleted_at
                        ) VALUES (
                            :id, :course_id, 'QUICK_NOTE', '待删除记录', 'NOTE', 0,
                            NULL, '2026-08-19T08:00:00.000000Z',
                            '2026-08-19T08:00:00.000000Z', :deleted_at
                        )
                        """
                    ),
                    {
                        "id": seeded_id,
                        "course_id": course_id,
                        "deleted_at": deleted_at,
                    },
                )
            await session.execute(
                text(
                    "UPDATE courses SET deleted_at = '2026-08-19T09:00:00.000000Z' WHERE id = :id"
                ),
                {"id": hidden_course_id},
            )

        assert (await client.delete(f"/api/records/{record_id}")).status_code == 403
        assert (
            await client.delete(
                f"/api/records/{record_id}",
                headers={"X-KnowRealm-Token": "wrong"},
            )
        ).status_code == 403
        deleted = await client.delete(f"/api/records/{record_id}", headers=headers)

        assert deleted.status_code == 204
        assert deleted.content == b""
        assert (
            await client.get(f"/api/courses/{visible_course_id}/records", headers=headers)
        ).json() == []
        assert (await client.get(f"/api/records/{record_id}", headers=headers)).status_code == 404
        for invisible_id in (
            record_id,
            deleted_record_id,
            hidden_parent_record_id,
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        ):
            assert (
                await client.delete(f"/api/records/{invisible_id}", headers=headers)
            ).status_code == 404

        async with app.state.session_factory() as session:
            deleted_at, updated_at = (
                await session.execute(
                    text("SELECT deleted_at, updated_at FROM records WHERE id = :record_id"),
                    {"record_id": record_id},
                )
            ).one()
            hidden_parent_deleted_at = (
                await session.execute(
                    text("SELECT deleted_at FROM records WHERE id = :record_id"),
                    {"record_id": hidden_parent_record_id},
                )
            ).scalar_one()
        assert deleted_at == updated_at
        assert deleted_at > "2026-08-19T08:00:00.000000Z"
        assert hidden_parent_deleted_at is None

    async with running_record_app(data_dir) as (_app, restarted_client):
        assert (
            await restarted_client.get(
                f"/api/courses/{visible_course_id}/records",
                headers=headers,
            )
        ).json() == []
        assert (
            await restarted_client.get(f"/api/records/{record_id}", headers=headers)
        ).status_code == 404


@pytest.mark.anyio
async def test_record_delete_cancels_only_nonterminal_jobs(tmp_path: Path) -> None:
    async with running_record_app(tmp_path / "KnowRealm") as (app, client):
        headers = {"X-KnowRealm-Token": TOKEN}
        course = await client.post(
            "/api/courses",
            headers=headers,
            json={
                "name": "操作系统",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        record_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    """
                    INSERT INTO records (
                        id, course_id, capture_type, title, status, duration_ms,
                        summary_confirmed_at, created_at, updated_at, deleted_at
                    ) VALUES (
                        :record_id, :course_id, 'DOCUMENT_IMPORT', '待删除文档',
                        'CONTENT_PROCESSING', 0, NULL,
                        '2026-08-19T08:00:00.000000Z',
                        '2026-08-19T08:00:00.000000Z', NULL
                    )
                    """
                ),
                {"record_id": record_id, "course_id": course.json()["id"]},
            )
            for status in ("PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"):
                await session.execute(
                    text(
                        """
                        INSERT INTO processing_jobs (
                            id, record_id, job_type, status, progress, attempts,
                            max_attempts, next_run_at, input_json, result_json,
                            error_code, error_message, started_at, finished_at,
                            created_at, updated_at
                        ) VALUES (
                            :id, :record_id, 'DOCUMENT_PARSE', :status, 0, 0,
                            3, :next_run_at, '{}', NULL, NULL, NULL, NULL, NULL,
                            '2026-08-19T08:00:00.000000Z',
                            '2026-08-19T08:00:00.000000Z'
                        )
                        """
                    ),
                    {
                        "id": f"job-{status.lower()}",
                        "record_id": record_id,
                        "status": status,
                        "next_run_at": (
                            "2099-01-01T00:00:00.000000Z" if status == "PENDING" else None
                        ),
                    },
                )

        deleted = await client.delete(f"/api/records/{record_id}", headers=headers)
        repeated = await client.delete(f"/api/records/{record_id}", headers=headers)
        assert deleted.status_code == 204
        assert repeated.status_code == 404

        async with app.state.session_factory() as session:
            jobs = (
                await session.execute(
                    text(
                        "SELECT id, status, finished_at FROM processing_jobs "
                        "WHERE record_id = :record_id ORDER BY id"
                    ),
                    {"record_id": record_id},
                )
            ).all()
        assert [(job.id, job.status) for job in jobs] == [
            ("job-cancelled", "CANCELLED"),
            ("job-failed", "FAILED"),
            ("job-pending", "CANCELLED"),
            ("job-running", "CANCELLED"),
            ("job-succeeded", "SUCCEEDED"),
        ]
        assert all(
            job.finished_at is not None for job in jobs if job.id in {"job-pending", "job-running"}
        )


@pytest.mark.anyio
async def test_record_delete_rolls_back_when_tombstone_write_fails(tmp_path: Path) -> None:
    async with running_record_app(tmp_path / "KnowRealm") as (app, client):
        headers = {"X-KnowRealm-Token": TOKEN}
        course = await client.post(
            "/api/courses",
            headers=headers,
            json={
                "name": "事务课程",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        course_id = course.json()["id"]
        record_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    """
                    INSERT INTO records (
                        id, course_id, capture_type, title, status, duration_ms,
                        summary_confirmed_at, created_at, updated_at, deleted_at
                    ) VALUES (
                        :record_id, :course_id, 'QUICK_NOTE', '事务记录', 'NOTE', 0,
                        NULL, '2026-08-19T08:00:00.000000Z',
                        '2026-08-19T08:00:00.000000Z', NULL
                    );
                    """
                ),
                {"record_id": record_id, "course_id": course_id},
            )
            await session.execute(
                text(
                    """
                    CREATE TRIGGER fail_record_soft_delete
                    BEFORE UPDATE OF deleted_at ON records
                    WHEN NEW.deleted_at IS NOT NULL
                    BEGIN
                        SELECT RAISE(ABORT, 'forced record update failure');
                    END
                    """
                )
            )

        failed = await client.delete(f"/api/records/{record_id}", headers=headers)

        assert failed.status_code == 500
        assert (await client.get(f"/api/records/{record_id}", headers=headers)).status_code == 200
        async with app.state.session_factory() as session:
            tombstone = (
                await session.execute(
                    text("SELECT deleted_at, updated_at FROM records WHERE id = :record_id"),
                    {"record_id": record_id},
                )
            ).one()
        assert tombstone == (None, "2026-08-19T08:00:00.000000Z")


@pytest.mark.anyio
async def test_deleting_course_soft_deletes_its_records_in_one_transaction(
    tmp_path: Path,
) -> None:
    async with running_record_app(tmp_path / "KnowRealm") as (app, client):
        headers = {"X-KnowRealm-Token": TOKEN}
        created = await client.post(
            "/api/courses",
            headers=headers,
            json={
                "name": "数据库系统",
                "learning_context": "SCHOOL",
                "education_stage": "UNDERGRADUATE",
            },
        )
        course_id = created.json()["id"]
        async with app.state.session_factory() as session, session.begin():
            for record_id in ("record-a", "record-b"):
                await session.execute(
                    text(
                        """
                        INSERT INTO records (
                            id, course_id, capture_type, title, status, duration_ms,
                            summary_confirmed_at, created_at, updated_at, deleted_at
                        ) VALUES (
                            :record_id, :course_id, 'QUICK_NOTE', '', 'NOTE', 0,
                            NULL, '2026-08-19T08:00:00.000000Z',
                            '2026-08-19T08:00:00.000000Z', NULL
                        )
                        """
                    ),
                    {"record_id": record_id, "course_id": course_id},
                )
                await session.execute(
                    text(
                        """
                        INSERT INTO processing_jobs (
                            id, record_id, job_type, status, progress, attempts,
                            max_attempts, next_run_at, input_json, result_json,
                            error_code, error_message, started_at, finished_at,
                            created_at, updated_at
                        ) VALUES (
                            :job_id, :record_id, 'DOCUMENT_PARSE', 'RUNNING', 0, 1,
                            3, NULL, '{}', NULL, NULL, NULL,
                            '2026-08-19T08:00:00.000000Z', NULL,
                            '2026-08-19T08:00:00.000000Z',
                            '2026-08-19T08:00:00.000000Z'
                        )
                        """
                    ),
                    {"job_id": f"job-{record_id}", "record_id": record_id},
                )

        deleted = await client.delete(f"/api/courses/{course_id}", headers=headers)

        assert deleted.status_code == 204
        assert (
            await client.get(f"/api/courses/{course_id}/records", headers=headers)
        ).status_code == 404
        async with app.state.session_factory() as session:
            course_deleted_at = (
                await session.execute(
                    text("SELECT deleted_at FROM courses WHERE id = :id"),
                    {"id": course_id},
                )
            ).scalar_one()
            record_tombstones = (
                await session.execute(
                    text(
                        "SELECT deleted_at, updated_at FROM records "
                        "WHERE course_id = :course_id ORDER BY id"
                    ),
                    {"course_id": course_id},
                )
            ).all()
            job_statuses = (
                (await session.execute(text("SELECT status FROM processing_jobs ORDER BY id")))
                .scalars()
                .all()
            )
        assert course_deleted_at is not None
        assert record_tombstones == [
            (course_deleted_at, course_deleted_at),
            (course_deleted_at, course_deleted_at),
        ]
        assert job_statuses == ["CANCELLED", "CANCELLED"]


@pytest.mark.anyio
async def test_course_delete_rolls_back_record_tombstones_when_parent_update_fails(
    tmp_path: Path,
) -> None:
    async with running_record_app(tmp_path / "KnowRealm") as (app, client):
        headers = {"X-KnowRealm-Token": TOKEN}
        created = await client.post(
            "/api/courses",
            headers=headers,
            json={
                "name": "事务课程",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        course_id = created.json()["id"]
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    """
                    INSERT INTO records (
                        id, course_id, capture_type, title, status, duration_ms,
                        summary_confirmed_at, created_at, updated_at, deleted_at
                    ) VALUES (
                        'record-rollback', :course_id, 'QUICK_NOTE', '', 'NOTE', 0,
                        NULL, '2026-08-19T08:00:00.000000Z',
                        '2026-08-19T08:00:00.000000Z', NULL
                    );
                    """
                ),
                {"course_id": course_id},
            )
            await session.execute(
                text(
                    """
                    INSERT INTO processing_jobs (
                        id, record_id, job_type, status, progress, attempts,
                        max_attempts, next_run_at, input_json, result_json,
                        error_code, error_message, started_at, finished_at,
                        created_at, updated_at
                    ) VALUES (
                        'job-rollback', 'record-rollback', 'DOCUMENT_PARSE',
                        'PENDING', 0, 0, 3, '2099-01-01T00:00:00.000000Z',
                        '{}', NULL, NULL, NULL, NULL, NULL,
                        '2026-08-19T08:00:00.000000Z',
                        '2026-08-19T08:00:00.000000Z'
                    )
                    """
                )
            )
            await session.execute(
                text(
                    """
                    CREATE TRIGGER fail_course_soft_delete
                    BEFORE UPDATE OF deleted_at ON courses
                    WHEN NEW.deleted_at IS NOT NULL
                    BEGIN
                        SELECT RAISE(ABORT, 'forced course update failure');
                    END
                    """
                )
            )

        failed = await client.delete(f"/api/courses/{course_id}", headers=headers)

        assert failed.status_code == 500
        async with app.state.session_factory() as session:
            course_deleted_at = (
                await session.execute(
                    text("SELECT deleted_at FROM courses WHERE id = :id"),
                    {"id": course_id},
                )
            ).scalar_one()
            record_deleted_at = (
                await session.execute(
                    text("SELECT deleted_at FROM records WHERE id = 'record-rollback'")
                )
            ).scalar_one()
            job_status = (
                await session.execute(
                    text("SELECT status FROM processing_jobs WHERE id = 'job-rollback'")
                )
            ).scalar_one()
        assert course_deleted_at is None
        assert record_deleted_at is None
        assert job_status == "PENDING"
        visible = await client.get(f"/api/courses/{course_id}/records", headers=headers)
        assert [record["id"] for record in visible.json()] == ["record-rollback"]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
