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
from app.services.audio_worker import AudioWorker
from app.services.tencent_asr_client import (
    TencentAsrApiError,
    TencentAsrClient,
    TencentAsrCredentials,
    TencentAsrTask,
    TencentAsrTaskStatus,
)

TOKEN = "test-launch-token"
type JsonObject = dict[str, object]


def job_items(payload: JsonObject) -> list[JsonObject]:
    return cast(list[JsonObject], payload["jobs"])


def wav_bytes(*, seconds: float = 0.2) -> bytes:
    output = BytesIO()
    sample_rate = 16_000
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        frames = (
            struct.pack("<h", int(8_000 * math.sin(2 * math.pi * 440 * index / sample_rate)))
            for index in range(int(sample_rate * seconds))
        )
        audio.writeframes(b"".join(frames))
    return output.getvalue()


def ffmpeg_executable() -> Path:
    executable = shutil.which("ffmpeg")
    if executable is None:
        pytest.skip("真实 ffmpeg 不可用")
    return Path(executable).resolve()


def encoded_audio(tmp_path: Path, extension: str) -> bytes:
    source = tmp_path / "source.wav"
    source.write_bytes(wav_bytes())
    target = tmp_path / f"encoded{extension}"
    subprocess.run(
        [
            str(ffmpeg_executable()),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            str(target),
        ],
        check=True,
    )
    return target.read_bytes()


@asynccontextmanager
async def running_audio_app(
    data_dir: Path,
    *,
    asr_client: TencentAsrClient | None = None,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(
        data_dir=data_dir,
        launch_token=TOKEN,
        ffmpeg_path=ffmpeg_executable(),
        asr_client=asr_client,
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client


class FakeTencentAsrClient(TencentAsrClient):
    def __init__(self) -> None:
        self.online = False
        self.submitted: list[Path] = []

    async def is_online(self) -> bool:
        return self.online

    async def submit(
        self,
        path: Path,
        credentials: TencentAsrCredentials,
        config: dict[str, object],
    ) -> str:
        assert credentials.secret_id == "secret-id"
        assert config["engine_model_type"] == "16k_zh"
        self.submitted.append(path)
        return f"task-{len(self.submitted)}"

    async def poll(
        self,
        task_id: str,
        credentials: TencentAsrCredentials,
    ) -> TencentAsrTask:
        assert task_id.startswith("task-")
        assert credentials.region == "ap-shanghai"
        return TencentAsrTask(
            status=TencentAsrTaskStatus.SUCCEEDED,
            text="真实边界替身返回的正文。",
        )


class FailingPollTencentAsrClient(FakeTencentAsrClient):
    def __init__(self) -> None:
        super().__init__()
        self.online = True
        self.polls = 0
        self.regions: list[str] = []

    async def poll(
        self,
        task_id: str,
        credentials: TencentAsrCredentials,
    ) -> TencentAsrTask:
        self.polls += 1
        self.regions.append(credentials.region)
        raise TencentAsrApiError("InternalError")


class UnknownSubmitTencentAsrClient(FakeTencentAsrClient):
    def __init__(self) -> None:
        super().__init__()
        self.online = True

    async def submit(
        self,
        path: Path,
        credentials: TencentAsrCredentials,
        config: dict[str, object],
    ) -> str:
        request = httpx.Request("POST", "https://asr.tencentcloudapi.com")
        raise httpx.ReadTimeout("unknown", request=request)


class AuthFailingPollTencentAsrClient(FakeTencentAsrClient):
    def __init__(self) -> None:
        super().__init__()
        self.online = True
        self.authorized = False

    async def poll(
        self,
        task_id: str,
        credentials: TencentAsrCredentials,
    ) -> TencentAsrTask:
        if not self.authorized:
            raise TencentAsrApiError("AuthFailure.SignatureFailure")
        return await super().poll(task_id, credentials)


class BlockingPollTencentAsrClient(FakeTencentAsrClient):
    def __init__(self) -> None:
        super().__init__()
        self.online = True
        self.poll_started = asyncio.Event()
        self.release_poll = asyncio.Event()

    async def poll(
        self,
        task_id: str,
        credentials: TencentAsrCredentials,
    ) -> TencentAsrTask:
        self.poll_started.set()
        await self.release_poll.wait()
        return await super().poll(task_id, credentials)


class ExpiredPollTencentAsrClient(FakeTencentAsrClient):
    def __init__(self) -> None:
        super().__init__()
        self.online = True
        self.expired = True

    async def poll(
        self,
        task_id: str,
        credentials: TencentAsrCredentials,
    ) -> TencentAsrTask:
        if self.expired:
            raise TencentAsrApiError("FailedOperation.NoSuchTask")
        return await super().poll(task_id, credentials)


def write_asr_prerequisites(data_dir: Path) -> None:
    config = data_dir / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "settings.json").write_text(
        json.dumps({"tencent_asr_consent_granted_at": "2026-08-22T00:00:00Z"}),
        encoding="utf-8",
    )
    (config / "providers.json").write_text(
        json.dumps(
            {
                "tencent_asr": {
                    "secret_id": "secret-id",
                    "secret_key": "secret-key",
                    "region": "ap-shanghai",
                }
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.anyio
async def test_audio_import_registers_original_and_ordered_jobs_atomically(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with running_audio_app(data_dir) as (_app, client):
        accepted = await client.post(
            "/api/audio-imports",
            files={"file": ("../第一课.WAV", wav_bytes(), "audio/wav")},
        )

        assert accepted.status_code == 202
        body = accepted.json()
        record = await client.get(f"/api/records/{body['record_id']}")
        jobs = await client.get(f"/api/records/{body['record_id']}/jobs")

    assert record.json()["title"] == "第一课"
    assert record.json()["course_id"] is None
    assert record.json()["capture_type"] == "AUDIO_IMPORT"
    assert record.json()["status"] == "CONTENT_PROCESSING"
    assert [job["job_type"] for job in jobs.json()["jobs"]] == [
        "AUDIO_TRANSCODE",
        "ASR",
    ]
    assert 0 <= jobs.json()["progress"] <= 0.5
    originals = [path for path in (data_dir / "files").rglob("*.wav")]
    assert len(originals) == 1
    assert originals[0].read_bytes() == wav_bytes()
    assert "第一课" not in originals[0].as_posix()


@pytest.mark.anyio
async def test_audio_import_freezes_tencent_hot_word_format(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with running_audio_app(data_dir) as (app, client):
        course = await client.post(
            "/api/courses",
            json={
                "name": "术语课",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        course_id = course.json()["id"]
        assert (
            await client.patch(
                f"/api/courses/{course_id}",
                json={"hot_words": ["操作系统", "线程"]},
            )
        ).status_code == 200
        accepted = await client.post(
            "/api/audio-imports",
            data={"course_id": course_id},
            files={"file": ("lesson.wav", wav_bytes(), "audio/wav")},
        )
        async with app.state.session_factory() as session:
            input_json = await session.scalar(
                text("SELECT input_json FROM processing_jobs WHERE id=:id"),
                {"id": accepted.json()["asr_job_id"]},
            )

    assert json.loads(cast(str, input_json))["hot_words"] == "操作系统|5,线程|5"


@pytest.mark.anyio
async def test_audio_worker_transcodes_and_slices_before_waiting_for_consent(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with running_audio_app(data_dir) as (_app, client):
        accepted = await client.post(
            "/api/audio-imports",
            files={"file": ("lesson.wav", wav_bytes(seconds=1), "audio/wav")},
        )
        record_id = accepted.json()["record_id"]

        jobs: JsonObject | None = None
        for _ in range(250):
            response = await client.get(f"/api/records/{record_id}/jobs")
            jobs = cast(JsonObject, response.json())
            first, second = job_items(jobs)
            if first["status"] == "SUCCEEDED" and second["waiting_reason"] == "CONSENT_REQUIRED":
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("音频转码未完成")

    assert jobs is not None
    first, second = job_items(jobs)
    assert first["job_type"] == "AUDIO_TRANSCODE"
    assert first["attempts"] == 1
    assert second["job_type"] == "ASR"
    assert second["status"] == "PENDING"
    assert second["attempts"] == 0
    assert jobs["progress"] == 0.5
    chunks = list((data_dir / "cache" / "audio" / record_id).rglob("chunk-*.ogg"))
    assert chunks
    assert all(chunk.stat().st_size < 5 * 1024 * 1024 for chunk in chunks)


@pytest.mark.anyio
async def test_audio_import_accepts_mp3_aac_wav_and_m4a(tmp_path: Path) -> None:
    cases = (
        ("mp3", encoded_audio(tmp_path, ".mp3")),
        ("aac", encoded_audio(tmp_path, ".aac")),
        ("wav", wav_bytes()),
        ("m4a", encoded_audio(tmp_path, ".m4a")),
    )
    async with running_audio_app(tmp_path / "KnowRealm") as (_app, client):
        for extension, content in cases:
            response = await client.post(
                "/api/audio-imports",
                files={"file": (f"lesson.{extension}", content, "application/octet-stream")},
            )
            assert response.status_code == 202


@pytest.mark.anyio
async def test_audio_prevalidation_rejects_without_business_rows_or_formal_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with running_audio_app(data_dir) as (app, client):
        unsupported = await client.post(
            "/api/audio-imports",
            files={"file": ("lesson.flac", b"fLaC", "audio/flac")},
        )
        mismatch = await client.post(
            "/api/audio-imports",
            files={"file": ("lesson.mp3", wav_bytes(), "audio/mpeg")},
        )
        corrupt = await client.post(
            "/api/audio-imports",
            files={"file": ("lesson.wav", b"RIFF\x00\x00\x00\x00WAVEbroken", "audio/wav")},
        )

        async def too_long_probe(_ffmpeg_path: Path, _path: Path) -> int:
            return 5 * 60 * 60 * 1000 + 1

        with monkeypatch.context() as scoped:
            scoped.setattr(
                "app.services.audio_import_service.probe_audio_duration_ms",
                too_long_probe,
            )
            too_long = await client.post(
                "/api/audio-imports",
                files={"file": ("lesson.wav", wav_bytes(), "audio/wav")},
            )

        async with app.state.session_factory() as session:
            counts = tuple(
                (
                    await session.execute(
                        text(
                            "SELECT "
                            "(SELECT count(*) FROM records), "
                            "(SELECT count(*) FROM record_files), "
                            "(SELECT count(*) FROM processing_jobs)"
                        )
                    )
                ).one()
            )

    assert [unsupported.status_code, mismatch.status_code, corrupt.status_code] == [400, 400, 400]
    assert too_long.status_code == 400
    assert counts == (0, 0, 0)
    assert [path for path in (data_dir / "files").rglob("*") if path.is_file()] == []
    assert [path for path in (data_dir / "cache" / "imports").glob("*")] == []


@pytest.mark.anyio
async def test_asr_waits_without_attempts_then_resumes_and_publishes_once(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    fake_asr = FakeTencentAsrClient()
    async with running_audio_app(data_dir, asr_client=fake_asr) as (_app, client):
        accepted = await client.post(
            "/api/audio-imports",
            files={"file": ("lesson.wav", wav_bytes(seconds=1), "audio/wav")},
        )
        record_id = accepted.json()["record_id"]

        async def wait_for_reason(reason: str) -> dict[str, object]:
            for _ in range(250):
                payload = (await client.get(f"/api/records/{record_id}/jobs")).json()
                asr_job = payload["jobs"][1]
                if asr_job["waiting_reason"] == reason:
                    return asr_job
                await asyncio.sleep(0.02)
            pytest.fail(f"ASR 未进入等待态 {reason}")

        assert (await wait_for_reason("CONSENT_REQUIRED"))["attempts"] == 0
        consent = await client.post("/api/settings/external-processing-consents/tencent-asr")
        assert consent.status_code == 200
        assert consent.json()["granted_at"] is not None
        assert (await wait_for_reason("ASR_KEY_REQUIRED"))["attempts"] == 0

        (data_dir / "config" / "providers.json").write_text(
            json.dumps(
                {
                    "tencent_asr": {
                        "secret_id": "secret-id",
                        "secret_key": "secret-key",
                        "region": "ap-shanghai",
                    }
                }
            ),
            encoding="utf-8",
        )
        assert (await wait_for_reason("OFFLINE"))["attempts"] == 0
        fake_asr.online = True

        transcript: JsonObject | None = None
        jobs: JsonObject | None = None
        for _ in range(250):
            transcript = cast(
                JsonObject,
                (await client.get(f"/api/records/{record_id}/transcript")).json(),
            )
            jobs = cast(JsonObject, (await client.get(f"/api/records/{record_id}/jobs")).json())
            if transcript["status"] == "READY":
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("ASR 未发布 Transcript")

    assert transcript is not None and jobs is not None
    transcript_out = cast(JsonObject, transcript["transcript"])
    assert transcript_out["content"] == "真实边界替身返回的正文。"
    assert transcript_out["language"] == "zh-CN"
    assert job_items(jobs)[1]["status"] == "SUCCEEDED"
    assert job_items(jobs)[1]["attempts"] == 1
    assert len(fake_asr.submitted) == 1
    assert fake_asr.submitted[0].suffix == ".ogg"
    assert not (data_dir / "cache" / "audio" / record_id).exists()


@pytest.mark.anyio
async def test_asr_polling_failure_retries_three_rounds_without_resubmitting(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    write_asr_prerequisites(data_dir)
    fake_asr = FailingPollTencentAsrClient()
    async with running_audio_app(data_dir, asr_client=fake_asr) as (_app, client):
        accepted = await client.post(
            "/api/audio-imports",
            files={"file": ("lesson.wav", wav_bytes(seconds=1), "audio/wav")},
        )
        record_id = accepted.json()["record_id"]
        for _ in range(250):
            if fake_asr.polls >= 1:
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("ASR 未开始首次轮询")
        (data_dir / "config" / "providers.json").write_text(
            json.dumps(
                {
                    "tencent_asr": {
                        "secret_id": "secret-id",
                        "secret_key": "secret-key",
                        "region": "ap-beijing",
                    }
                }
            ),
            encoding="utf-8",
        )
        asr_job: JsonObject | None = None
        for _ in range(400):
            jobs = cast(JsonObject, (await client.get(f"/api/records/{record_id}/jobs")).json())
            asr_job = job_items(jobs)[1]
            if asr_job["status"] == "FAILED":
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("ASR 临时故障没有在有限重试后停止")

    assert asr_job is not None
    assert asr_job["error_code"] == "ASR_TEMPORARY_UNAVAILABLE"
    assert asr_job["attempts"] == 3
    assert fake_asr.polls == 3
    assert fake_asr.regions == ["ap-shanghai"] * 3
    assert len(fake_asr.submitted) == 1


@pytest.mark.anyio
async def test_asr_submit_timeout_stops_without_automatic_resubmit(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    write_asr_prerequisites(data_dir)
    fake_asr = UnknownSubmitTencentAsrClient()
    async with running_audio_app(data_dir, asr_client=fake_asr) as (_app, client):
        accepted = await client.post(
            "/api/audio-imports",
            files={"file": ("lesson.wav", wav_bytes(seconds=1), "audio/wav")},
        )
        record_id = accepted.json()["record_id"]
        asr_job: JsonObject | None = None
        for _ in range(250):
            jobs = cast(JsonObject, (await client.get(f"/api/records/{record_id}/jobs")).json())
            asr_job = job_items(jobs)[1]
            if asr_job["status"] == "FAILED":
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("ASR 提交超时没有停止")

    assert asr_job is not None
    assert asr_job["error_code"] == "ASR_SUBMIT_UNKNOWN"
    assert asr_job["attempts"] == 1
    assert asr_job["retryable"] is True


@pytest.mark.anyio
async def test_manual_retry_keeps_task_id_after_poll_auth_failure(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    write_asr_prerequisites(data_dir)
    fake_asr = AuthFailingPollTencentAsrClient()
    async with running_audio_app(data_dir, asr_client=fake_asr) as (app, client):
        accepted = await client.post(
            "/api/audio-imports",
            files={"file": ("lesson.wav", wav_bytes(seconds=1), "audio/wav")},
        )
        record_id = accepted.json()["record_id"]
        job_id = accepted.json()["asr_job_id"]
        for _ in range(250):
            job = (await client.get(f"/api/records/{record_id}/jobs")).json()["jobs"][1]
            if job["status"] == "FAILED":
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("ASR 鉴权失败未进入失败态")
        async with app.state.session_factory() as session:
            checkpoint = await session.scalar(
                text("SELECT result_json FROM processing_jobs WHERE id=:id"), {"id": job_id}
            )
        state = json.loads(cast(str, checkpoint))["chunks"][0]
        assert state["status"] == "SUBMITTED"
        assert state["task_id"] == "task-1"
        assert state["error_code"] == "ASR_AUTH_FAILED"

        fake_asr.authorized = True
        assert (
            await client.post(
                f"/api/processing-jobs/{job_id}/retries",
                json={"record_id": record_id},
            )
        ).status_code == 202
        for _ in range(250):
            transcript = (await client.get(f"/api/records/{record_id}/transcript")).json()
            if transcript["status"] == "READY":
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("修复凭据后未从已有 TaskId 恢复")

    assert len(fake_asr.submitted) == 1


@pytest.mark.anyio
async def test_manual_retry_resubmits_expired_task_id(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    write_asr_prerequisites(data_dir)
    fake_asr = ExpiredPollTencentAsrClient()
    async with running_audio_app(data_dir, asr_client=fake_asr) as (app, client):
        accepted = await client.post(
            "/api/audio-imports",
            files={"file": ("lesson.wav", wav_bytes(seconds=1), "audio/wav")},
        )
        record_id = accepted.json()["record_id"]
        job_id = accepted.json()["asr_job_id"]
        for _ in range(250):
            job = (await client.get(f"/api/records/{record_id}/jobs")).json()["jobs"][1]
            if job["status"] == "FAILED":
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("过期 TaskId 未进入失败态")
        async with app.state.session_factory() as session:
            checkpoint = await session.scalar(
                text("SELECT result_json FROM processing_jobs WHERE id=:id"), {"id": job_id}
            )
        state = json.loads(cast(str, checkpoint))["chunks"][0]
        assert state["status"] == "EXPIRED"
        assert state["task_id"] == "task-1"
        assert state["error_code"] == "ASR_TASK_EXPIRED"

        fake_asr.expired = False
        assert (
            await client.post(
                f"/api/processing-jobs/{job_id}/retries",
                json={"record_id": record_id},
            )
        ).status_code == 202
        for _ in range(250):
            transcript = (await client.get(f"/api/records/{record_id}/transcript")).json()
            if transcript["status"] == "READY":
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("过期 TaskId 手动重试未重新提交")

    assert len(fake_asr.submitted) == 2


@pytest.mark.anyio
async def test_restart_polls_persisted_task_id_without_duplicate_submit(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    write_asr_prerequisites(data_dir)
    offline = FakeTencentAsrClient()
    async with running_audio_app(data_dir, asr_client=offline) as (app, client):
        accepted = await client.post(
            "/api/audio-imports",
            files={"file": ("lesson.wav", wav_bytes(seconds=1), "audio/wav")},
        )
        record_id = accepted.json()["record_id"]
        asr_job_id = accepted.json()["asr_job_id"]
        for _ in range(250):
            jobs = (await client.get(f"/api/records/{record_id}/jobs")).json()
            if jobs["jobs"][1]["waiting_reason"] == "OFFLINE":
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("ASR 未进入离线等待态")

        async with app.state.session_factory() as session, session.begin():
            input_json = (
                await session.execute(
                    text("SELECT input_json FROM processing_jobs WHERE id=:id"),
                    {"id": asr_job_id},
                )
            ).scalar_one()
            chunks = json.loads(input_json)["chunks"]
            await session.execute(
                text(
                    "UPDATE processing_jobs SET status='RUNNING', attempts=1, waiting_reason=NULL, "
                    "result_json=:result WHERE id=:id"
                ),
                {
                    "id": asr_job_id,
                    "result": json.dumps(
                        {
                            "cursor": 0,
                            "chunks": [
                                {"index": 0, "status": "SUBMITTED", "task_id": "task-restart"}
                            ],
                        }
                    ),
                },
            )
            assert len(chunks) == 1

    resumed = FakeTencentAsrClient()
    resumed.online = True
    async with running_audio_app(data_dir, asr_client=resumed) as (_app, client):
        for _ in range(250):
            transcript = (await client.get(f"/api/records/{record_id}/transcript")).json()
            if transcript["status"] == "READY":
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("重启后没有从 TaskId 恢复")

    assert resumed.submitted == []
    assert transcript["transcript"]["content"] == "真实边界替身返回的正文。"


@pytest.mark.anyio
async def test_delete_during_transcode_cleans_late_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    transcode_finished = asyncio.Event()
    allow_completion = asyncio.Event()
    original_transcode = AudioWorker._transcode  # pyright: ignore[reportPrivateUsage]

    async def delayed_transcode(
        self: AudioWorker,
        record_id: str,
        record_file_id: str,
        source_path: Path,
        duration_ms: int,
    ) -> list[dict[str, object]]:
        await original_transcode(
            self,
            record_id,
            record_file_id,
            source_path,
            duration_ms,
        )
        transcode_finished.set()
        await allow_completion.wait()
        late_cache = data_dir / "cache" / "audio" / record_id / record_file_id
        late_cache.mkdir(parents=True, exist_ok=True)
        (late_cache / "late.ogg").write_bytes(b"late")
        raise RuntimeError("ffmpeg failed after delete")

    monkeypatch.setattr(AudioWorker, "_transcode", delayed_transcode)
    async with running_audio_app(data_dir) as (_app, client):
        accepted = await client.post(
            "/api/audio-imports",
            files={"file": ("lesson.wav", wav_bytes(seconds=1), "audio/wav")},
        )
        record_id = accepted.json()["record_id"]
        await asyncio.wait_for(transcode_finished.wait(), timeout=5)
        assert (await client.delete(f"/api/records/{record_id}")).status_code == 204
        allow_completion.set()
        for _ in range(100):
            if not (data_dir / "cache" / "audio" / record_id).exists():
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("删除后的转码产物没有在 ffmpeg 退出后清理")


@pytest.mark.anyio
async def test_delete_during_asr_poll_rejects_late_text_and_cleans_cache(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    write_asr_prerequisites(data_dir)
    fake_asr = BlockingPollTencentAsrClient()
    async with running_audio_app(data_dir, asr_client=fake_asr) as (_app, client):
        accepted = await client.post(
            "/api/audio-imports",
            files={"file": ("lesson.wav", wav_bytes(seconds=1), "audio/wav")},
        )
        record_id = accepted.json()["record_id"]
        await asyncio.wait_for(fake_asr.poll_started.wait(), timeout=5)
        assert (await client.delete(f"/api/records/{record_id}")).status_code == 204
        fake_asr.release_poll.set()
        for _ in range(100):
            if not (data_dir / "cache" / "audio" / record_id).exists():
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("删除后的迟到 ASR 结果遗留了 cache")
        assert (await client.get(f"/api/records/{record_id}/transcript")).status_code == 404


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
