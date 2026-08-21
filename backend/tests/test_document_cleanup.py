import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from loguru import logger
from sqlalchemy import text

from app.main import create_app
from app.services.document_cleanup_service import DocumentCleanupService

TOKEN = "test-launch-token"


@asynccontextmanager
async def running_cleanup_app(
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


async def create_course(client: httpx.AsyncClient, name: str) -> str:
    response = await client.post(
        "/api/courses",
        json={"name": name, "learning_context": "INTEREST", "depth": "BEGINNER"},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def import_document(
    client: httpx.AsyncClient,
    course_id: str,
    filename: str,
    content: bytes = b"same document",
) -> dict[str, str]:
    response = await client.post(
        "/api/document-imports",
        data={"course_id": course_id},
        files={"file": (filename, content, "text/plain")},
    )
    assert response.status_code == 202
    result: dict[str, str] = response.json()
    for _ in range(250):
        job = (await client.get(f"/api/processing-jobs/{result['job_id']}")).json()
        if job["status"] == "SUCCEEDED":
            return result
        await asyncio.sleep(0.02)
    pytest.fail("文档解析任务未完成")


def stored_file(data_dir: Path, record_id: str) -> Path:
    return next(path for path in (data_dir / "files" / record_id).iterdir() if path.is_file())


@pytest.mark.anyio
async def test_cleanup_honors_boundary_order_and_duplicate_isolation(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    now = datetime(2026, 8, 21, 12, tzinfo=UTC)
    async with running_cleanup_app(data_dir) as (app, client):
        active_course = await create_course(client, "保留课程")
        expired_course = await create_course(client, "到期课程")
        records = {
            "29天": await import_document(client, active_course, "same.txt"),
            "30天": await import_document(client, active_course, "same.txt"),
            "独立到期": await import_document(client, active_course, "same.txt"),
            "随课程到期": await import_document(client, expired_course, "same.txt"),
        }
        paths = {name: stored_file(data_dir, item["record_id"]) for name, item in records.items()}
        (paths["独立到期"].parent / ".parser.tmp").write_text("temporary", encoding="utf-8")
        paths["随课程到期"].unlink()

        deleted_at = {
            "29天": now - timedelta(days=29),
            "30天": now - timedelta(days=30),
            "独立到期": now - timedelta(days=30, microseconds=1),
            "随课程到期": now - timedelta(days=31),
        }
        async with app.state.session_factory() as session, session.begin():
            for name, item in records.items():
                timestamp = (
                    deleted_at[name].isoformat(timespec="microseconds").replace("+00:00", "Z")
                )
                await session.execute(
                    text("UPDATE records SET deleted_at = :deleted_at WHERE id = :id"),
                    {"deleted_at": timestamp, "id": item["record_id"]},
                )
            await session.execute(
                text("UPDATE courses SET deleted_at = :deleted_at WHERE id = :id"),
                {
                    "deleted_at": deleted_at["随课程到期"]
                    .isoformat(timespec="microseconds")
                    .replace("+00:00", "Z"),
                    "id": expired_course,
                },
            )
            await session.execute(
                text(
                    """
                    CREATE TRIGGER require_child_cleanup_before_course
                    BEFORE DELETE ON courses
                    WHEN EXISTS (SELECT 1 FROM records WHERE course_id = OLD.id)
                    BEGIN
                        SELECT RAISE(ABORT, 'records still exist');
                    END
                    """
                )
            )

        await DocumentCleanupService.purge_expired(
            app.state.session_factory,
            data_dir,
            now=now,
        )
        await DocumentCleanupService.purge_expired(
            app.state.session_factory,
            data_dir,
            now=now,
        )

        async with app.state.session_factory() as session:
            remaining_records = set(
                (await session.execute(text("SELECT id FROM records"))).scalars()
            )
            remaining_courses = set(
                (await session.execute(text("SELECT id FROM courses"))).scalars()
            )
            child_rows = {
                table: (
                    await session.execute(
                        text(f"SELECT count(*) FROM {table} WHERE record_id = :record_id"),
                        {"record_id": records["独立到期"]["record_id"]},
                    )
                ).scalar_one()
                for table in ("transcripts", "record_files", "processing_jobs")
            }

    assert remaining_records == {
        records["29天"]["record_id"],
        records["30天"]["record_id"],
    }
    assert expired_course not in remaining_courses
    assert active_course in remaining_courses
    assert child_rows == {"transcripts": 0, "record_files": 0, "processing_jobs": 0}
    assert paths["29天"].read_bytes() == b"same document"
    assert paths["30天"].read_bytes() == b"same document"
    assert not paths["独立到期"].parent.exists()
    assert not paths["随课程到期"].parent.exists()


@pytest.mark.anyio
async def test_cleanup_rejects_unsafe_or_active_paths_and_retries_file_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    now = datetime(2026, 8, 21, 12, tzinfo=UTC)
    async with running_cleanup_app(data_dir) as (app, client):
        course_id = await create_course(client, "路径保护")
        active = await import_document(client, course_id, "active.txt")
        traversal = await import_document(client, course_id, "traversal.txt")
        active_pointer = await import_document(client, course_id, "pointer.txt")
        file_failure = await import_document(client, course_id, "failure.txt")
        active_path = stored_file(data_dir, active["record_id"])
        failure_dir = stored_file(data_dir, file_failure["record_id"]).parent
        expired_at = (
            (now - timedelta(days=31)).isoformat(timespec="microseconds").replace("+00:00", "Z")
        )
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE records SET deleted_at = :deleted_at WHERE id IN (:a, :b, :c)"),
                {
                    "deleted_at": expired_at,
                    "a": traversal["record_id"],
                    "b": active_pointer["record_id"],
                    "c": file_failure["record_id"],
                },
            )
            await session.execute(
                text(
                    "UPDATE record_files SET file_path = '../../outside.txt' WHERE record_id = :id"
                ),
                {"id": traversal["record_id"]},
            )
            await session.execute(
                text("UPDATE record_files SET file_path = :path WHERE record_id = :id"),
                {
                    "path": active_path.relative_to(data_dir).as_posix(),
                    "id": active_pointer["record_id"],
                },
            )

        original_replace = os.replace

        def fail_one_move(source: Path, target: Path) -> None:
            if Path(source) == failure_dir:
                raise PermissionError("forced file failure")
            original_replace(source, target)

        monkeypatch.setattr("app.services.document_cleanup_service.os.replace", fail_one_move)
        await DocumentCleanupService.purge_expired(
            app.state.session_factory,
            data_dir,
            now=now,
        )

        async with app.state.session_factory() as session:
            remaining = set((await session.execute(text("SELECT id FROM records"))).scalars())
        assert {
            active["record_id"],
            traversal["record_id"],
            active_pointer["record_id"],
            file_failure["record_id"],
        } <= remaining
        assert active_path.exists()
        assert failure_dir.exists()

        monkeypatch.setattr("app.services.document_cleanup_service.os.replace", original_replace)
        await DocumentCleanupService.purge_expired(
            app.state.session_factory,
            data_dir,
            now=now,
        )
        async with app.state.session_factory() as session:
            remaining_after_retry = set(
                (await session.execute(text("SELECT id FROM records"))).scalars()
            )

    assert file_failure["record_id"] not in remaining_after_retry
    assert traversal["record_id"] in remaining_after_retry
    assert active_pointer["record_id"] in remaining_after_retry


@pytest.mark.anyio
async def test_cleanup_restores_files_after_database_failure_and_removes_proven_orphan(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    now = datetime(2026, 8, 21, 12, tzinfo=UTC)
    orphan_id = str(uuid4())
    orphan_file = data_dir / "files" / orphan_id / ".uncommitted.tmp"
    async with running_cleanup_app(data_dir) as (app, client):
        course_id = await create_course(client, "数据库恢复")
        expired = await import_document(client, course_id, "restore.txt")
        source = stored_file(data_dir, expired["record_id"])
        orphan_file.parent.mkdir(parents=True)
        orphan_file.write_bytes(b"orphan")
        expired_at = (
            (now - timedelta(days=31)).isoformat(timespec="microseconds").replace("+00:00", "Z")
        )
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE records SET deleted_at = :deleted_at WHERE id = :id"),
                {"deleted_at": expired_at, "id": expired["record_id"]},
            )
            await session.execute(
                text(
                    """
                    CREATE TRIGGER reject_cleanup BEFORE DELETE ON records
                    BEGIN
                        SELECT RAISE(ABORT, 'forced database failure');
                    END
                    """
                )
            )

        await DocumentCleanupService.purge_expired(
            app.state.session_factory,
            data_dir,
            now=now,
        )
        async with app.state.session_factory() as session:
            record_exists = (
                await session.execute(
                    text("SELECT count(*) FROM records WHERE id = :id"),
                    {"id": expired["record_id"]},
                )
            ).scalar_one()
        assert record_exists == 1
        assert source.read_bytes() == b"same document"
        assert not orphan_file.exists()

        async with app.state.session_factory() as session, session.begin():
            await session.execute(text("DROP TRIGGER reject_cleanup"))
        await DocumentCleanupService.purge_expired(
            app.state.session_factory,
            data_dir,
            now=now,
        )
        async with app.state.session_factory() as session:
            record_exists_after_retry = (
                await session.execute(
                    text("SELECT count(*) FROM records WHERE id = :id"),
                    {"id": expired["record_id"]},
                )
            ).scalar_one()

    assert record_exists_after_retry == 0
    assert not source.parent.exists()


@pytest.mark.anyio
async def test_compensation_failure_logs_and_leaves_a_proven_cleanup_orphan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    logs = StringIO()
    orphan_dirs: list[Path] = []
    sink_id = logger.add(logs, format="{message} {extra}", level="ERROR")
    try:
        async with running_cleanup_app(data_dir) as (app, client):
            course_id = await create_course(client, "补偿失败")
            async with app.state.session_factory() as session, session.begin():
                await session.execute(
                    text(
                        """
                        CREATE TRIGGER reject_import BEFORE INSERT ON records
                        BEGIN
                            SELECT RAISE(ABORT, 'forced import failure');
                        END
                        """
                    )
                )

            def fail_compensation(_path: Path) -> None:
                raise PermissionError("forced compensation failure")

            monkeypatch.setattr(
                "app.services.document_import_service._remove_import_file",
                fail_compensation,
            )
            failed = await client.post(
                "/api/document-imports",
                data={"course_id": course_id},
                files={"file": ("orphan.txt", b"orphan", "text/plain")},
            )
            orphan_dirs = list((data_dir / "files").iterdir())
            assert failed.status_code == 500
            assert len(orphan_dirs) == 1

            await DocumentCleanupService.purge_expired(
                app.state.session_factory,
                data_dir,
            )
    finally:
        logger.remove(sink_id)

    assert "DOCUMENT_IMPORT_COMPENSATION_FAILED" in logs.getvalue()
    assert not orphan_dirs[0].exists()


@pytest.mark.anyio
async def test_startup_cleanup_removes_expired_document_assets(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with running_cleanup_app(data_dir) as (app, client):
        course_id = await create_course(client, "重启清理")
        imported = await import_document(client, course_id, "restart.txt")
        source = stored_file(data_dir, imported["record_id"])
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE records SET deleted_at = '2020-01-01T00:00:00.000000Z' WHERE id = :id"
                ),
                {"id": imported["record_id"]},
            )

    async with running_cleanup_app(data_dir) as (app, _client):
        async with app.state.session_factory() as session:
            remaining = (
                await session.execute(
                    text("SELECT count(*) FROM records WHERE id = :id"),
                    {"id": imported["record_id"]},
                )
            ).scalar_one()

    assert remaining == 0
    assert not source.parent.exists()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
