import secrets
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


def random_local_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def stop_process_tree(process: subprocess.Popen[bytes]) -> tuple[bytes, bytes]:
    if process.poll() is None:
        if sys.platform == "win32":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.terminate()
    return process.communicate(timeout=10)


def test_real_process_uses_random_loopback_port_and_requires_token(tmp_path: Path) -> None:
    port = random_local_port()
    token = secrets.token_urlsafe(32)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "app.server",
            "--port",
            str(port),
            "--token",
            token,
            "--data-dir",
            str(tmp_path / "KnowRealm"),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )
    base_url = f"http://127.0.0.1:{port}"

    try:
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
                        break
                except httpx.ConnectError:
                    pass
                time.sleep(0.1)
            else:
                pytest.fail("sidecar 未在随机本机端口启动")

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

    assert token.encode() not in stdout
    assert token.encode() not in stderr
