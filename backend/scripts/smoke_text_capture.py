"""真实 localhost socket 冒烟：无课程文本捕获 → Inbox 可见 → 删除 → 重启后仍不可见。

与 ASGI（pytest 传输）、MSW（前端 mock）证据分开：本脚本通过真实 TCP socket
访问 uvicorn 监听的 127.0.0.1 端口，验证启动令牌与重启持久化。
"""

import asyncio
import socket
import tempfile
from pathlib import Path

import httpx
import uvicorn

from app.main import create_app

TOKEN = "smoke-launch-token"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def run_server(
    data_dir: Path,
    port: int,
    handle: dict[str, uvicorn.Server],
) -> None:
    app = create_app(data_dir=data_dir, launch_token=TOKEN)
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        lifespan="on",
    )
    server = uvicorn.Server(config)
    handle["server"] = server
    await server.serve()


async def stop_server(
    handle: dict[str, uvicorn.Server],
    task: asyncio.Task[None],
) -> None:
    # 优雅退出让 lifespan 释放数据目录锁；直接 cancel 会残留 .knowrealm.lock。
    while "server" not in handle:
        await asyncio.sleep(0.05)
    handle["server"].should_exit = True
    await asyncio.wait_for(task, timeout=15)


async def wait_ready(client: httpx.AsyncClient) -> None:
    for _ in range(100):
        try:
            await client.get("/api/health")
            return
        except httpx.HTTPError:
            await asyncio.sleep(0.1)
    raise RuntimeError("sidecar 未在真实端口就绪")


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="knowrealm-smoke-") as raw_dir:
        data_dir = Path(raw_dir)
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        first_handle: dict[str, uvicorn.Server] = {}
        server_task = asyncio.create_task(run_server(data_dir, port, first_handle))
        async with httpx.AsyncClient(base_url=base_url, timeout=5) as client:
            await wait_ready(client)

            no_token = await client.post(
                "/api/text-captures",
                json={"capture_type": "QUICK_NOTE", "content": "无令牌"},
            )
            assert no_token.status_code == 403, no_token.text
            headers = {"X-KnowRealm-Token": TOKEN}

            created = await client.post(
                "/api/text-captures",
                json={
                    "capture_type": "PASTE",
                    "content": "冒烟正文第一行\n\n第二段",
                },
                headers=headers,
            )
            assert created.status_code == 201, created.text
            record_id = created.json()["record_id"]
            assert created.json()["summary_job_id"] is None

            inbox = await client.get("/api/inbox", headers=headers)
            assert inbox.status_code == 200, inbox.text
            assert [item["id"] for item in inbox.json()] == [record_id]
            assert inbox.json()[0]["status"] == "NOTE"
            assert inbox.json()[0]["title"] == "冒烟正文第一行"
            print("SMOKE: 捕获后 Inbox 可见")

            deleted = await client.delete(f"/api/records/{record_id}", headers=headers)
            assert deleted.status_code == 204, deleted.text
            inbox_after_delete = await client.get("/api/inbox", headers=headers)
            assert inbox_after_delete.json() == []
            print("SMOKE: 删除后 Inbox 为空")

        await stop_server(first_handle, server_task)

        restart_port = free_port()
        restart_handle: dict[str, uvicorn.Server] = {}
        restart_task = asyncio.create_task(run_server(data_dir, restart_port, restart_handle))
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{restart_port}", timeout=5
        ) as client:
            await wait_ready(client)
            inbox_restart = await client.get("/api/inbox", headers={"X-KnowRealm-Token": TOKEN})
            assert inbox_restart.status_code == 200, inbox_restart.text
            assert inbox_restart.json() == []
            print("SMOKE: 重启后 Inbox 仍不可见")
        await stop_server(restart_handle, restart_task)
    print("SMOKE: 全部通过")


if __name__ == "__main__":
    asyncio.run(main())
