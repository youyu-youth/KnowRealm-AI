"""错误码契约抽查（界面语言切换工单 20-03）。

γ′ 附加字段契约：全部错误响应携带稳定 code（{detail, code, params?}），
detail 中文原文保留——既有测试只断言 detail，本文件只补 code 形状。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app.main import create_app
from app.modules.record.service import RecordService

TOKEN = "test-launch-token"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


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


@pytest.mark.anyio
async def test_missing_launch_token_returns_coded_403(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (app, _client):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
        ) as anonymous:
            response = await anonymous.get("/api/inbox")

    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "LAUNCH_TOKEN_INVALID"
    assert body["detail"] == "无权访问本地服务"
    assert "params" not in body


@pytest.mark.anyio
async def test_unknown_route_falls_back_to_generic_code(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (_app, client):
        response = await client.get("/api/no-such-route")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "HTTP_ERROR"


@pytest.mark.anyio
async def test_validation_error_returns_generic_422_code(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (_app, client):
        response = await client.post("/api/chat-sessions", json={"mode": 123})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "REQUEST_VALIDATION_FAILED"
    assert body["detail"]


@pytest.mark.anyio
async def test_chat_message_without_provider_returns_coded_409(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (_app, client):
        created = await client.post("/api/chat-sessions", json={})
        session_id = created.json()["id"]
        response = await client.post(
            f"/api/chat-sessions/{session_id}/turns",
            json={"content": "你好", "web_search": False, "request_id": "req-errc-01"},
        )

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "LLM_PROVIDER_UNCONFIGURED"
    assert body["detail"] == "LLM_PROVIDER_UNCONFIGURED：未配置 AI 服务，请先完成供应商配置"
    assert "params" not in body


@pytest.mark.anyio
async def test_unhandled_error_returns_500_code_with_request_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def explode(_session: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(RecordService, "list_inbox", explode)
    async with running_app(tmp_path) as (_app, client):
        response = await client.get("/api/inbox")

    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "INTERNAL_ERROR"
    assert body["params"]["request_id"]
    assert body["params"]["request_id"] in body["detail"]
