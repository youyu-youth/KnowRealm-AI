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
            "--token",
            token,
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
                'record-http', '11111111-1111-4111-8111-111111111111',
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
                    "id": "record-http",
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
            assert (
                client.get(
                    f"{base_url}/api/courses/11111111-1111-4111-8111-111111111111/records"
                ).status_code
                == 403
            )
    finally:
        stdout, stderr = stop_process_tree(process)

    assert token.encode() not in port_line + stdout
    assert token.encode() not in stderr
