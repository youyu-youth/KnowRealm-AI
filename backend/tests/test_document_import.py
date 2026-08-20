import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from zipfile import ZipFile

import aiosqlite
import httpx
import pymupdf
import pytest
from docx import Document
from fastapi import FastAPI
from sqlalchemy import text

from app.db.migrations import MIGRATIONS_DIR, run_migrations
from app.main import create_app

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
    for _ in range(100):
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

    async with running_document_app(data_dir) as (_app, client):
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

    assert job["status"] == "SUCCEEDED"
    assert job["record_id"] == accepted_body["record_id"]
    assert record.json()["title"] == "Lecture"
    assert record.json()["capture_type"] == "DOCUMENT_IMPORT"
    assert record.json()["status"] == "SUMMARY_PENDING"
    assert transcript.json()["status"] == "READY"
    assert transcript.json()["transcript"]["language"] == "und"
    assert transcript.json()["transcript"]["content"] == ("line one\n# heading\nline three")
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
            }
            assert record.json()["status"] == "FAILED"
            assert transcript.json() == {"status": "NOT_READY", "transcript": None}


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
