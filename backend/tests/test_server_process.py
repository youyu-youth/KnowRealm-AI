import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


def stop_process_tree(process: subprocess.Popen[bytes]) -> tuple[bytes, bytes]:
    if process.poll() is None:
        if sys.platform == "win32":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.terminate()
    return process.communicate(timeout=10)


def test_real_process_selects_random_loopback_port_and_requires_token(tmp_path: Path) -> None:
    token = secrets.token_urlsafe(32)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "app.server",
            "--port",
            "0",
            "--token",
            token,
            "--data-dir",
            str(tmp_path / "KnowRealm"),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )
    assert process.stdout is not None
    port_line = process.stdout.readline()
    prefix = b"KNOWREALM_SIDECAR_PORT="
    assert port_line.startswith(prefix)
    port = int(port_line.removeprefix(prefix))
    assert port > 0
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

    assert token.encode() not in port_line + stdout
    assert token.encode() not in stderr
