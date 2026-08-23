import asyncio
import json
import math
import shutil
import struct
import subprocess
import wave
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.main import create_app
from app.services.cache_lifecycle_service import CacheLifecycleService
from app.services.tencent_asr_client import (
    TencentAsrClient,
    TencentAsrCredentials,
    TencentAsrTask,
    TencentAsrTaskStatus,
)

TOKEN = "test-launch-token"


@asynccontextmanager
async def running_app(
    data_dir: Path,
    *,
    ffmpeg_path: Path | None = None,
    asr_client: TencentAsrClient | None = None,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(
        data_dir=data_dir,
        launch_token=TOKEN,
        ffmpeg_path=ffmpeg_path,
        asr_client=asr_client,
    )
    app.exception_handlers.pop(Exception, None)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client


async def wait_for_transcript(client: httpx.AsyncClient, record_id: str) -> dict[str, object]:
    for _ in range(250):
        response = await client.get(f"/api/records/{record_id}/transcript")
        assert response.status_code == 200
        payload = cast(dict[str, object], response.json())
        if payload["status"] == "READY":
            return cast(dict[str, object], payload["transcript"])
        await asyncio.sleep(0.02)
    pytest.fail("批次未发布 Transcript")


def wav_bytes() -> bytes:
    output = BytesIO()
    sample_rate = 16_000
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(
            b"".join(
                struct.pack("<h", int(8_000 * math.sin(2 * math.pi * 440 * i / sample_rate)))
                for i in range(sample_rate // 5)
            )
        )
    return output.getvalue()


class SuccessfulAsrClient(TencentAsrClient):
    async def is_online(self) -> bool:
        return True

    async def submit(
        self,
        path: Path,
        credentials: TencentAsrCredentials,
        config: dict[str, object],
    ) -> str:
        assert path.suffix == ".ogg"
        return "task-1"

    async def poll(
        self,
        task_id: str,
        credentials: TencentAsrCredentials,
    ) -> TencentAsrTask:
        return TencentAsrTask(status=TencentAsrTaskStatus.SUCCEEDED, text="audio body")


@pytest.mark.anyio
async def test_two_documents_are_registered_and_published_in_selection_order(
    tmp_path: Path,
) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        course = await client.post(
            "/api/courses",
            json={
                "name": "批次课程",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        response = await client.post(
            "/api/capture-batches",
            data={"course_id": course.json()["id"]},
            files=[
                ("files", ("first.txt", b"first body", "text/plain")),
                ("files", ("second.md", b"second body", "text/markdown")),
            ],
        )

        assert response.status_code == 202
        accepted = cast(dict[str, object], response.json())
        record_id = cast(str, accepted["record_id"])
        transcript = await wait_for_transcript(client, record_id)
        record = await client.get(f"/api/records/{record_id}")
        jobs = await client.get(f"/api/records/{record_id}/jobs")
        async with app.state.session_factory() as session:
            files = (
                await session.execute(
                    text(
                        "SELECT original_name, sequence_no FROM record_files "
                        "WHERE record_id = :record_id ORDER BY sequence_no"
                    ),
                    {"record_id": record_id},
                )
            ).all()

    assert accepted["job_ids"] and len(cast(list[str], accepted["job_ids"])) == 2
    assert record.json()["title"] == "first 等 2 个文件"
    assert record.json()["capture_type"] == "MULTI_SOURCE"
    assert files == [("first.txt", 0), ("second.md", 1)]
    assert [job["job_type"] for job in jobs.json()["jobs"]] == [
        "DOCUMENT_PARSE",
        "DOCUMENT_PARSE",
    ]
    assert transcript["content"] == "first body\n\nsecond body"
    assert transcript["language"] == "und"


@pytest.mark.anyio
async def test_audio_and_document_publish_one_transcript_in_selection_order(
    tmp_path: Path,
) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("真实 ffmpeg 不可用")
    data_dir = tmp_path / "KnowRealm"
    (data_dir / "config").mkdir(parents=True)
    (data_dir / "config" / "providers.json").write_text(
        '{"tencent_asr":{"secret_id":"id","secret_key":"key","region":"ap-shanghai"}}',
        encoding="utf-8",
    )
    (data_dir / "config" / "settings.json").write_text(
        '{"tencent_asr_consent_granted_at":"2026-08-23T00:00:00Z"}',
        encoding="utf-8",
    )
    async with running_app(
        data_dir,
        ffmpeg_path=Path(ffmpeg),
        asr_client=SuccessfulAsrClient(),
    ) as (_, client):
        course = await client.post(
            "/api/courses",
            json={
                "name": "混合课程",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        response = await client.post(
            "/api/capture-batches",
            data={"course_id": course.json()["id"]},
            files=[
                ("files", ("voice.wav", wav_bytes(), "audio/wav")),
                ("files", ("notes.txt", b"document body", "text/plain")),
            ],
        )
        assert response.status_code == 202
        transcript = await wait_for_transcript(client, response.json()["record_id"])

    assert transcript["content"] == "audio body\n\ndocument body"
    assert transcript["language"] == "und"


@pytest.mark.anyio
async def test_invalid_middle_source_rejects_the_whole_batch_without_business_rows(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with running_app(data_dir) as (app, client):
        course = await client.post(
            "/api/courses",
            json={
                "name": "原子预校验",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        response = await client.post(
            "/api/capture-batches",
            data={"course_id": course.json()["id"]},
            files=[
                ("files", ("first.txt", b"first", "text/plain")),
                ("files", ("broken.exe", b"broken", "application/octet-stream")),
                ("files", ("last.md", b"last", "text/markdown")),
            ],
        )
        async with app.state.session_factory() as session:
            counts: list[int | None] = []
            for table in ("records", "record_files", "processing_jobs"):
                counts.append(await session.scalar(text(f"SELECT count(*) FROM {table}")))

    assert response.status_code == 400
    assert response.json()["detail"].startswith("UNSUPPORTED_SOURCE")
    assert counts == [0, 0, 0]
    assert [
        path
        for path in data_dir.rglob("*")
        if path.is_file() and path.suffix != ".db" and path.name != ".knowrealm.lock"
    ] == []


@pytest.mark.anyio
async def test_sealed_recording_registers_final_ogg_before_deleting_webm_staging(
    tmp_path: Path,
) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("真实 ffmpeg 不可用")
    data_dir = tmp_path / "KnowRealm"
    staging = data_dir / "cache" / "staging" / "session"
    staging.mkdir(parents=True)
    source = tmp_path / "source.wav"
    source.write_bytes(wav_bytes())
    chunks = [staging / f"chunk-{index}.webm" for index in range(2)]
    for chunk in chunks:
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-c:a",
                "libopus",
                str(chunk),
            ],
            check=True,
        )

    async with running_app(data_dir, ffmpeg_path=Path(ffmpeg)) as (app, client):
        staging.mkdir(parents=True, exist_ok=True)
        for chunk in chunks:
            subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(source),
                    "-c:a",
                    "libopus",
                    str(chunk),
                ],
                check=True,
            )
        session_id = "11111111-1111-4111-8111-111111111111"
        now = "2026-08-23T00:00:00.000000Z"
        relative_chunks = [path.relative_to(data_dir).as_posix() for path in chunks]
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO recording_sessions "
                    "(id, course_id, title, started_at, updated_at, state, chunk_paths) "
                    "VALUES (:id, NULL, '封口录音', :now, :now, 'FINALIZING', :chunks)"
                ),
                {"id": session_id, "now": now, "chunks": json.dumps(relative_chunks)},
            )
        response = await client.post(
            "/api/capture-batches",
            data={"recording_session_id": session_id},
        )
        async with app.state.session_factory() as session:
            stored = (
                await session.execute(
                    text(
                        "SELECT source_type, file_path FROM record_files "
                        "WHERE record_id = :record_id"
                    ),
                    {"record_id": session_id},
                )
            ).one()
            state = await session.scalar(
                text("SELECT state FROM recording_sessions WHERE id = :id"),
                {"id": session_id},
            )

    assert response.status_code == 202
    assert stored[0] == "RECORDED"
    assert stored[1].endswith(".ogg")
    assert (data_dir / stored[1]).is_file()
    assert state == "DONE"
    assert all(not path.exists() for path in chunks)


@pytest.mark.anyio
async def test_startup_cleanup_keeps_only_staging_owned_by_an_active_recording(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with running_app(data_dir) as (app, _client):
        owned = data_dir / "cache" / "staging" / "owned.webm"
        orphan = data_dir / "cache" / "staging" / "orphan.webm"
        owned.parent.mkdir(parents=True, exist_ok=True)
        owned.write_bytes(b"owned")
        orphan.write_bytes(b"orphan")
        now = "2026-08-23T00:00:00.000000Z"
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO recording_sessions "
                    "(id, course_id, title, started_at, updated_at, state, chunk_paths) "
                    "VALUES (:id, NULL, NULL, :now, :now, 'PAUSED', :chunks)"
                ),
                {
                    "id": "22222222-2222-4222-8222-222222222222",
                    "now": now,
                    "chunks": json.dumps([owned.relative_to(data_dir).as_posix()]),
                },
            )
        await CacheLifecycleService.cleanup_orphans(app.state.session_factory, data_dir)

        assert owned.is_file()
        assert not orphan.exists()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
