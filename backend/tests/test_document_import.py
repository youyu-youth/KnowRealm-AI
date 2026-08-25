import asyncio
import errno
import threading
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4
from zipfile import ZipFile

import aiosqlite
import httpx
import pymupdf
import pytest
from docx import Document
from fastapi import FastAPI
from loguru import logger
from sqlalchemy import text

from app.db.migrations import MIGRATIONS_DIR, run_migrations
from app.main import create_app
from app.models.document import ProcessingJob
from app.services.document_worker import DocumentWorker
from app.services.processing_job_service import ProcessingJobService

TOKEN = "test-launch-token"


@asynccontextmanager
async def running_document_app(
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


async def wait_for_terminal_job(
    client: httpx.AsyncClient,
    job_id: str,
) -> dict[str, object]:
    for _ in range(250):
        response = await client.get(f"/api/processing-jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return job
        await asyncio.sleep(0.02)
    pytest.fail("文档解析任务未进入终态")


def pdf_bytes() -> bytes:
    document = pymupdf.open()
    for page_text in ("PDF page one", "", "PDF page three"):
        page = document.new_page()
        if page_text:
            page.insert_text(  # pyright: ignore[reportUnknownMemberType]
                (72, 72), page_text
            )
    content = document.tobytes()  # pyright: ignore[reportUnknownMemberType]
    document.close()
    return content


def docx_bytes() -> bytes:
    document = Document()
    document.sections[0].header.paragraphs[0].text = "excluded header"
    document.add_paragraph("DOCX first paragraph")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "left cell"
    table.rows[0].cells[1].text = "right cell"
    document.add_paragraph("DOCX last paragraph")
    document.sections[0].footer.paragraphs[0].text = "excluded footer"
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def corrupt_docx_bytes() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("word/document.xml", "<document />")
    return output.getvalue()


def malformed_xml_docx_bytes() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types>")
    return output.getvalue()


def password_pdf_bytes() -> bytes:
    document = pymupdf.open()
    document.new_page().insert_text(  # pyright: ignore[reportUnknownMemberType]
        (72, 72), "secret text"
    )
    content = document.tobytes(  # pyright: ignore[reportUnknownMemberType]
        encryption=pymupdf.PDF_ENCRYPT_AES_256,  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue, reportUnknownArgumentType]
        owner_pw="owner",
        user_pw="secret",
    )
    document.close()
    return content


def image_only_pdf_bytes() -> bytes:
    document = pymupdf.open()
    document.new_page()
    content = document.tobytes()  # pyright: ignore[reportUnknownMemberType]
    document.close()
    return content


async def assert_document_import_schema(db_path: Path) -> None:
    async with aiosqlite.connect(db_path) as connection:
        version = await (await connection.execute("PRAGMA user_version")).fetchone()
        tables = {
            row[0]
            for row in await (
                await connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            ).fetchall()
        }
        record_file_columns = await (
            await connection.execute("PRAGMA table_info(record_files)")
        ).fetchall()
        processing_job_indexes = await (
            await connection.execute("PRAGMA index_list(processing_jobs)")
        ).fetchall()

    assert version == (10,)
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
            await connection.executescript((MIGRATIONS_DIR / migration).read_text(encoding="utf-8"))
        await connection.execute("PRAGMA user_version=2")
        await connection.commit()
    await run_migrations(upgraded_db)

    await assert_document_import_schema(fresh_db)
    await assert_document_import_schema(upgraded_db)


@pytest.mark.anyio
async def test_txt_import_preserves_file_and_builds_real_transcript(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    source = b"\xef\xbb\xbfline one\r\n# heading\rline three"

    async with running_document_app(data_dir) as (app, client):
        course = await client.post(
            "/api/courses",
            json={
                "name": "操作系统",
                "learning_context": "SCHOOL",
                "education_stage": "UNDERGRADUATE",
            },
        )
        accepted = await client.post(
            "/api/document-imports",
            data={"course_id": course.json()["id"]},
            files={"file": ("Lecture.TXT", source, "text/plain")},
        )

        assert accepted.status_code == 202
        accepted_body = accepted.json()
        job = await wait_for_terminal_job(client, accepted_body["job_id"])
        record = await client.get(f"/api/records/{accepted_body['record_id']}")
        transcript = await client.get(f"/api/records/{accepted_body['record_id']}/transcript")
        notification_version = app.state.record_notifier.version(accepted_body["record_id"])

    assert job["status"] == "SUCCEEDED"
    assert job["record_id"] == accepted_body["record_id"]
    assert record.json()["title"] == "Lecture"
    assert record.json()["capture_type"] == "DOCUMENT_IMPORT"
    assert record.json()["status"] == "SUMMARY_PENDING"
    assert transcript.json()["status"] == "READY"
    assert transcript.json()["transcript"]["language"] == "und"
    assert transcript.json()["transcript"]["content"] == ("line one\n# heading\nline three")
    assert notification_version > 0
    stored_files = list((data_dir / "files" / accepted_body["record_id"]).iterdir())
    assert len(stored_files) == 1
    assert stored_files[0].read_bytes() == source


@pytest.mark.anyio
async def test_md_pdf_and_docx_extract_source_text_in_document_order(tmp_path: Path) -> None:
    cases = (
        (
            "notes.MD",
            b"# Heading\r\n\r\n- item\r\n```py\r\nprint('ok')\r\n```",
            "# Heading\n\n- item\n```py\nprint('ok')\n```",
        ),
        ("slides.PDF", pdf_bytes(), "PDF page one\n\nPDF page three"),
        (
            "handout.DOCX",
            docx_bytes(),
            "DOCX first paragraph\nleft cell\tright cell\nDOCX last paragraph",
        ),
    )
    async with running_document_app(tmp_path / "KnowRealm") as (_app, client):
        course = await client.post(
            "/api/courses",
            json={
                "name": "编译原理",
                "learning_context": "SCHOOL",
                "education_stage": "UNDERGRADUATE",
            },
        )
        for filename, source, expected in cases:
            accepted = await client.post(
                "/api/document-imports",
                data={"course_id": course.json()["id"]},
                files={"file": (filename, source, "application/octet-stream")},
            )
            assert accepted.status_code == 202
            body = accepted.json()
            assert (await wait_for_terminal_job(client, body["job_id"]))["status"] == ("SUCCEEDED")
            transcript = await client.get(f"/api/records/{body['record_id']}/transcript")
            assert transcript.json()["transcript"]["content"] == expected


@pytest.mark.anyio
async def test_deterministic_parse_failures_expose_only_stable_codes(tmp_path: Path) -> None:
    cases = (
        ("legacy.txt", b"\xff\xfelegacy", "NON_UTF8_TEXT"),
        ("fake.pdf", b"this is plain text", "FORMAT_MISMATCH"),
        ("broken.pdf", b"%PDF-1.7\nbroken", "CORRUPT_DOCUMENT"),
        ("locked.pdf", password_pdf_bytes(), "PASSWORD_PROTECTED"),
        ("scan.pdf", image_only_pdf_bytes(), "NO_EXTRACTABLE_TEXT"),
        ("partial.docx", corrupt_docx_bytes(), "CORRUPT_DOCUMENT"),
        ("malformed.docx", malformed_xml_docx_bytes(), "CORRUPT_DOCUMENT"),
        ("blank.md", b" \r\n\t", "NO_EXTRACTABLE_TEXT"),
    )
    async with running_document_app(tmp_path / "KnowRealm") as (_app, client):
        course = await client.post(
            "/api/courses",
            json={
                "name": "确定性失败",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        for filename, source, expected_code in cases:
            accepted = await client.post(
                "/api/document-imports",
                data={"course_id": course.json()["id"]},
                files={"file": (filename, source, "application/octet-stream")},
            )
            assert accepted.status_code == 202
            body = accepted.json()
            job = await wait_for_terminal_job(client, body["job_id"])
            record = await client.get(f"/api/records/{body['record_id']}")
            transcript = await client.get(f"/api/records/{body['record_id']}/transcript")

            assert job == {
                "id": body["job_id"],
                "record_id": body["record_id"],
                "job_type": "DOCUMENT_PARSE",
                "status": "FAILED",
                "progress": 0.0,
                "attempts": 1,
                "max_attempts": 3,
                "error_code": expected_code,
                "retryable": False,
                "waiting_reason": None,
                "sequence_no": 0,
                "source_name": None,
            }
            assert record.json()["status"] == "FAILED"
            assert transcript.json() == {"status": "NOT_READY", "transcript": None}


@pytest.mark.anyio
async def test_temporary_io_retries_twice_then_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    clock = [datetime(2026, 8, 21, tzinfo=UTC)]

    def fail_twice(path: Path) -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise BlockingIOError(errno.EAGAIN, "temporary read failure")
        return path.read_text(encoding="utf-8")

    monkeypatch.setattr(
        "app.services.document_worker.extract_document_text",
        fail_twice,
    )
    monkeypatch.setattr("app.services.document_worker.utcnow", lambda: clock[0])
    async with running_document_app(tmp_path / "KnowRealm") as (app, client):
        course = await client.post(
            "/api/courses",
            json={
                "name": "自动恢复",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        accepted = await client.post(
            "/api/document-imports",
            data={"course_id": course.json()["id"]},
            files={"file": ("recover.txt", b"recovered", "text/plain")},
        )
        job_id = accepted.json()["job_id"]

        first_retry = None
        for _ in range(100):
            first_retry = (await client.get(f"/api/processing-jobs/{job_id}")).json()
            if first_retry["status"] == "PENDING" and first_retry["attempts"] == 1:
                break
            await asyncio.sleep(0.01)

        async with app.state.session_factory() as session:
            first_job = await session.get(ProcessingJob, job_id)
        assert first_job is not None
        assert first_job.next_run_at is not None
        assert first_job.next_run_at.replace(tzinfo=UTC) == clock[0] + timedelta(seconds=1)
        clock[0] += timedelta(seconds=1)

        second_retry = None
        for _ in range(100):
            second_retry = (await client.get(f"/api/processing-jobs/{job_id}")).json()
            if second_retry["status"] == "PENDING" and second_retry["attempts"] == 2:
                break
            await asyncio.sleep(0.01)
        async with app.state.session_factory() as session:
            second_job = await session.get(ProcessingJob, job_id)
        assert second_job is not None
        assert second_job.next_run_at is not None
        assert second_job.next_run_at.replace(tzinfo=UTC) == clock[0] + timedelta(seconds=2)
        clock[0] += timedelta(seconds=2)

        terminal = await wait_for_terminal_job(client, job_id)
        transcript = await client.get(f"/api/records/{accepted.json()['record_id']}/transcript")

    assert first_retry is not None
    assert first_retry["status"] == "PENDING"
    assert first_retry["attempts"] == 1
    assert second_retry is not None
    assert second_retry["status"] == "PENDING"
    assert second_retry["attempts"] == 2
    assert terminal["status"] == "SUCCEEDED"
    assert terminal["attempts"] == 3
    assert transcript.json()["transcript"]["content"] == "recovered"


@pytest.mark.anyio
async def test_exhausted_temporary_failure_can_retry_same_job_and_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fail_first_round(path: Path) -> str:
        nonlocal calls
        calls += 1
        if calls <= 3:
            raise BlockingIOError(errno.EAGAIN, "temporary read failure")
        return path.read_text(encoding="utf-8")

    monkeypatch.setattr(
        "app.services.document_worker.extract_document_text",
        fail_first_round,
    )
    data_dir = tmp_path / "KnowRealm"
    async with running_document_app(data_dir) as (_, client):
        course = await client.post(
            "/api/courses",
            json={
                "name": "手动恢复",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        accepted = await client.post(
            "/api/document-imports",
            data={"course_id": course.json()["id"]},
            files={"file": ("recover.txt", b"same source", "text/plain")},
        )
        body = accepted.json()
        exhausted = await wait_for_terminal_job(client, body["job_id"])
        failed_record = await client.get(f"/api/records/{body['record_id']}")

        retry = await client.post(
            f"/api/processing-jobs/{body['job_id']}/retries",
            json={"record_id": body["record_id"]},
        )
        succeeded = await wait_for_terminal_job(client, body["job_id"])
        recovered_record = await client.get(f"/api/records/{body['record_id']}")
        transcript = await client.get(f"/api/records/{body['record_id']}/transcript")

    assert exhausted["status"] == "FAILED"
    assert exhausted["attempts"] == 3
    assert exhausted["retryable"] is True
    assert failed_record.json()["status"] == "FAILED"
    assert retry.status_code == 202
    assert retry.json()["id"] == body["job_id"]
    assert retry.json()["record_id"] == body["record_id"]
    assert retry.json()["attempts"] == 0
    assert retry.json()["error_code"] is None
    assert succeeded["status"] == "SUCCEEDED"
    assert succeeded["attempts"] == 1
    assert recovered_record.json()["status"] == "SUMMARY_PENDING"
    assert transcript.json()["transcript"]["content"] == "same source"
    assert len(list((data_dir / "files" / body["record_id"]).iterdir())) == 1


@pytest.mark.anyio
async def test_restart_recovers_running_jobs_and_keeps_archived_course_transcript(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [datetime(2026, 8, 21, tzinfo=UTC)]
    monkeypatch.setattr("app.services.document_worker.utcnow", lambda: clock[0])
    data_dir = tmp_path / "KnowRealm"
    async with running_document_app(data_dir) as (_, client):
        course = await client.post(
            "/api/courses",
            json={
                "name": "重启恢复",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        accepted: list[dict[str, str]] = []
        for filename, content in (
            ("resume.txt", b"resume after restart"),
            ("exhausted.txt", b"manual retry required"),
            ("cancelled.txt", b"deleted before restart"),
        ):
            response = await client.post(
                "/api/document-imports",
                data={"course_id": course.json()["id"]},
                files={"file": (filename, content, "text/plain")},
            )
            accepted.append(cast(dict[str, str], response.json()))
        for item in accepted:
            assert (await wait_for_terminal_job(client, item["job_id"]))["status"] == ("SUCCEEDED")

    async with aiosqlite.connect(data_dir / "knowrealm.db") as connection:
        await connection.execute("PRAGMA foreign_keys=ON")
        await connection.execute(
            "UPDATE courses SET status = 'ARCHIVED' WHERE id = ?",
            (course.json()["id"],),
        )
        for attempts, item in zip((1, 3, 1), accepted, strict=True):
            await connection.execute(
                "DELETE FROM transcripts WHERE record_id = ?",
                (item["record_id"],),
            )
            await connection.execute(
                "UPDATE records SET status = 'CONTENT_PROCESSING' WHERE id = ?",
                (item["record_id"],),
            )
            await connection.execute(
                "UPDATE processing_jobs SET status = 'RUNNING', attempts = ?, "
                "error_code = NULL, error_message = NULL, next_run_at = NULL, "
                "finished_at = NULL WHERE id = ?",
                (attempts, item["job_id"]),
            )
        await connection.execute(
            "UPDATE records SET deleted_at = ? WHERE id = ?",
            (
                clock[0].isoformat(timespec="microseconds").replace("+00:00", "Z"),
                accepted[2]["record_id"],
            ),
        )
        await connection.commit()

    async with running_document_app(data_dir) as (app, client):
        async with app.state.session_factory() as session:
            pending_job = await session.get(ProcessingJob, accepted[0]["job_id"])
            cancelled_job = await session.get(ProcessingJob, accepted[2]["job_id"])
        assert pending_job is not None
        assert cancelled_job is not None
        assert pending_job.status == "PENDING"
        assert pending_job.next_run_at is not None
        assert pending_job.next_run_at.replace(tzinfo=UTC) == clock[0] + timedelta(seconds=2)
        assert cancelled_job.status == "CANCELLED"
        assert cancelled_job.attempts == 1
        clock[0] += timedelta(seconds=2)
        resumed = await wait_for_terminal_job(client, accepted[0]["job_id"])
        resumed_record = await client.get(f"/api/records/{accepted[0]['record_id']}")
        transcript = await client.get(f"/api/records/{accepted[0]['record_id']}/transcript")
        exhausted = await wait_for_terminal_job(client, accepted[1]["job_id"])
        exhausted_record = await client.get(f"/api/records/{accepted[1]['record_id']}")

    assert resumed["status"] == "SUCCEEDED"
    assert resumed["attempts"] == 2
    assert resumed_record.json()["status"] == "SUMMARY_PENDING"
    assert transcript.json()["transcript"]["content"] == "resume after restart"
    assert exhausted["status"] == "FAILED"
    assert exhausted["attempts"] == 3
    assert exhausted["error_code"] == "WORKER_INTERRUPTED"
    assert exhausted["retryable"] is True
    assert exhausted_record.json()["status"] == "FAILED"


@pytest.mark.anyio
async def test_sqlite_busy_requeues_running_job_without_stopping_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser_started = threading.Event()
    continue_parse = threading.Event()
    parse_calls = 0

    def gated_parse(path: Path) -> str:
        nonlocal parse_calls
        parse_calls += 1
        parser_started.set()
        if not continue_parse.wait(timeout=10):
            raise OSError("test parser gate timed out")
        return path.read_text(encoding="utf-8")

    monkeypatch.setattr(
        "app.services.document_worker.extract_document_text",
        gated_parse,
    )
    data_dir = tmp_path / "KnowRealm"
    async with running_document_app(data_dir) as (_, client):
        course = await client.post(
            "/api/courses",
            json={
                "name": "SQLite 恢复",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        accepted = await client.post(
            "/api/document-imports",
            data={"course_id": course.json()["id"]},
            files={"file": ("busy.txt", b"busy recovered", "text/plain")},
        )
        body = accepted.json()
        assert await asyncio.to_thread(parser_started.wait, 2)

        lock = await aiosqlite.connect(data_dir / "knowrealm.db")
        try:
            await lock.execute("BEGIN IMMEDIATE")
            continue_parse.set()
            await asyncio.sleep(7)
            await lock.rollback()
        finally:
            await lock.close()

        terminal = await wait_for_terminal_job(client, body["job_id"])
        transcript = await client.get(f"/api/records/{body['record_id']}/transcript")

    assert terminal["status"] == "SUCCEEDED"
    assert terminal["attempts"] == 2
    assert parse_calls == 2
    assert transcript.json()["transcript"]["content"] == "busy recovered"


@pytest.mark.anyio
async def test_manual_retry_rejects_invalid_jobs_without_partial_updates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with running_document_app(data_dir) as (app, client):
        course = await client.post(
            "/api/courses",
            json={
                "name": "非法重试",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        failed: list[dict[str, str]] = []
        for index in range(3):
            accepted = await client.post(
                "/api/document-imports",
                data={"course_id": course.json()["id"]},
                files={"file": (f"fake-{index}.pdf", b"not a pdf", "application/pdf")},
            )
            failed.append(cast(dict[str, str], accepted.json()))
        for item in failed:
            assert (await wait_for_terminal_job(client, item["job_id"]))["status"] == ("FAILED")

        succeeded = await client.post(
            "/api/document-imports",
            data={"course_id": course.json()["id"]},
            files={"file": ("done.txt", b"done", "text/plain")},
        )
        succeeded_body = cast(dict[str, str], succeeded.json())
        assert (await wait_for_terminal_job(client, succeeded_body["job_id"]))[
            "status"
        ] == "SUCCEEDED"

        deterministic = await client.post(
            f"/api/processing-jobs/{failed[0]['job_id']}/retries",
            json={"record_id": failed[0]["record_id"]},
        )
        mismatch = await client.post(
            f"/api/processing-jobs/{failed[0]['job_id']}/retries",
            json={"record_id": failed[1]["record_id"]},
        )
        invalid_record_id = await client.post(
            f"/api/processing-jobs/{failed[0]['job_id']}/retries",
            json={"record_id": "not-a-uuid"},
        )
        non_failed = await client.post(
            f"/api/processing-jobs/{succeeded_body['job_id']}/retries",
            json={"record_id": succeeded_body["record_id"]},
        )

        assert (await client.delete(f"/api/records/{failed[1]['record_id']}")).status_code == 204
        deleted_record = await client.post(
            f"/api/processing-jobs/{failed[1]['job_id']}/retries",
            json={"record_id": failed[1]["record_id"]},
        )

        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE processing_jobs SET error_code = 'SQLITE_BUSY' WHERE id = :job_id"),
                {"job_id": failed[2]["job_id"]},
            )
        busy_failure = await client.get(f"/api/processing-jobs/{failed[2]['job_id']}")
        release_parse = threading.Event()

        def gated_retry(_path: Path) -> str:
            if not release_parse.wait(timeout=5):
                raise TimeoutError("test retry parser gate timed out")
            return "retried once"

        monkeypatch.setattr(
            "app.services.document_worker.extract_document_text",
            gated_retry,
        )
        concurrent_retries = await asyncio.gather(
            client.post(
                f"/api/processing-jobs/{failed[2]['job_id']}/retries",
                json={"record_id": failed[2]["record_id"]},
            ),
            client.post(
                f"/api/processing-jobs/{failed[2]['job_id']}/retries",
                json={"record_id": failed[2]["record_id"]},
            ),
        )
        release_parse.set()
        assert sorted(response.status_code for response in concurrent_retries) == [202, 409]
        await wait_for_terminal_job(client, failed[2]["job_id"])
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE processing_jobs SET status = 'CANCELLED' WHERE id = :job_id"),
                {"job_id": failed[2]["job_id"]},
            )
        cancelled = await client.post(
            f"/api/processing-jobs/{failed[2]['job_id']}/retries",
            json={"record_id": failed[2]["record_id"]},
        )

        unchanged_failed = await client.get(f"/api/processing-jobs/{failed[0]['job_id']}")
        unchanged_succeeded = await client.get(f"/api/processing-jobs/{succeeded_body['job_id']}")
        unchanged_cancelled = await client.get(f"/api/processing-jobs/{failed[2]['job_id']}")

    assert deterministic.status_code == 409
    assert mismatch.status_code == 409
    assert invalid_record_id.status_code == 422
    assert non_failed.status_code == 409
    assert deleted_record.status_code == 404
    assert cancelled.status_code == 409
    assert unchanged_failed.json()["status"] == "FAILED"
    assert unchanged_failed.json()["attempts"] == 1
    assert unchanged_succeeded.json()["status"] == "SUCCEEDED"
    assert busy_failure.json()["error_code"] == "SQLITE_BUSY"
    assert busy_failure.json()["retryable"] is True
    assert unchanged_cancelled.json()["status"] == "CANCELLED"


@pytest.mark.anyio
async def test_unexpected_io_and_parser_errors_are_not_retryable_or_logged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    logs = StringIO()
    sink_id = logger.add(logs, format="{message} {extra}", level="ERROR")

    def fail_unexpected(_path: Path) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise FileNotFoundError("private-source-path")
        raise RuntimeError("private-document-content")

    monkeypatch.setattr(
        "app.services.document_worker.extract_document_text",
        fail_unexpected,
    )
    try:
        async with running_document_app(tmp_path / "KnowRealm") as (_, client):
            course = await client.post(
                "/api/courses",
                json={
                    "name": "不可恢复错误",
                    "learning_context": "INTEREST",
                    "depth": "BEGINNER",
                },
            )
            jobs: list[dict[str, str]] = []
            for index in range(2):
                accepted = await client.post(
                    "/api/document-imports",
                    data={"course_id": course.json()["id"]},
                    files={"file": (f"private-{index}.txt", b"private", "text/plain")},
                )
                jobs.append(cast(dict[str, str], accepted.json()))
            failures = [await wait_for_terminal_job(client, item["job_id"]) for item in jobs]

            async def fail_job_query(*_args: object) -> None:
                raise RuntimeError("private-job-query-stack")

            monkeypatch.setattr(ProcessingJobService, "get", fail_job_query)
            failed_query = await client.get(f"/api/processing-jobs/{jobs[0]['job_id']}")
    finally:
        logger.remove(sink_id)

    assert all(failure["status"] == "FAILED" for failure in failures)
    assert all(failure["attempts"] == 1 for failure in failures)
    assert all(failure["error_code"] == "INTERNAL_ERROR" for failure in failures)
    assert all(failure["retryable"] is False for failure in failures)
    assert failed_query.status_code == 500
    assert "private-source-path" not in logs.getvalue()
    assert "private-document-content" not in logs.getvalue()
    assert "private-job-query-stack" not in logs.getvalue()


@pytest.mark.anyio
async def test_import_rejects_invalid_boundaries_before_business_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with running_document_app(data_dir) as (app, client):
        active = await client.post(
            "/api/courses",
            json={
                "name": "可导入课程",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        archived = await client.post(
            "/api/courses",
            json={
                "name": "已归档课程",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE courses SET status = 'ARCHIVED' WHERE id = :id"),
                {"id": archived.json()["id"]},
            )

        wrong_token = await client.post(
            "/api/document-imports",
            headers={"X-KnowRealm-Token": "wrong"},
            data={"course_id": active.json()["id"]},
            files={"file": ("ok.txt", b"text", "text/plain")},
        )
        missing_course = await client.post(
            "/api/document-imports",
            files={"file": ("ok.txt", b"text", "text/plain")},
        )
        missing_file = await client.post(
            "/api/document-imports",
            data={"course_id": active.json()["id"]},
        )
        unknown_course = await client.post(
            "/api/document-imports",
            data={"course_id": str(uuid4())},
            files={"file": ("ok.txt", b"text", "text/plain")},
        )
        archived_course = await client.post(
            "/api/document-imports",
            data={"course_id": archived.json()["id"]},
            files={"file": ("ok.txt", b"text", "text/plain")},
        )
        empty = await client.post(
            "/api/document-imports",
            data={"course_id": active.json()["id"]},
            files={"file": ("empty.txt", b"", "text/plain")},
        )
        unsupported = await client.post(
            "/api/document-imports",
            data={"course_id": active.json()["id"]},
            files={"file": ("slides.pptx", b"data", "application/octet-stream")},
        )

        def disk_full(_path: object) -> SimpleNamespace:
            return SimpleNamespace(total=10, used=10, free=0)

        monkeypatch.setattr("app.services.document_import_service.shutil.disk_usage", disk_full)
        no_space = await client.post(
            "/api/document-imports",
            data={"course_id": active.json()["id"]},
            files={"file": ("large.txt", b"four", "text/plain")},
        )

        assert [
            wrong_token.status_code,
            missing_course.status_code,
            missing_file.status_code,
            unknown_course.status_code,
            archived_course.status_code,
            empty.status_code,
            unsupported.status_code,
            no_space.status_code,
        ] == [403, 422, 422, 404, 409, 400, 400, 507]
        assert (await client.get(f"/api/courses/{active.json()['id']}/records")).json() == []

    assert list((data_dir / "files").rglob("*")) == []


@pytest.mark.anyio
async def test_import_compensates_database_failure_and_allows_duplicate_content(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    source = b"same document"
    async with running_document_app(data_dir) as (app, client):
        course = await client.post(
            "/api/courses",
            json={
                "name": "重复导入",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        course_id = course.json()["id"]
        accepted: list[dict[str, str]] = []
        for _ in range(2):
            response = await client.post(
                "/api/document-imports",
                data={"course_id": course_id},
                files={"file": ("../same.txt", source, "text/plain")},
            )
            assert response.status_code == 202
            accepted.append(response.json())
        for item in accepted:
            assert (await wait_for_terminal_job(client, item["job_id"]))["status"] == ("SUCCEEDED")

        records = (await client.get(f"/api/courses/{course_id}/records")).json()
        assert {record["id"] for record in records} == {item["record_id"] for item in accepted}
        assert {record["title"] for record in records} == {"same"}
        stored_files = [path for path in (data_dir / "files").rglob("*.txt")]
        assert len(stored_files) == 2
        assert all(path.read_bytes() == source for path in stored_files)

        async with app.state.session_factory() as session, session.begin():
            hashes = (
                (await session.execute(text("SELECT content_hash FROM record_files")))
                .scalars()
                .all()
            )
            assert len(set(hashes)) == 1
            await session.execute(
                text(
                    "CREATE TRIGGER reject_document_record "
                    "BEFORE INSERT ON records BEGIN "
                    "SELECT RAISE(ABORT, 'forced failure'); END"
                )
            )

        failed = await client.post(
            "/api/document-imports",
            data={"course_id": course_id},
            files={"file": ("rejected.txt", b"rejected", "text/plain")},
        )
        assert failed.status_code == 500

    assert [path for path in (data_dir / "files").rglob("*") if path.is_file()] == (stored_files)


@pytest.mark.anyio
async def test_deleted_job_is_rechecked_after_claim_before_parsing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claimed = asyncio.Event()
    continue_after_delete = asyncio.Event()
    parser_calls = 0
    original_claim = DocumentWorker._claim_one  # pyright: ignore[reportPrivateUsage]

    async def gated_claim(worker: DocumentWorker) -> tuple[str, str, Path] | None:
        result = await original_claim(worker)
        if result is not None:
            claimed.set()
            await continue_after_delete.wait()
        return result

    def observe_parse(path: Path) -> str:
        nonlocal parser_calls
        parser_calls += 1
        return path.read_text(encoding="utf-8")

    monkeypatch.setattr(DocumentWorker, "_claim_one", gated_claim)
    monkeypatch.setattr(
        "app.services.document_worker.extract_document_text",
        observe_parse,
    )

    data_dir = tmp_path / "KnowRealm"
    async with running_document_app(data_dir) as (_app, client):
        course = await client.post(
            "/api/courses",
            json={
                "name": "删除竞态",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        accepted = await client.post(
            "/api/document-imports",
            data={"course_id": course.json()["id"]},
            files={"file": ("cancel.txt", b"must not parse", "text/plain")},
        )
        body = accepted.json()
        await asyncio.wait_for(claimed.wait(), timeout=2)

        assert (await client.delete(f"/api/records/{body['record_id']}")).status_code == 204
        continue_after_delete.set()

    async with aiosqlite.connect(data_dir / "knowrealm.db") as connection:
        job_cursor = await connection.execute(
            "SELECT status FROM processing_jobs WHERE id = ?",
            (body["job_id"],),
        )
        transcript_cursor = await connection.execute(
            "SELECT count(*) FROM transcripts WHERE record_id = ?",
            (body["record_id"],),
        )
        job_row = await job_cursor.fetchone()
        transcript_row = await transcript_cursor.fetchone()
        assert job_row is not None
        assert transcript_row is not None
        job_status = cast(str, job_row[0])
        transcript_count = cast(int, transcript_row[0])

    assert parser_calls == 0
    assert job_status == "CANCELLED"
    assert transcript_count == 0
    assert not (data_dir / "cache" / "sources" / body["record_id"]).exists()


@pytest.mark.anyio
async def test_delete_after_parse_before_commit_discards_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = asyncio.Event()
    continue_commit = asyncio.Event()
    original_succeed = DocumentWorker._succeed  # pyright: ignore[reportPrivateUsage]

    async def gated_succeed(
        worker: DocumentWorker,
        job_id: str,
        record_id: str,
        content: str,
    ) -> None:
        parsed.set()
        await continue_commit.wait()
        await original_succeed(worker, job_id, record_id, content)

    monkeypatch.setattr(DocumentWorker, "_succeed", gated_succeed)

    data_dir = tmp_path / "KnowRealm"
    async with running_document_app(data_dir) as (_app, client):
        course = await client.post(
            "/api/courses",
            json={
                "name": "提交前删除",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        accepted = await client.post(
            "/api/document-imports",
            data={"course_id": course.json()["id"]},
            files={"file": ("parsed.txt", b"discard this", "text/plain")},
        )
        body = accepted.json()
        await asyncio.wait_for(parsed.wait(), timeout=2)

        assert (await client.delete(f"/api/records/{body['record_id']}")).status_code == 204
        continue_commit.set()

    async with aiosqlite.connect(data_dir / "knowrealm.db") as connection:
        job_cursor = await connection.execute(
            "SELECT status FROM processing_jobs WHERE id = ?",
            (body["job_id"],),
        )
        transcript_cursor = await connection.execute(
            "SELECT count(*) FROM transcripts WHERE record_id = ?",
            (body["record_id"],),
        )
        job_row = await job_cursor.fetchone()
        transcript_row = await transcript_cursor.fetchone()
        assert job_row is not None
        assert transcript_row is not None
        job_status = cast(str, job_row[0])
        transcript_count = cast(int, transcript_row[0])

    assert job_status == "CANCELLED"
    assert transcript_count == 0


@pytest.mark.anyio
async def test_worker_claims_only_due_pending_job_from_persistent_queue(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    data_dir.mkdir()
    db_path = data_dir / "knowrealm.db"
    await run_migrations(db_path)
    record_id = "11111111-1111-4111-8111-111111111111"
    file_id = "22222222-2222-4222-8222-222222222222"
    job_id = "33333333-3333-4333-8333-333333333333"
    relative_file = f"files/{record_id}/{file_id}.txt"
    source_path = data_dir / relative_file
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"persistent queue")
    now = "2026-08-20T08:00:00.000000Z"
    async with aiosqlite.connect(db_path) as connection:
        await connection.execute("PRAGMA foreign_keys=ON")
        await connection.executescript(
            f"""
            INSERT INTO courses (
                id, name, learning_context, education_stage, depth,
                course_type, description, hot_words, status,
                created_at, updated_at, deleted_at
            ) VALUES (
                'course-due', '持久任务', 'INTEREST', NULL, 'BEGINNER',
                NULL, NULL, NULL, 'ACTIVE', '{now}', '{now}', NULL
            );
            INSERT INTO records (
                id, course_id, capture_type, title, status, duration_ms,
                summary_confirmed_at, created_at, updated_at, deleted_at
            ) VALUES (
                '{record_id}', 'course-due', 'DOCUMENT_IMPORT', '持久任务',
                'CONTENT_PROCESSING', 0, NULL, '{now}', '{now}', NULL
            );
            INSERT INTO record_files (
                id, record_id, file_type, source_type, file_path, original_name,
                mime_type, file_size, duration_ms, sequence_no, content_hash,
                created_at, updated_at, deleted_at
            ) VALUES (
                '{file_id}', '{record_id}', 'DOCUMENT', 'UPLOADED',
                '{relative_file}', 'persistent.txt', 'text/plain', 16, NULL, 0,
                'hash', '{now}', '{now}', NULL
            );
            INSERT INTO processing_jobs (
                id, record_id, job_type, status, progress, attempts, max_attempts,
                next_run_at, input_json, result_json, error_code, error_message,
                started_at, finished_at, created_at, updated_at
            ) VALUES (
                '{job_id}', '{record_id}', 'DOCUMENT_PARSE', 'PENDING', 0, 0, 3,
                '2099-01-01T00:00:00.000000Z',
                '{{"record_file_id":"{file_id}"}}', NULL, NULL, NULL,
                NULL, NULL, '{now}', '{now}'
            );
            """
        )
        await connection.commit()

    async with running_document_app(data_dir) as (app, client):
        pending = await client.get(f"/api/processing-jobs/{job_id}")
        await asyncio.sleep(0.15)
        still_pending = await client.get(f"/api/processing-jobs/{job_id}")
        assert pending.json()["status"] == "PENDING"
        assert still_pending.json()["attempts"] == 0

        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE processing_jobs SET next_run_at = NULL WHERE id = :job_id"),
                {"job_id": job_id},
            )
        terminal = await wait_for_terminal_job(client, job_id)
        transcript = await client.get(f"/api/records/{record_id}/transcript")

        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE records SET deleted_at = :now WHERE id = :record_id"),
                {"now": now, "record_id": record_id},
            )
            await session.execute(
                text(
                    "UPDATE processing_jobs SET status = 'PENDING', next_run_at = NULL "
                    "WHERE id = :job_id"
                ),
                {"job_id": job_id},
            )
        await asyncio.sleep(0.15)
        async with app.state.session_factory() as session:
            skipped = (
                await session.execute(
                    text("SELECT status, attempts FROM processing_jobs WHERE id = :job_id"),
                    {"job_id": job_id},
                )
            ).one()

    assert terminal["status"] == "SUCCEEDED"
    assert terminal["attempts"] == 1
    assert transcript.json()["transcript"]["content"] == "persistent queue"
    assert skipped == ("PENDING", 1)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
