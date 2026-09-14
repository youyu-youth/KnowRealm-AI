"""B1 联网搜索：Tavily 客户端四态（MockTransport）、web_search 工具载荷与设置端点。"""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app.main import create_app
from app.modules.agent.tools.web_search import (
    bind_web_search,
    reset_web_search,
    web_search,
)
from app.modules.search.integrations.tavily import TavilySearchClient
from app.modules.search.web_search import WebSearchError, WebSearchHit

TOKEN = "test-launch-token"
WEB_SEARCH_URL = "/api/settings/providers/web-search"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# TavilySearchClient：MockTransport 四态（正常解析 / 非 200 / 坏 JSON / 请求错误）。
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_tavily_normal_response_parses_hits_and_request_shape() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "标题甲", "url": "https://a.example.com", "content": "内容甲"},
                    {"title": "无内容条目", "url": "https://b.example.com"},
                    {"url": "https://c.example.com"},  # 缺 title：跳过
                    {"title": "", "url": "https://d.example.com"},  # 空 title：跳过
                    "非 dict 条目：跳过",
                ]
            },
        )

    client = TavilySearchClient("tvly-key", transport=httpx.MockTransport(handler))
    hits = await client.search("傅里叶变换", max_results=5)

    assert [(hit.title, hit.url, hit.content) for hit in hits] == [
        ("标题甲", "https://a.example.com", "内容甲"),
        ("无内容条目", "https://b.example.com", ""),
    ]
    request = requests[0]
    assert str(request.url) == "https://api.tavily.com/search"
    assert request.headers["Authorization"] == "Bearer tvly-key"
    assert json.loads(request.content) == {"query": "傅里叶变换", "max_results": 5}


@pytest.mark.anyio
async def test_tavily_non_200_raises_web_search_error() -> None:
    client = TavilySearchClient(
        "tvly-key", transport=httpx.MockTransport(lambda request: httpx.Response(401))
    )
    with pytest.raises(WebSearchError, match="HTTP 401"):
        await client.search("query", max_results=1)


@pytest.mark.anyio
async def test_tavily_bad_json_raises_web_search_error() -> None:
    client = TavilySearchClient(
        "tvly-key",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text="<html>")),
    )
    with pytest.raises(WebSearchError):
        await client.search("query", max_results=1)


@pytest.mark.anyio
async def test_tavily_missing_results_field_raises_web_search_error() -> None:
    client = TavilySearchClient(
        "tvly-key", transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    )
    with pytest.raises(WebSearchError):
        await client.search("query", max_results=1)


@pytest.mark.anyio
async def test_tavily_request_error_propagates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    client = TavilySearchClient("tvly-key", transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.ConnectTimeout):
        await client.search("query", max_results=1)


# ---------------------------------------------------------------------------
# web_search 工具：对外 JSON 载荷行为（结果 / 错误 / 未绑定）。
# ---------------------------------------------------------------------------


class FakeProvider:
    def __init__(
        self,
        hits: list[WebSearchHit] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.hits = hits if hits is not None else []
        self.error = error
        self.max_results: int | None = None

    async def search(self, query: str, *, max_results: int) -> list[WebSearchHit]:
        self.max_results = max_results
        if self.error is not None:
            raise self.error
        return self.hits


async def call_web_search(query: str, provider: object) -> str:
    token = bind_web_search(provider)  # type: ignore[arg-type]
    try:
        return await web_search.ainvoke({"query": query})
    finally:
        reset_web_search(token)


@pytest.mark.anyio
async def test_web_search_tool_returns_hits_with_truncated_content() -> None:
    from app.modules.agent.tools.web_search import WEB_SEARCH_CONTENT_MAX_CHARS

    provider = FakeProvider(
        hits=[
            WebSearchHit(title="长文", url="https://example.com", content="字" * 500),
        ]
    )
    payload = json.loads(await call_web_search("查询", provider))

    assert provider.max_results == 5
    assert payload["ok"] is True
    assert payload["hits"] == [
        {
            "title": "长文",
            "url": "https://example.com",
            "content": "字" * WEB_SEARCH_CONTENT_MAX_CHARS,
        }
    ]


@pytest.mark.anyio
async def test_web_search_tool_empty_hits_carries_retry_message() -> None:
    payload = json.loads(await call_web_search("查询", FakeProvider(hits=[])))

    assert payload["ok"] is True
    assert payload["hits"] == []
    assert "重试" in payload["message"]


@pytest.mark.anyio
async def test_web_search_tool_service_error_returns_error_payload() -> None:
    provider = FakeProvider(error=WebSearchError("搜索服务返回 HTTP 401"))
    payload = json.loads(await call_web_search("查询", provider))

    # 失败不抛错：返回错误载荷（ok=false + message），模型可据此向用户说明。
    assert payload == {"hits": [], "ok": False, "message": "搜索服务返回 HTTP 401"}


@pytest.mark.anyio
async def test_web_search_tool_network_error_returns_error_payload() -> None:
    provider = FakeProvider(error=httpx.ConnectTimeout("timed out"))
    payload = json.loads(await call_web_search("查询", provider))

    assert payload["ok"] is False
    assert payload["hits"] == []
    assert "网络请求失败" in payload["message"]


@pytest.mark.anyio
async def test_web_search_tool_unbound_returns_error_payload() -> None:
    payload = json.loads(await web_search.ainvoke({"query": "查询"}))

    assert payload["ok"] is False
    assert "未启用联网搜索" in payload["message"]


# ---------------------------------------------------------------------------
# 设置端点三件套：GET/PUT 读写与 tests 连通性（对齐 llm/tencent-asr 卡模式）。
# ---------------------------------------------------------------------------


def patch_routes_tavily(
    monkeypatch: pytest.MonkeyPatch, transport: httpx.AsyncBaseTransport
) -> None:
    class _Transported(TavilySearchClient):
        def __init__(self, api_key: str) -> None:
            super().__init__(api_key, transport=transport)

    monkeypatch.setattr("app.modules.settings.routes.TavilySearchClient", _Transported)


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
async def test_web_search_provider_masks_key_and_preserves_empty_key(tmp_path: Path) -> None:
    async with running_app(tmp_path / "KnowRealm") as (_app, client):
        missing = await client.get(WEB_SEARCH_URL)
        saved = await client.put(
            WEB_SEARCH_URL, json={"provider": "tavily", "api_key": "tvly-secret"}
        )
        key_kept = await client.put(WEB_SEARCH_URL, json={"provider": "tavily", "api_key": ""})
        cleared = await client.put(
            WEB_SEARCH_URL, json={"provider": "tavily", "api_key": "", "clear_api_key": True}
        )

    assert missing.status_code == 200
    assert missing.json() == {"provider": None}
    assert saved.status_code == 200
    assert saved.json() == {
        "provider": {"provider": "tavily", "has_api_key": True, "api_key_hint": "••••cret"}
    }
    assert "tvly-secret" not in saved.text
    # 空 key 保存保留旧值；clear 语义清除。
    assert key_kept.json() == saved.json()
    assert cleared.json() == {
        "provider": {"provider": "tavily", "has_api_key": False, "api_key_hint": None}
    }

    providers = json.loads(
        (tmp_path / "KnowRealm" / "config" / "providers.json").read_text(encoding="utf-8")
    )
    assert providers["web_search"] == {"provider": "tavily", "api_key": ""}


@pytest.mark.anyio
async def test_web_search_provider_rejects_unknown_vendor(tmp_path: Path) -> None:
    async with running_app(tmp_path / "KnowRealm") as (_app, client):
        bad = await client.put(WEB_SEARCH_URL, json={"provider": "bocha", "api_key": "tvly-key"})

    # 本期只认 tavily（spec 根决策 2）：坏 provider 值 422 拒绝。
    assert bad.status_code == 422


@pytest.mark.anyio
async def test_web_search_connection_test_uses_real_minimal_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"results": [{"title": "t", "url": "https://example.com", "content": "c"}]},
        )

    patch_routes_tavily(monkeypatch, httpx.MockTransport(handler))
    async with running_app(tmp_path / "KnowRealm") as (_app, client):
        unconfigured = await client.post(f"{WEB_SEARCH_URL}/tests")
        await client.put(WEB_SEARCH_URL, json={"provider": "tavily", "api_key": "tvly-secret"})
        ok = await client.post(f"{WEB_SEARCH_URL}/tests")

    # 未配置 409；测试 = 一次真实极简搜索（max_results=1，Tavily 计 1 credit）。
    assert unconfigured.status_code == 409
    assert unconfigured.json()["code"] == "WEB_SEARCH_KEY_NOT_CONFIGURED"
    assert ok.status_code == 200
    assert ok.json() == {"ok": True, "provider": "tavily"}
    assert json.loads(requests[0].content) == {"query": "hello", "max_results": 1}


class QueueTransport(httpx.AsyncBaseTransport):
    """按队列依次返回响应或抛出异常的替身传输。"""

    def __init__(self, outcomes: list[httpx.Response | Exception]) -> None:
        self.outcomes = outcomes

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.mark.anyio
async def test_web_search_connection_test_maps_service_and_network_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_routes_tavily(
        monkeypatch,
        QueueTransport([httpx.Response(401), httpx.ConnectTimeout("timed out")]),
    )
    async with running_app(tmp_path / "KnowRealm") as (_app, client):
        await client.put(WEB_SEARCH_URL, json={"provider": "tavily", "api_key": "tvly-secret"})
        service_error = await client.post(f"{WEB_SEARCH_URL}/tests")
        network_error = await client.post(f"{WEB_SEARCH_URL}/tests")

    assert service_error.status_code == 502
    assert service_error.json()["code"] == "WEB_SEARCH_TEST_FAILED"
    assert network_error.status_code == 502
    assert network_error.json()["code"] == "WEB_SEARCH_UNREACHABLE"
