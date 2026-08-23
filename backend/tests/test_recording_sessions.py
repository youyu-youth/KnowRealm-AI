from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest

from app.main import create_app

TOKEN = "test-launch-token"


def webm_bytes(seed: bytes = b"recording") -> bytes:
    return b"\x1aE\xdf\xa3" + seed


@asynccontextmanager
async def recording_client(data_dir: Path) -> AsyncGenerator[httpx.AsyncClient]:
    app = create_app(data_dir=data_dir, launch_token=TOKEN)
    app.exception_handlers.pop(Exception, None)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield client


@pytest.mark.anyio
async def test_create_and_list_single_active_recording(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with recording_client(data_dir) as client:
        created = await client.post("/api/recording-sessions", json={"title": "  算法课  "})
        duplicate = await client.post("/api/recording-sessions", json={})
        listing = await client.get("/api/recording-sessions")

        assert created.status_code == 201
        assert created.json()["title"] == "算法课"
        assert created.json()["state"] == "RECORDING"
        assert created.json()["recorded_duration_ms"] == 0
        assert created.json()["chunk_count"] == 0
        assert duplicate.status_code == 409
        assert listing.json() == [created.json()]


@pytest.mark.anyio
async def test_create_uses_timestamp_title_and_validates_course(tmp_path: Path) -> None:
    async with recording_client(tmp_path / "KnowRealm") as client:
        missing = await client.post(
            "/api/recording-sessions",
            json={"course_id": "00000000-0000-0000-0000-000000000001"},
        )
        created = await client.post("/api/recording-sessions", json={})

        assert missing.status_code == 404
        assert created.status_code == 201
        assert created.json()["title"].startswith("录音 ")


@pytest.mark.anyio
async def test_chunks_are_ordered_idempotent_and_sealed(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with recording_client(data_dir) as client:
        created = await client.post("/api/recording-sessions", json={})
        recording_id = created.json()["id"]

        first = await client.post(
            f"/api/recording-sessions/{recording_id}/chunks",
            data={"sequence_no": 0, "duration_ms": 20_000, "target_state": "PAUSED"},
            files={"file": ("0000.webm", webm_bytes(), "audio/webm")},
        )
        retry = await client.post(
            f"/api/recording-sessions/{recording_id}/chunks",
            data={"sequence_no": 0, "duration_ms": 20_000, "target_state": "PAUSED"},
            files={"file": ("0000.webm", webm_bytes(), "audio/webm")},
        )
        conflict = await client.post(
            f"/api/recording-sessions/{recording_id}/chunks",
            data={"sequence_no": 0, "duration_ms": 20_000, "target_state": "PAUSED"},
            files={"file": ("0000.webm", webm_bytes(b"different"), "audio/webm")},
        )
        gap = await client.post(
            f"/api/recording-sessions/{recording_id}/chunks",
            data={"sequence_no": 2, "duration_ms": 20_000, "target_state": "RECORDING"},
            files={"file": ("0002.webm", webm_bytes(b"gap"), "audio/webm")},
        )
        resumed = await client.patch(
            f"/api/recording-sessions/{recording_id}",
            json={"target_state": "RECORDING"},
        )
        final = await client.post(
            f"/api/recording-sessions/{recording_id}/chunks",
            data={"sequence_no": 1, "duration_ms": 15_000, "target_state": "FINALIZING"},
            files={"file": ("0001.webm", webm_bytes(b"final"), "audio/webm")},
        )

        assert first.status_code == 201
        assert retry.status_code == 201
        assert retry.json()["content_hash"] == first.json()["content_hash"]
        assert conflict.status_code == 409
        assert gap.status_code == 409
        assert resumed.json()["state"] == "RECORDING"
        assert final.json()["session"]["state"] == "FINALIZING"
        assert final.json()["session"]["chunk_count"] == 2
        assert final.json()["session"]["recorded_duration_ms"] == 35_000
        assert (data_dir / "cache" / "staging" / recording_id / "0000.webm").is_file()


@pytest.mark.anyio
async def test_paused_session_can_finalize_or_be_abandoned(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with recording_client(data_dir) as client:
        created = await client.post("/api/recording-sessions", json={})
        recording_id = created.json()["id"]
        await client.post(
            f"/api/recording-sessions/{recording_id}/chunks",
            data={"sequence_no": 0, "duration_ms": 10_000, "target_state": "PAUSED"},
            files={"file": ("0000.webm", webm_bytes(), "audio/webm")},
        )
        finalized = await client.patch(
            f"/api/recording-sessions/{recording_id}",
            json={"target_state": "FINALIZING"},
        )
        assert finalized.json()["state"] == "FINALIZING"
        assert (await client.delete(f"/api/recording-sessions/{recording_id}")).status_code == 409

    second_data_dir = tmp_path / "SecondKnowRealm"
    async with recording_client(second_data_dir) as client:
        created = await client.post("/api/recording-sessions", json={})
        recording_id = created.json()["id"]
        await client.post(
            f"/api/recording-sessions/{recording_id}/chunks",
            data={"sequence_no": 0, "duration_ms": 10_000, "target_state": "PAUSED"},
            files={"file": ("0000.webm", webm_bytes(), "audio/webm")},
        )
        abandoned = await client.delete(f"/api/recording-sessions/{recording_id}")
        assert abandoned.status_code == 204
        assert (await client.get("/api/recording-sessions")).json() == []
        assert not (second_data_dir / "cache" / "staging" / recording_id).exists()


@pytest.mark.anyio
async def test_crash_recovered_recording_with_saved_chunks_can_finalize(tmp_path: Path) -> None:
    async with recording_client(tmp_path / "KnowRealm") as client:
        created = await client.post("/api/recording-sessions", json={})
        recording_id = created.json()["id"]
        await client.post(
            f"/api/recording-sessions/{recording_id}/chunks",
            data={"sequence_no": 0, "duration_ms": 10_000, "target_state": "RECORDING"},
            files={"file": ("0000.webm", webm_bytes(), "audio/webm")},
        )

        finalized = await client.patch(
            f"/api/recording-sessions/{recording_id}",
            json={"target_state": "FINALIZING"},
        )

        assert finalized.status_code == 200
        assert finalized.json()["state"] == "FINALIZING"


@pytest.mark.anyio
async def test_deleting_course_moves_active_recording_to_inbox(tmp_path: Path) -> None:
    async with recording_client(tmp_path / "KnowRealm") as client:
        course = await client.post(
            "/api/courses",
            json={
                "name": "待删除课程",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        recording = await client.post(
            "/api/recording-sessions",
            json={"course_id": course.json()["id"]},
        )

        deleted = await client.delete(f"/api/courses/{course.json()['id']}")
        unfinished = await client.get("/api/recording-sessions")

        assert deleted.status_code == 204
        assert unfinished.json()[0]["id"] == recording.json()["id"]
        assert unfinished.json()[0]["course_id"] is None


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
