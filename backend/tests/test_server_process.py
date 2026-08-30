import asyncio
import io
import json
import os
import secrets
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import wave
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from app.db.migrations import run_migrations
from app.services.local_config import LlmProviderConfig, llm_provider_fingerprint


def start_sidecar(
    data_dir: Path,
    token: str,
    *,
    ffmpeg_path: Path | None = None,
    empty_path: bool = False,
    asr_control: Path | None = None,
    fake_summary: bool = False,
    import_archive: Path | None = None,
) -> subprocess.Popen[bytes]:
    if asr_control is not None and ffmpeg_path is None:
        ffmpeg_path = (
            Path(__file__).resolve().parents[2]
            / "apps"
            / "desktop"
            / "src-tauri"
            / "binaries"
            / "ffmpeg-x86_64-pc-windows-msvc.exe"
        )
        if not ffmpeg_path.is_file():
            pytest.skip("尚未运行 desktop prepare:ffmpeg")
    resolved_ffmpeg = str(ffmpeg_path) if ffmpeg_path is not None else shutil.which("ffmpeg")
    if resolved_ffmpeg is None:
        pytest.skip("真实 ffmpeg 不可用")
    environment = os.environ.copy()
    if empty_path:
        environment["PATH"] = ""
    command = [
        sys.executable,
        *(
            [str(Path(__file__).with_name("sidecar_asr_fixture.py"))]
            if asr_control
            else ["-m", "app.server"]
        ),
        "--port",
        "0",
        f"--token={token}",
        "--data-dir",
        str(data_dir),
        "--ffmpeg",
        resolved_ffmpeg,
    ]
    if import_archive is not None:
        command.extend(["--import-archive", str(import_archive)])
    if asr_control is not None:
        command.extend(["--asr-control", str(asr_control)])
    if fake_summary:
        command.append("--fake-summary")
    return subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )


def short_wav() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        audio.writeframes(b"\x00\x00" * 16_000)
    return output.getvalue()


def over_five_hours_wav() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(1)
        audio.writeframes(b"\x00\x00" * (5 * 60 * 60 + 1))
    return output.getvalue()


def write_asr_fixture(data_dir: Path, control: Path, mode: str) -> None:
    config = data_dir / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "settings.json").write_text(
        json.dumps({"tencent_asr_consent_granted_at": "2026-08-22T00:00:00Z"}),
        encoding="utf-8",
    )
    write_provider_config(data_dir)
    control.write_text(json.dumps({"mode": mode}), encoding="utf-8")


def write_provider_config(data_dir: Path) -> None:
    config = data_dir / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "providers.json").write_text(
        json.dumps(
            {
                "tencent_asr": {
                    "secret_id": "fixture-id",
                    "secret_key": "fixture-key",
                    "region": "ap-shanghai",
                }
            }
        ),
        encoding="utf-8",
    )


def asr_events(control: Path) -> list[dict[str, object]]:
    path = control.with_suffix(".events.json")
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def wait_for_job(
    client: httpx.Client,
    record_id: str,
    *,
    status: str,
    attempts: int | None = None,
) -> dict[str, object]:
    for _ in range(300):
        job = client.get(f"/api/records/{record_id}/jobs").json()["jobs"][1]
        if job["status"] == status and (attempts is None or job["attempts"] == attempts):
            return job
        time.sleep(0.05)
    pytest.fail(f"ASR Job 未进入 {status}")


def wait_for_waiting_reason(
    client: httpx.Client,
    record_id: str,
    reason: str,
) -> dict[str, object]:
    for _ in range(300):
        job = client.get(f"/api/records/{record_id}/jobs").json()["jobs"][1]
        if job["waiting_reason"] == reason:
            return job
        time.sleep(0.05)
    pytest.fail(f"ASR Job 未进入等待态 {reason}")


def wait_for_sidecar(
    process: subprocess.Popen[bytes],
    token: str,
) -> tuple[str, bytes]:
    assert process.stdout is not None
    port_line = process.stdout.readline()
    prefix = b"KNOWREALM_SIDECAR_PORT="
    assert port_line.startswith(prefix)
    port = int(port_line.removeprefix(prefix))
    assert port > 0
    base_url = f"http://127.0.0.1:{port}"

    with httpx.Client(trust_env=False) as client:
        for _ in range(50):
            if process.poll() is not None:
                _, stderr = process.communicate(timeout=1)
                pytest.fail(stderr.decode(errors="replace"))
            try:
                response = client.get(
                    f"{base_url}/api/health",
                    headers={"X-KnowRealm-Token": token},
                )
                if response.status_code == 200:
                    return base_url, port_line
            except httpx.ConnectError:
                pass
            time.sleep(0.1)
    pytest.fail("sidecar 未在随机本机端口启动")


def stop_process_tree(process: subprocess.Popen[bytes]) -> tuple[bytes, bytes]:
    if process.poll() is None:
        if sys.platform == "win32":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.terminate()
    return process.communicate(timeout=10)


def test_real_process_selects_random_loopback_port_and_requires_token(tmp_path: Path) -> None:
    token = secrets.token_urlsafe(32)
    process = start_sidecar(tmp_path / "KnowRealm", token)
    base_url, port_line = wait_for_sidecar(process, token)

    try:
        with httpx.Client(trust_env=False) as client:
            assert client.get(f"{base_url}/api/health").status_code == 403
            assert (
                client.get(
                    f"{base_url}/api/health",
                    headers={"X-KnowRealm-Token": "wrong"},
                ).status_code
                == 403
            )
    finally:
        stdout, stderr = stop_process_tree(process)

    assert token.encode() not in port_line + stdout
    assert token.encode() not in stderr


def test_real_process_audio_import_uses_bundled_ffmpeg_with_empty_path(tmp_path: Path) -> None:
    ffmpeg = (
        Path(__file__).resolve().parents[2]
        / "apps"
        / "desktop"
        / "src-tauri"
        / "binaries"
        / "ffmpeg-x86_64-pc-windows-msvc.exe"
    )
    if not ffmpeg.is_file():
        pytest.skip("尚未运行 desktop prepare:ffmpeg")
    data_dir = tmp_path / "KnowRealm"
    token = secrets.token_urlsafe(32)
    process = start_sidecar(data_dir, token, ffmpeg_path=ffmpeg, empty_path=True)
    stopped = False
    stderr = b""
    try:
        base_url, _ = wait_for_sidecar(process, token)
        with httpx.Client(
            base_url=base_url,
            headers={"X-KnowRealm-Token": token},
            trust_env=False,
        ) as client:
            assert (
                client.post(
                    "/api/audio-imports",
                    files={"file": ("格式不符.mp3", short_wav(), "audio/mpeg")},
                ).status_code
                == 400
            )
            assert (
                client.post(
                    "/api/audio-imports",
                    files={"file": ("损坏.wav", b"RIFF0000WAVEbroken", "audio/wav")},
                ).status_code
                == 400
            )
            too_long = client.post(
                "/api/audio-imports",
                files={"file": ("超长.wav", over_five_hours_wav(), "audio/wav")},
            )
            assert too_long.status_code == 400
            assert too_long.json()["detail"].startswith("AUDIO_TOO_LONG")
            accepted = client.post(
                "/api/audio-imports",
                files={"file": ("真实进程.wav", short_wav(), "audio/wav")},
            )
            if accepted.status_code != 202:
                _, stderr = stop_process_tree(process)
                stopped = True
                pytest.fail(
                    f"audio import returned {accepted.status_code}: {accepted.text}\n"
                    f"{stderr.decode(errors='replace')}"
                )
            record_id = accepted.json()["record_id"]
            for _ in range(200):
                jobs = client.get(f"/api/records/{record_id}/jobs").json()["jobs"]
                if jobs[0]["status"] == "SUCCEEDED":
                    break
                time.sleep(0.05)
            else:
                pytest.fail("随包 ffmpeg 未完成真实进程转码")
            assert jobs[1]["waiting_reason"] == "CONSENT_REQUIRED"
            chunks = list((data_dir / "cache" / "audio" / record_id).rglob("chunk-*.ogg"))
            assert chunks
            assert all(chunk.stat().st_size < 5 * 1024 * 1024 for chunk in chunks)
    finally:
        if not stopped:
            _, stderr = stop_process_tree(process)

    assert token.encode() not in stderr
    with sqlite3.connect(data_dir / "knowrealm.db") as connection:
        assert connection.execute("SELECT count(*) FROM records").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM record_files").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM processing_jobs").fetchone() == (2,)


def test_real_process_audio_asr_and_sse_over_protected_socket(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    control = tmp_path / "asr-control.json"
    control.write_text(json.dumps({"mode": "pending", "online": False}), encoding="utf-8")
    token = secrets.token_urlsafe(32)
    process = start_sidecar(data_dir, token, asr_control=control)
    try:
        base_url, _ = wait_for_sidecar(process, token)
        with httpx.Client(
            base_url=base_url,
            headers={"X-KnowRealm-Token": token},
            trust_env=False,
        ) as client:
            accepted = client.post(
                "/api/audio-imports",
                files={"file": ("真实控制面.wav", short_wav(), "audio/wav")},
            )
            assert accepted.status_code == 202
            record_id = accepted.json()["record_id"]
            assert wait_for_waiting_reason(client, record_id, "CONSENT_REQUIRED")["attempts"] == 0
            assert (
                client.post("/api/settings/external-processing-consents/tencent-asr").status_code
                == 200
            )
            assert wait_for_waiting_reason(client, record_id, "ASR_KEY_REQUIRED")["attempts"] == 0
            write_provider_config(data_dir)
            assert wait_for_waiting_reason(client, record_id, "OFFLINE")["attempts"] == 0
            control.write_text(json.dumps({"mode": "pending", "online": True}), encoding="utf-8")
            wait_for_job(client, record_id, status="RUNNING")
            with client.stream("GET", f"/api/records/{record_id}/events") as stream:
                assert stream.status_code == 200
                lines = stream.iter_lines()
                assert next(lines) == "event: invalidate"
                assert json.loads(next(lines).removeprefix("data: ")) == {"record_id": record_id}
                assert next(lines) == ""
                control.write_text(json.dumps({"mode": "success"}), encoding="utf-8")
                remaining = list(lines)
                assert "event: invalidate" in remaining
                assert f'data: {{"record_id":"{record_id}"}}' in remaining
            job = wait_for_job(client, record_id, status="SUCCEEDED", attempts=1)
            transcript = client.get(f"/api/records/{record_id}/transcript").json()
            assert transcript["transcript"]["content"] == "真实进程替身正文。"
            assert job["progress"] == 1
    finally:
        _, stderr = stop_process_tree(process)

    events = asr_events(control)
    assert [event["event"] for event in events].count("submit") == 1
    assert [event["event"] for event in events].count("poll") >= 1
    assert token.encode() not in stderr
    assert not (data_dir / "cache" / "audio" / record_id).exists()


def test_real_process_asr_restart_resumes_persisted_task_id(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    control = tmp_path / "asr-control.json"
    write_asr_fixture(data_dir, control, "pending")
    first_token = secrets.token_urlsafe(32)
    first = start_sidecar(data_dir, first_token, asr_control=control)
    try:
        first_url, _ = wait_for_sidecar(first, first_token)
        with httpx.Client(
            base_url=first_url,
            headers={"X-KnowRealm-Token": first_token},
            trust_env=False,
        ) as client:
            accepted = client.post(
                "/api/audio-imports",
                files={"file": ("重启恢复.wav", short_wav(), "audio/wav")},
            )
            record_id = accepted.json()["record_id"]
            for _ in range(300):
                if any(event["event"] == "poll" for event in asr_events(control)):
                    break
                time.sleep(0.05)
            else:
                pytest.fail("真实 sidecar 未提交并轮询 ASR TaskId")
    finally:
        stop_process_tree(first)

    control.write_text(json.dumps({"mode": "success"}), encoding="utf-8")
    restart_token = secrets.token_urlsafe(32)
    restarted = start_sidecar(data_dir, restart_token, asr_control=control)
    try:
        restart_url, _ = wait_for_sidecar(restarted, restart_token)
        with httpx.Client(
            base_url=restart_url,
            headers={"X-KnowRealm-Token": restart_token},
            trust_env=False,
        ) as client:
            wait_for_job(client, record_id, status="SUCCEEDED")
            assert client.get(f"/api/records/{record_id}/transcript").json()["status"] == "READY"
    finally:
        stop_process_tree(restarted)

    assert [event["event"] for event in asr_events(control)].count("submit") == 1


def test_real_process_http_503_retries_three_times(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    control = tmp_path / "asr-control.json"
    write_asr_fixture(data_dir, control, "poll_503")
    token = secrets.token_urlsafe(32)
    process = start_sidecar(data_dir, token, asr_control=control)
    try:
        base_url, _ = wait_for_sidecar(process, token)
        with httpx.Client(
            base_url=base_url,
            headers={"X-KnowRealm-Token": token},
            trust_env=False,
            timeout=15,
        ) as client:
            transient = client.post(
                "/api/audio-imports",
                files={"file": ("有限重试.wav", short_wav(), "audio/wav")},
            ).json()
            failed = wait_for_job(client, transient["record_id"], status="FAILED", attempts=3)
            assert failed["error_code"] == "ASR_TEMPORARY_UNAVAILABLE"
    finally:
        stop_process_tree(process)


def test_real_process_asr_failure_retry_and_delete_races(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    control = tmp_path / "asr-control.json"
    write_asr_fixture(data_dir, control, "submit_timeout")
    token = secrets.token_urlsafe(32)
    process = start_sidecar(data_dir, token, asr_control=control)
    try:
        base_url, _ = wait_for_sidecar(process, token)
        with httpx.Client(
            base_url=base_url,
            headers={"X-KnowRealm-Token": token},
            trust_env=False,
        ) as client:
            unknown = client.post(
                "/api/audio-imports",
                files={"file": ("提交未知.wav", short_wav(), "audio/wav")},
            ).json()
            failed = wait_for_job(client, unknown["record_id"], status="FAILED", attempts=1)
            assert failed["error_code"] == "ASR_SUBMIT_UNKNOWN"
            control.write_text(json.dumps({"mode": "success"}), encoding="utf-8")
            assert (
                client.post(
                    f"/api/processing-jobs/{unknown['asr_job_id']}/retries",
                    json={"record_id": unknown["record_id"]},
                ).status_code
                == 202
            )
            wait_for_job(client, unknown["record_id"], status="SUCCEEDED")

            for mode in ("invalid_json", "invalid_task_id"):
                control.write_text(json.dumps({"mode": mode}), encoding="utf-8")
                invalid = client.post(
                    "/api/audio-imports",
                    files={"file": (f"{mode}.wav", short_wav(), "audio/wav")},
                ).json()
                failed = wait_for_job(client, invalid["record_id"], status="FAILED", attempts=1)
                assert failed["error_code"] == "ASR_RECOGNITION_FAILED"

            control.write_text(json.dumps({"mode": "pending"}), encoding="utf-8")
            deleting = client.post(
                "/api/audio-imports",
                files={"file": ("删除竞态.wav", short_wav(), "audio/wav")},
            ).json()
            wait_for_job(client, deleting["record_id"], status="RUNNING")
            with client.stream("GET", f"/api/records/{deleting['record_id']}/events") as stream:
                lines = stream.iter_lines()
                assert next(lines) == "event: invalidate"
                assert next(lines).startswith("data: ")
                assert next(lines) == ""
                with httpx.Client(
                    base_url=base_url,
                    headers={"X-KnowRealm-Token": token},
                    trust_env=False,
                ) as mutator:
                    assert (
                        mutator.delete(f"/api/records/{deleting['record_id']}").status_code == 204
                    )
                remaining = list(lines)
                assert "event: invalidate" in remaining
            time.sleep(1.2)
            assert not (data_dir / "cache" / "audio" / deleting["record_id"]).exists()
            assert client.get(f"/api/records/{deleting['record_id']}").status_code == 404
    finally:
        stop_process_tree(process)


def test_second_sidecar_cannot_open_locked_data_directory(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    first_token = secrets.token_urlsafe(32)
    first = start_sidecar(data_dir, first_token)
    try:
        wait_for_sidecar(first, first_token)
        second = start_sidecar(data_dir, secrets.token_urlsafe(32))
        try:
            _, second_stderr = second.communicate(timeout=10)
            assert second.returncode != 0
            assert "DATA_DIRECTORY_IN_USE" in second_stderr.decode(errors="replace")
        finally:
            if second.poll() is None:
                stop_process_tree(second)
    finally:
        stop_process_tree(first)

    restarted_token = secrets.token_urlsafe(32)
    restarted = start_sidecar(data_dir, restarted_token)
    try:
        wait_for_sidecar(restarted, restarted_token)
        restarted.kill()
        restarted.communicate(timeout=10)
    finally:
        if restarted.poll() is None:
            stop_process_tree(restarted)

    after_crash_token = secrets.token_urlsafe(32)
    after_crash = start_sidecar(data_dir, after_crash_token)
    try:
        wait_for_sidecar(after_crash, after_crash_token)
    finally:
        stop_process_tree(after_crash)


def test_real_process_imports_document_and_reads_it_after_restart(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    token = secrets.token_urlsafe(32)
    process = start_sidecar(data_dir, token)
    try:
        base_url, _ = wait_for_sidecar(process, token)
        headers = {"X-KnowRealm-Token": token}
        with httpx.Client(base_url=base_url, headers=headers, trust_env=False) as client:
            course = client.post(
                "/api/courses",
                json={
                    "name": "真实进程文档导入",
                    "learning_context": "INTEREST",
                    "depth": "BEGINNER",
                },
            )
            accepted = client.post(
                "/api/document-imports",
                data={"course_id": course.json()["id"]},
                files={"file": ("lecture.md", "# 第一讲\n进程与线程", "text/markdown")},
            )
            assert accepted.status_code == 202
            body = accepted.json()
            job = None
            for _ in range(100):
                job = client.get(f"/api/processing-jobs/{body['job_id']}").json()
                if job["status"] in {"SUCCEEDED", "FAILED"}:
                    break
                time.sleep(0.05)
            assert job is not None
            assert job["status"] == "SUCCEEDED"
            assert (
                client.get(f"/api/records/{body['record_id']}/transcript").json()["transcript"][
                    "content"
                ]
                == "# 第一讲\n进程与线程"
            )
    finally:
        stop_process_tree(process)

    restart_token = secrets.token_urlsafe(32)
    restarted = start_sidecar(data_dir, restart_token)
    try:
        restarted_url, _ = wait_for_sidecar(restarted, restart_token)
        with httpx.Client(
            base_url=restarted_url,
            headers={"X-KnowRealm-Token": restart_token},
            trust_env=False,
        ) as client:
            assert client.get(f"/api/records/{body['record_id']}").status_code == 200
            assert (
                client.get(f"/api/records/{body['record_id']}/transcript").json()["status"]
                == "READY"
            )
            stored_files = list((data_dir / "files" / body["record_id"]).iterdir())
            assert len(stored_files) == 1
            assert stored_files[0].read_bytes() == "# 第一讲\n进程与线程".encode()
    finally:
        stop_process_tree(restarted)


def test_real_process_restart_keeps_recent_tombstone_and_purges_expired_assets(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    first_token = secrets.token_urlsafe(32)
    first = start_sidecar(data_dir, first_token)
    try:
        wait_for_sidecar(first, first_token)
    finally:
        stop_process_tree(first)

    db_path = data_dir / "knowrealm.db"
    course_id = "11111111-1111-4111-8111-111111111111"
    expired_record_id = "22222222-2222-4222-8222-222222222222"
    recent_record_id = "33333333-3333-4333-8333-333333333333"
    expired_file_id = "44444444-4444-4444-8444-444444444444"
    recent_file_id = "55555555-5555-4555-8555-555555555555"
    expired_job_id = "66666666-6666-4666-8666-666666666666"
    recent_job_id = "77777777-7777-4777-8777-777777777777"
    now = datetime.now(UTC)
    current = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    expired_at = (now - timedelta(days=31)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    recent_at = (now - timedelta(days=29)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    for record_id, body in (
        (expired_record_id, b"expired"),
        (recent_record_id, b"recent"),
    ):
        record_dir = data_dir / "files" / record_id
        record_dir.mkdir(parents=True)
        (record_dir / "source.txt").write_bytes(body)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(
            f"""
            INSERT INTO courses (
                id, name, learning_context, education_stage, depth,
                course_type, description, hot_words, status,
                created_at, updated_at, deleted_at
            ) VALUES (
                '{course_id}', '删除清理重启', 'INTEREST', NULL, 'BEGINNER',
                NULL, NULL, NULL, 'ACTIVE', '{current}', '{current}', NULL
            );
            INSERT INTO records (
                id, course_id, capture_type, title, status, duration_ms,
                summary_confirmed_at, created_at, updated_at, deleted_at
            ) VALUES
                ('{expired_record_id}', '{course_id}', 'DOCUMENT_IMPORT', '已到期',
                 'CONTENT_PROCESSING', 0, NULL, '{current}', '{current}', '{expired_at}'),
                ('{recent_record_id}', '{course_id}', 'DOCUMENT_IMPORT', '未到期',
                 'CONTENT_PROCESSING', 0, NULL, '{current}', '{current}', '{recent_at}');
            INSERT INTO record_files (
                id, record_id, file_type, source_type, file_path, original_name,
                mime_type, file_size, duration_ms, sequence_no, content_hash,
                created_at, updated_at, deleted_at
            ) VALUES
                ('{expired_file_id}', '{expired_record_id}', 'DOCUMENT', 'UPLOADED',
                 'files/{expired_record_id}/source.txt', 'expired.txt', 'text/plain', 7,
                 NULL, 0, 'expired-hash', '{current}', '{current}', NULL),
                ('{recent_file_id}', '{recent_record_id}', 'DOCUMENT', 'UPLOADED',
                 'files/{recent_record_id}/source.txt', 'recent.txt', 'text/plain', 6,
                 NULL, 0, 'recent-hash', '{current}', '{current}', NULL);
            INSERT INTO processing_jobs (
                id, record_id, job_type, status, progress, attempts, max_attempts,
                next_run_at, input_json, result_json, error_code, error_message,
                started_at, finished_at, created_at, updated_at
            ) VALUES
                ('{expired_job_id}', '{expired_record_id}', 'DOCUMENT_PARSE', 'CANCELLED',
                 0, 1, 3, NULL, '{{}}', NULL, NULL, NULL, '{current}', '{current}',
                 '{current}', '{current}'),
                ('{recent_job_id}', '{recent_record_id}', 'DOCUMENT_PARSE', 'CANCELLED',
                 0, 1, 3, NULL, '{{}}', NULL, NULL, NULL, '{current}', '{current}',
                 '{current}', '{current}');
            """
        )

    token = secrets.token_urlsafe(32)
    restarted = start_sidecar(data_dir, token)
    try:
        base_url, _ = wait_for_sidecar(restarted, token)
        with httpx.Client(
            base_url=base_url,
            headers={"X-KnowRealm-Token": token},
            trust_env=False,
        ) as client:
            assert client.get(f"/api/records/{expired_record_id}").status_code == 404
            assert client.get(f"/api/records/{recent_record_id}").status_code == 404
    finally:
        stop_process_tree(restarted)

    with sqlite3.connect(db_path) as connection:
        assert (
            connection.execute(
                "SELECT id FROM records WHERE id = ?", (expired_record_id,)
            ).fetchone()
            is None
        )
        assert connection.execute(
            "SELECT status, attempts FROM processing_jobs WHERE id = ?", (recent_job_id,)
        ).fetchone() == ("CANCELLED", 1)
    assert not (data_dir / "files" / expired_record_id).exists()
    assert (data_dir / "files" / recent_record_id / "source.txt").read_bytes() == b"recent"


def test_real_process_recovers_running_document_job_after_crash(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    data_dir.mkdir()
    db_path = data_dir / "knowrealm.db"
    asyncio.run(run_migrations(db_path))
    course_id = "11111111-1111-4111-8111-111111111111"
    record_id = "22222222-2222-4222-8222-222222222222"
    file_id = "33333333-3333-4333-8333-333333333333"
    job_id = "44444444-4444-4444-8444-444444444444"
    relative_file = f"files/{record_id}/{file_id}.txt"
    source_path = data_dir / relative_file
    source_path.parent.mkdir(parents=True)
    marker = b"private-document-body"
    source = marker + b"\n" + (b"x" * (4 * 1024 * 1024))
    source_path.write_bytes(source)
    now = "2026-08-21T12:00:00.000000Z"
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(
            f"""
            INSERT INTO courses (
                id, name, learning_context, education_stage, depth,
                course_type, description, hot_words, status,
                created_at, updated_at, deleted_at
            ) VALUES (
                '{course_id}', '进程恢复', 'INTEREST', NULL, 'BEGINNER',
                NULL, NULL, NULL, 'ACTIVE', '{now}', '{now}', NULL
            );
            INSERT INTO records (
                id, course_id, capture_type, title, status, duration_ms,
                summary_confirmed_at, created_at, updated_at, deleted_at
            ) VALUES (
                '{record_id}', '{course_id}', 'DOCUMENT_IMPORT', '进程恢复',
                'CONTENT_PROCESSING', 0, NULL, '{now}', '{now}', NULL
            );
            INSERT INTO record_files (
                id, record_id, file_type, source_type, file_path, original_name,
                mime_type, file_size, duration_ms, sequence_no, content_hash,
                created_at, updated_at, deleted_at
            ) VALUES (
                '{file_id}', '{record_id}', 'DOCUMENT', 'UPLOADED',
                '{relative_file}', 'recovery.txt', 'text/plain', {len(source)}, NULL, 0,
                'hash', '{now}', '{now}', NULL
            );
            INSERT INTO processing_jobs (
                id, record_id, job_type, status, progress, attempts, max_attempts,
                next_run_at, input_json, result_json, error_code, error_message,
                started_at, finished_at, created_at, updated_at
            ) VALUES (
                '{job_id}', '{record_id}', 'DOCUMENT_PARSE', 'RUNNING', 0, 1, 3,
                NULL, '{{"record_file_id":"{file_id}"}}', NULL, NULL, NULL,
                '{now}', NULL, '{now}', '{now}'
            );
            """
        )

    first_token = secrets.token_urlsafe(32)
    first = start_sidecar(data_dir, first_token)
    try:
        wait_for_sidecar(first, first_token)
        with sqlite3.connect(db_path, isolation_level=None) as connection:
            connection.execute(
                "UPDATE processing_jobs SET next_run_at = NULL WHERE id = ?",
                (job_id,),
            )
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                status = connection.execute(
                    "SELECT status FROM processing_jobs WHERE id = ?",
                    (job_id,),
                ).fetchone()
                if status == ("RUNNING",):
                    first.kill()
                    break
            else:
                pytest.fail("真实 sidecar 未领取恢复任务")
    finally:
        first_stdout, first_stderr = stop_process_tree(first)

    with sqlite3.connect(db_path) as connection:
        assert connection.execute(
            "SELECT status, attempts FROM processing_jobs WHERE id = ?",
            (job_id,),
        ).fetchone() == ("RUNNING", 2)

    restart_token = secrets.token_urlsafe(32)
    restarted = start_sidecar(data_dir, restart_token)
    try:
        restarted_url, _ = wait_for_sidecar(restarted, restart_token)
        with httpx.Client(
            base_url=restarted_url,
            headers={"X-KnowRealm-Token": restart_token},
            trust_env=False,
        ) as client:
            job = None
            for _ in range(200):
                job = client.get(f"/api/processing-jobs/{job_id}").json()
                if job["status"] in {"SUCCEEDED", "FAILED"}:
                    break
                time.sleep(0.05)
            assert job is not None
            assert job["status"] == "SUCCEEDED"
            assert job["attempts"] == 3
            transcript = client.get(f"/api/records/{record_id}/transcript").json()
            assert transcript["status"] == "READY"
            assert transcript["transcript"]["content"].encode() == source
    finally:
        restarted_stdout, restarted_stderr = stop_process_tree(restarted)

    final_token = secrets.token_urlsafe(32)
    final_process = start_sidecar(data_dir, final_token)
    try:
        final_url, _ = wait_for_sidecar(final_process, final_token)
        with httpx.Client(
            base_url=final_url,
            headers={"X-KnowRealm-Token": final_token},
            trust_env=False,
        ) as client:
            assert client.get(f"/api/processing-jobs/{job_id}").json()["status"] == ("SUCCEEDED")
            assert client.get(f"/api/records/{record_id}/transcript").json()["status"] == ("READY")
    finally:
        final_stdout, final_stderr = stop_process_tree(final_process)

    logs = (
        first_stdout
        + first_stderr
        + restarted_stdout
        + restarted_stderr
        + final_stdout
        + final_stderr
    )
    assert first_token.encode() not in logs
    assert restart_token.encode() not in logs
    assert final_token.encode() not in logs
    assert marker not in logs
    assert str(data_dir).encode() not in logs
    assert source_path.read_bytes() == source


def test_real_process_reads_preseeded_record_over_protected_socket(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    data_dir.mkdir()
    db_path = data_dir / "knowrealm.db"
    asyncio.run(run_migrations(db_path))
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            """
            INSERT INTO courses (
                id, name, learning_context, education_stage, depth,
                course_type, description, hot_words, status,
                created_at, updated_at, deleted_at
            ) VALUES (
                '11111111-1111-4111-8111-111111111111', '真实 HTTP',
                'INTEREST', NULL, 'BEGINNER',
                NULL, NULL, NULL, 'ACTIVE',
                '2026-08-19T08:00:00.000000Z',
                '2026-08-19T08:00:00.000000Z', NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO records (
                id, course_id, capture_type, title, status, duration_ms,
                summary_confirmed_at, created_at, updated_at, deleted_at
            ) VALUES (
                '22222222-2222-4222-8222-222222222222',
                '11111111-1111-4111-8111-111111111111',
                'AUDIO_IMPORT', '植入记录',
                'CONTENT_PROCESSING', 65000, NULL,
                '2026-08-19T08:30:00.000000Z',
                '2026-08-19T08:30:00.000000Z', NULL
            )
            """
        )

    token = secrets.token_urlsafe(32)
    process = start_sidecar(data_dir, token)
    base_url, port_line = wait_for_sidecar(process, token)
    try:
        with httpx.Client(trust_env=False) as client:
            response = client.get(
                f"{base_url}/api/courses/11111111-1111-4111-8111-111111111111/records",
                headers={"X-KnowRealm-Token": token},
            )
            assert response.status_code == 200
            assert response.json() == [
                {
                    "id": "22222222-2222-4222-8222-222222222222",
                    "course_id": "11111111-1111-4111-8111-111111111111",
                    "capture_type": "AUDIO_IMPORT",
                    "title": "植入记录",
                    "status": "CONTENT_PROCESSING",
                    "duration_ms": 65_000,
                    "summary_confirmed_at": None,
                    "created_at": "2026-08-19T08:30:00.000000Z",
                    "updated_at": "2026-08-19T08:30:00.000000Z",
                }
            ]
            detail = client.get(
                f"{base_url}/api/records/22222222-2222-4222-8222-222222222222",
                headers={"X-KnowRealm-Token": token},
            )
            assert detail.status_code == 200
            assert detail.json() == response.json()[0]
            assert (
                client.get(
                    f"{base_url}/api/records/22222222-2222-4222-8222-222222222222"
                ).status_code
                == 403
            )
    finally:
        stdout, stderr = stop_process_tree(process)

    assert token.encode() not in port_line + stdout
    assert token.encode() not in stderr


def test_real_process_inbox_classify_and_upgrade_over_real_socket(tmp_path: Path) -> None:
    token = secrets.token_urlsafe(32)
    data_dir = tmp_path / "KnowRealm"
    control = tmp_path / "asr-control.json"
    control.write_text(json.dumps({"mode": "success"}), encoding="utf-8")
    config = data_dir / "config"
    config.mkdir(parents=True)
    (config / "providers.json").write_text(
        json.dumps(
            {
                "llm": {
                    "base_url": "https://example.com/v1",
                    "api_key": "sk-test",
                    "model": "qwen-plus",
                }
            }
        ),
        encoding="utf-8",
    )
    (config / "settings.json").write_text(
        json.dumps(
            {
                "llm_external_processing_consent": {
                    "provider_fingerprint": llm_provider_fingerprint(
                        LlmProviderConfig(
                            base_url="https://example.com/v1",
                            api_key="sk-test",
                            model="qwen-plus",
                        )
                    ),
                    "granted_at": "2026-08-27T00:00:00Z",
                }
            }
        ),
        encoding="utf-8",
    )
    note_id = ""
    doc_id = ""
    course_id = ""

    process = start_sidecar(data_dir, token, asr_control=control, fake_summary=True)
    try:
        base_url, _ = wait_for_sidecar(process, token)
        with httpx.Client(trust_env=False) as client:
            headers = {"X-KnowRealm-Token": token}
            course_id = client.post(
                f"{base_url}/api/courses",
                headers=headers,
                json={
                    "name": "真实插座课程",
                    "learning_context": "INTEREST",
                    "depth": "BEGINNER",
                },
            ).json()["id"]
            note = client.post(
                f"{base_url}/api/text-captures",
                headers=headers,
                json={"capture_type": "QUICK_NOTE", "content": "真实插座速记\n\n正文"},
            ).json()
            note_id = note["record_id"]
            assert note["summary_job_id"] is None
            inbox_ids = {
                entry["id"] for entry in client.get(f"{base_url}/api/inbox", headers=headers).json()
            }
            assert note_id in inbox_ids

            classified = client.post(
                f"{base_url}/api/records/{note_id}/classification",
                headers=headers,
                json={"course_id": course_id},
            )
            assert classified.status_code == 200
            assert classified.json()["course_id"] == course_id
            assert classified.json()["status"] == "NOTE"
            assert (
                client.get(f"{base_url}/api/records/{note_id}/jobs", headers=headers).json()["jobs"]
                == []
            )
            inbox_after = {
                entry["id"] for entry in client.get(f"{base_url}/api/inbox", headers=headers).json()
            }
            assert note_id not in inbox_after

            batch = client.post(
                f"{base_url}/api/capture-batches",
                headers=headers,
                files=[("files", ("inbox.txt", b"real socket doc body", "text/plain"))],
            )
            assert batch.status_code == 202
            doc_id = batch.json()["record_id"]
            for _ in range(300):
                status = client.get(f"{base_url}/api/records/{doc_id}", headers=headers).json()[
                    "status"
                ]
                if status == "SUMMARY_PENDING":
                    break
                time.sleep(0.05)
            else:
                pytest.fail("未选课文档未停在 SUMMARY_PENDING")

            upgraded = client.post(
                f"{base_url}/api/records/{doc_id}/upgrade",
                headers=headers,
                json={"course_id": course_id},
            )
            assert upgraded.status_code == 200
            upgraded_body = upgraded.json()
            assert upgraded_body["record"]["course_id"] == course_id
            assert upgraded_body["record"]["status"] == "SUMMARY_PENDING"
            assert upgraded_body["summary_job_id"]
            for _ in range(300):
                status = client.get(f"{base_url}/api/records/{doc_id}", headers=headers).json()[
                    "status"
                ]
                if status == "SUMMARY_READY":
                    break
                time.sleep(0.05)
            else:
                pytest.fail("升级后总结未就绪")
            summary = client.get(f"{base_url}/api/records/{doc_id}/summary", headers=headers).json()
            assert summary["summary"] is not None
    finally:
        stop_process_tree(process)

    with sqlite3.connect(data_dir / "knowrealm.db") as connection:
        note_row = connection.execute(
            "SELECT course_id, status FROM records WHERE id = ?", (note_id,)
        ).fetchone()
        assert note_row == (course_id, "NOTE")
        note_job_count = connection.execute(
            "SELECT count(*) FROM processing_jobs WHERE record_id = ?", (note_id,)
        ).fetchone()[0]
        assert note_job_count == 0
        doc_row = connection.execute(
            "SELECT course_id, status FROM records WHERE id = ?", (doc_id,)
        ).fetchone()
        assert doc_row == (course_id, "SUMMARY_READY")
        summary_job_count = connection.execute(
            "SELECT count(*) FROM processing_jobs WHERE record_id = ? AND job_type = 'SUMMARY'",
            (doc_id,),
        ).fetchone()[0]
        assert summary_job_count == 1

    process = start_sidecar(data_dir, token, asr_control=control, fake_summary=True)
    try:
        base_url, _ = wait_for_sidecar(process, token)
        with httpx.Client(trust_env=False) as client:
            headers = {"X-KnowRealm-Token": token}
            restarted_note = client.get(f"{base_url}/api/records/{note_id}", headers=headers).json()
            assert restarted_note["course_id"] == course_id
            assert restarted_note["status"] == "NOTE"
            inbox_ids = {
                entry["id"] for entry in client.get(f"{base_url}/api/inbox", headers=headers).json()
            }
            assert note_id not in inbox_ids
            assert doc_id not in inbox_ids
    finally:
        stop_process_tree(process)


def test_real_process_export_then_import_archive_restores_data(tmp_path: Path) -> None:
    source = tmp_path / "Source"
    config = source / "config"
    config.mkdir(parents=True)
    provider = {
        "llm": {"base_url": "https://example.com/v1", "api_key": "sk-x", "model": "qwen-plus"}
    }
    (config / "providers.json").write_text(json.dumps(provider), encoding="utf-8")
    token = secrets.token_urlsafe(32)
    process = start_sidecar(source, token)
    course_id = ""
    archive = source / "exports" / "missing.zip"
    try:
        base_url, _ = wait_for_sidecar(process, token)
        with httpx.Client(
            base_url=base_url,
            headers={"X-KnowRealm-Token": token},
            trust_env=False,
        ) as client:
            course_id = client.post(
                "/api/courses",
                json={
                    "name": "真实导出导入课程",
                    "learning_context": "INTEREST",
                    "depth": "BEGINNER",
                },
            ).json()["id"]
            exported = client.post(
                "/api/settings/data-directory/export",
                json={"include_secrets": True},
            )
            assert exported.status_code == 200, exported.text
            archive = source / "exports" / exported.json()["file_name"]
    finally:
        stop_process_tree(process)

    assert archive.is_file()
    target = tmp_path / "Target"
    import_token = secrets.token_urlsafe(32)
    imported = start_sidecar(target, import_token, import_archive=archive)
    try:
        import_url, _ = wait_for_sidecar(imported, import_token)
        with httpx.Client(
            base_url=import_url,
            headers={"X-KnowRealm-Token": import_token},
            trust_env=False,
        ) as client:
            restored = client.get(f"/api/courses/{course_id}")
            assert restored.status_code == 200, restored.text
            assert restored.json()["name"] == "真实导出导入课程"
            assert client.get("/api/settings/data-directory/library-state").json() == {
                "empty_library": False
            }
    finally:
        stop_process_tree(imported)

    assert json.loads((target / "config" / "providers.json").read_text(encoding="utf-8"))[
        "llm"
    ]["api_key"] == "sk-x"


def test_real_process_import_archive_rejection_exits_without_residue(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    bad = tmp_path / "bad.zip"
    bad.write_text("not a zip", encoding="utf-8")
    token = secrets.token_urlsafe(32)
    process = start_sidecar(data_dir, token, import_archive=bad)
    try:
        _, stderr = process.communicate(timeout=20)
        assert process.returncode != 0
        assert "IMPORT_ARCHIVE_INVALID" in stderr.decode(errors="replace")
    finally:
        if process.poll() is None:
            stop_process_tree(process)

    assert not (data_dir / "knowrealm.db").exists()
    assert not (data_dir / "cache" / "import-archive").exists()
