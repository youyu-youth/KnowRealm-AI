import asyncio
import secrets
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from app.db.migrations import run_migrations


def start_sidecar(data_dir: Path, token: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "app.server",
            "--port",
            "0",
            f"--token={token}",
            "--data-dir",
            str(data_dir),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )


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
