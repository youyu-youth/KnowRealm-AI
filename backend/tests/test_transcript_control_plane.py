import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.main import create_app

TOKEN = "test-launch-token"


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


async def seed_transcript_record(app: FastAPI, *, status: str = "SUMMARY_READY") -> str:
    record_id = str(uuid4())
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO records "
                "(id, course_id, capture_type, title, status, duration_ms, "
                "summary_confirmed_at, created_at, updated_at, deleted_at) "
                "VALUES (:id, NULL, 'AUDIO_IMPORT', '音频', :status, 1000, NULL, :now, :now, NULL)"
            ),
            {"id": record_id, "status": status, "now": now},
        )
        await session.execute(
            text(
                "INSERT INTO transcripts "
                "(id, record_id, language, content, source_version, edited_by_user, "
                "created_at, updated_at, deleted_at) "
                "VALUES (:id, :record_id, 'zh-CN', '旧正文', 1, 0, :now, :now, NULL)"
            ),
            {"id": str(uuid4()), "record_id": record_id, "now": now},
        )
    return record_id


@pytest.mark.anyio
async def test_transcript_patch_is_atomic_and_supersedes_existing_summary(tmp_path: Path) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        record_id = await seed_transcript_record(app)
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO ai_summaries "
                    "(id, record_id, version_no, transcript_source_version, topic, abstract, "
                    "summary_json, status, model, prompt_version, token_usage_json, latency_ms, "
                    "user_feedback, confirmed_at, created_at, updated_at, deleted_at) "
                    "VALUES (:id, :record_id, 1, 1, '主题', '摘要', '{}', 'CONFIRMED', "
                    "'model', 'v1', '{}', 1, NULL, :now, :now, :now, NULL)"
                ),
                {"id": str(uuid4()), "record_id": record_id, "now": now},
            )

        before = app.state.record_notifier.version(record_id)
        updated = await client.patch(
            f"/api/records/{record_id}/transcript",
            json={"content": "修正后的正文", "expected_source_version": 1},
        )
        stale = await client.patch(
            f"/api/records/{record_id}/transcript",
            json={"content": "静默覆盖", "expected_source_version": 1},
        )
        after = app.state.record_notifier.version(record_id)

        async with app.state.session_factory() as session:
            state = (
                await session.execute(
                    text(
                        "SELECT r.status, t.content, t.source_version, t.edited_by_user, "
                        "s.status, (SELECT count(*) FROM processing_jobs WHERE record_id=:id) "
                        "FROM records r JOIN transcripts t ON t.record_id=r.id "
                        "JOIN ai_summaries s ON s.record_id=r.id WHERE r.id=:id"
                    ),
                    {"id": record_id},
                )
            ).one()

    assert updated.status_code == 200
    assert updated.json()["source_version"] == 2
    assert stale.status_code == 409
    assert tuple(state) == ("SUMMARY_PENDING", "修正后的正文", 2, 1, "SUPERSEDED", 0)
    assert before != after


@pytest.mark.anyio
async def test_summary_processing_blocks_transcript_edit(tmp_path: Path) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        record_id = await seed_transcript_record(app, status="SUMMARY_PROCESSING")
        response = await client.patch(
            f"/api/records/{record_id}/transcript",
            json={"content": "不能写入", "expected_source_version": 1},
        )

    assert response.status_code == 409


@pytest.mark.anyio
async def test_manual_asr_retry_reuses_job_and_preserves_checkpoint(tmp_path: Path) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        record_id = await seed_transcript_record(app, status="FAILED")
        job_id = str(uuid4())
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        checkpoint = {
            "cursor": 1,
            "chunks": [
                {"index": 0, "status": "SUCCEEDED", "task_id": "11"},
                {"index": 1, "status": "FAILED", "task_id": "12"},
            ],
        }
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO processing_jobs "
                    "(id, record_id, job_type, status, progress, attempts, max_attempts, "
                    "next_run_at, waiting_reason, input_json, result_json, error_code, "
                    "error_message, started_at, finished_at, created_at, updated_at) "
                    "VALUES (:id, :record_id, 'ASR', 'FAILED', 0.5, 3, 3, NULL, NULL, '{}', "
                    ":result, 'ASR_RECOGNITION_FAILED', '失败', :now, :now, :now, :now)"
                ),
                {
                    "id": job_id,
                    "record_id": record_id,
                    "result": json.dumps(checkpoint),
                    "now": now,
                },
            )

        response = await client.post(
            f"/api/processing-jobs/{job_id}/retries",
            json={"record_id": record_id},
        )
        async with app.state.session_factory() as session:
            raw = (
                await session.execute(
                    text("SELECT result_json FROM processing_jobs WHERE id=:id"), {"id": job_id}
                )
            ).scalar_one()

    assert response.status_code == 202
    assert response.json()["id"] == job_id
    assert response.json()["status"] == "PENDING"
    assert response.json()["attempts"] == 0
    restored = cast(dict[str, object], json.loads(cast(str, raw)))
    chunks = cast(list[dict[str, object]], restored["chunks"])
    assert chunks[0] == {"index": 0, "status": "SUCCEEDED", "task_id": "11"}
    assert chunks[1] == {"index": 1, "status": "PENDING"}


@pytest.mark.anyio
async def test_deleting_record_cancels_jobs_and_removes_audio_cache(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with running_app(data_dir) as (app, client):
        record_id = await seed_transcript_record(app, status="CONTENT_PROCESSING")
        cache_file = data_dir / "cache" / "audio" / record_id / "chunks" / "chunk-00000.ogg"
        cache_file.parent.mkdir(parents=True)
        cache_file.write_bytes(b"cache")
        response = await client.delete(f"/api/records/{record_id}")

    assert response.status_code == 204
    assert not (data_dir / "cache" / "audio" / record_id).exists()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
