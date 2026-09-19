"""网页剪藏适配器测试：SSRF 防护 / 重定向重校验 / 大小与类型限制 / 编码识别 /
垃圾正文判定——全部经 fake transport，不发真实网络（工单 03 契约）。"""

import asyncio
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.modules.capture.web_clip import (
    MAX_REDIRECTS,
    GuardedNetworkBackend,
    WebClipAdapter,
    WebClipError,
    assert_resolves_public,
    extract_clip,
    validate_public_http_url,
)

LONG_BODY = "这是一段足够长的中文正文内容，用于通过垃圾正文判定。" * 10


def html_page(body: str = LONG_BODY, title: str = "测试页面") -> str:
    return (
        "<html><head>"
        f'<meta charset="utf-8"/><title>{title}</title>'
        "</head><body>"
        f"<article><p>{body}</p></article>"
        "</body></html>"
    )


def mock_transport(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


async def _fake_getaddrinfo(*args: object, **kwargs: object) -> list[tuple[Any, ...]]:
    return [(None, None, None, None, ("93.184.216.34", 443))]


def stub_public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """fetch 层 DNS 预检也打桩：fake transport 契约=零真实网络（含 DNS 查询）。"""
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "getaddrinfo", _fake_getaddrinfo)


@pytest.mark.parametrize(
    "url",
    [
        "http://192.168.1.1/article",
        "http://127.0.0.1:8000/admin",
        "http://10.0.0.5/",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/",
        "http://[fe80::1]/",
        "ftp://example.com/article",
        "file:///etc/passwd",
        "http:///no-host",
        "",
    ],
)
def test_validate_rejects_restricted_or_invalid_urls(url: str) -> None:
    with pytest.raises(WebClipError):
        validate_public_http_url(url)


def test_validate_accepts_public_http_url() -> None:
    assert validate_public_http_url("https://example.com/article?a=1") is not None


@pytest.mark.anyio
async def test_fetch_extracts_markdown_with_title(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_public_dns(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/html; charset=utf-8"}, text=html_page()
        )

    clip = await WebClipAdapter(transport=mock_transport(handler)).fetch_and_extract(
        "https://example.com/article"
    )
    assert "足够长的中文正文" in clip.text
    assert clip.title == "测试页面"
    assert clip.metadata["kind"] == "web"
    assert clip.metadata["url"] == "https://example.com/article"


@pytest.mark.anyio
async def test_fetch_redirect_revalidates_target(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_public_dns(monkeypatch)
    """公网 302 → 私网目标：重定向后重新校验，拒绝而非跟随。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://192.168.0.10/inside"})

    with pytest.raises(WebClipError) as exc:
        await WebClipAdapter(transport=mock_transport(handler)).fetch("https://example.com/article")
    assert exc.value.code == "WEB_FETCH_BLOCKED_URL"


@pytest.mark.anyio
async def test_fetch_follows_safe_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_public_dns(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "https://example.com/new"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text=html_page())

    raw, final_url = await WebClipAdapter(transport=mock_transport(handler)).fetch(
        "https://example.com/old"
    )
    assert final_url == "https://example.com/new"
    assert b"<html>" in raw


@pytest.mark.anyio
async def test_fetch_rejects_redirect_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_public_dns(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://example.com/loop"})

    with pytest.raises(WebClipError) as exc:
        await WebClipAdapter(transport=mock_transport(handler)).fetch("https://example.com/loop")
    assert exc.value.code == "WEB_FETCH_UNREACHABLE"


@pytest.mark.anyio
async def test_fetch_rejects_redirect_count_over_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_public_dns(monkeypatch)
    state = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["count"] += 1
        return httpx.Response(302, headers={"location": f"https://example.com/hop{state['count']}"})

    with pytest.raises(WebClipError) as exc:
        await WebClipAdapter(transport=mock_transport(handler)).fetch("https://example.com/start")
    assert exc.value.code == "WEB_FETCH_UNREACHABLE"
    # 请求次数 = 首次 + 最多 5 次重定向
    assert state["count"] == MAX_REDIRECTS + 1


@pytest.mark.anyio
async def test_fetch_rejects_oversized_body(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_public_dns(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/html"}, content=b"x" * (5 * 1024 * 1024 + 1)
        )

    with pytest.raises(WebClipError) as exc:
        await WebClipAdapter(transport=mock_transport(handler)).fetch("https://example.com/big")
    assert exc.value.code == "WEB_FETCH_CONTENT_TOO_LARGE"


@pytest.mark.parametrize("content_type", ["application/json", "image/png", ""])
@pytest.mark.anyio
async def test_fetch_rejects_unsupported_content_type(
    content_type: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_public_dns(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": content_type}, text="{}")

    with pytest.raises(WebClipError) as exc:
        await WebClipAdapter(transport=mock_transport(handler)).fetch("https://example.com/api")
    assert exc.value.code == "WEB_FETCH_UNSUPPORTED_CONTENT_TYPE"


@pytest.mark.parametrize("status", [404, 503])
@pytest.mark.anyio
async def test_fetch_rejects_http_error_status(
    status: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_public_dns(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers={"content-type": "text/html"}, text="x")

    with pytest.raises(WebClipError) as exc:
        await WebClipAdapter(transport=mock_transport(handler)).fetch("https://example.com/missing")
    assert exc.value.code == "WEB_FETCH_UNREACHABLE"


def test_extract_clip_detects_gbk_encoding() -> None:
    raw = html_page(title="编码测试").replace('charset="utf-8"', 'charset="gbk"').encode("gbk")
    clip = extract_clip(raw, "https://example.com/gbk")
    assert clip.title == "编码测试"
    assert "足够长的中文正文" in clip.text


def test_extract_clip_rejects_undecodable_bytes() -> None:
    with pytest.raises(WebClipError) as exc:
        extract_clip(b"\xff\xfe\x00\xd8\x00\xff" * 200, "https://example.com/bin")
    assert exc.value.code == "WEB_FETCH_EXTRACT_FAILED"


def test_extract_clip_rejects_login_wall_thin_content() -> None:
    raw = html_page(body="请登录后查看全文", title="登录").encode()
    with pytest.raises(WebClipError) as exc:
        extract_clip(raw, "https://example.com/paywall")
    assert exc.value.code == "WEB_FETCH_EXTRACT_FAILED"


def test_extract_clip_rejects_duplicate_line_spam() -> None:
    # 重复行形态：逐段重复（占位页/刷屏页），单段长文本不属此形态
    spam_paragraphs = "<p>买一送一快来抢购</p>" * 60
    raw = html_page(body=spam_paragraphs, title="垃圾页").encode()
    with pytest.raises(WebClipError) as exc:
        extract_clip(raw, "https://example.com/spam")
    assert exc.value.code == "WEB_FETCH_EXTRACT_FAILED"


def test_extract_clip_metadata_fields() -> None:
    raw = (
        "<html><head><title>元数据页</title>"
        '<meta name="description" content="这是页面描述"/>'
        '<meta property="og:site_name" content="示例站"/>'
        "</head><body><article>" + LONG_BODY + "</article></body></html>"
    ).encode()
    clip = extract_clip(raw, "https://example.com/meta")
    assert clip.metadata["description"] == "这是页面描述"
    assert clip.metadata["sitename"] == "示例站"
    assert clip.metadata["title"] == "元数据页"


@pytest.mark.anyio
async def test_guarded_backend_blocks_private_dns_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DNS guard：域名解析到私网地址时拒绝，且不触达内层连接。"""

    class _Inner:
        async def connect_tcp(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("内网目标不应发起连接")

        async def sleep(self, seconds: float) -> None:
            return None

    async def fake_getaddrinfo(*args: object, **kwargs: object) -> list[tuple[Any, ...]]:
        return [(None, None, None, None, ("192.168.0.77", 80))]

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)
    backend = GuardedNetworkBackend(_Inner())  # type: ignore[arg-type]
    with pytest.raises(WebClipError) as exc:
        await backend.connect_tcp("internal.example.com", 80)
    assert exc.value.code == "WEB_FETCH_BLOCKED_URL"


@pytest.mark.anyio
async def test_guarded_backend_pins_resolved_public_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """公网解析结果以 IP 直连内层（钉住解析，防 rebinding 二次解析）。"""

    seen: dict[str, object] = {}

    class _Inner:
        async def connect_tcp(
            self,
            host: str,
            port: int,
            timeout: float | None = None,
            local_address: str | None = None,
            socket_options: Any = None,
        ) -> object:
            seen["host"] = host
            return object()

        async def sleep(self, seconds: float) -> None:
            return None

    async def fake_getaddrinfo(*args: object, **kwargs: object) -> list[tuple[Any, ...]]:
        return [(None, None, None, None, ("93.184.216.34", 443))]

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)
    backend = GuardedNetworkBackend(_Inner())  # type: ignore[arg-type]
    stream = await backend.connect_tcp("example.com", 443)
    assert stream is not None
    assert seen["host"] == "93.184.216.34"


@pytest.mark.anyio
async def test_fetch_dns_preflight_blocks_private_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """代理/预检路径：目标域名解析到私网即拒绝（fake transport 正常响应也不跟随）。"""

    async def fake_getaddrinfo(*args: object, **kwargs: object) -> list[tuple[Any, ...]]:
        return [(None, None, None, None, ("10.0.0.8", 80))]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text=html_page())

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(WebClipError) as exc:
        await WebClipAdapter(transport=mock_transport(handler)).fetch(
            "https://internal.example.com/doc"
        )
    assert exc.value.code == "WEB_FETCH_BLOCKED_URL"


@pytest.mark.anyio
async def test_fetch_dns_prefill_ignores_resolution_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """预检 DNS 解析失败放行（无外网测试环境零依赖），交由连接路径统一报错。"""

    async def fake_getaddrinfo(*args: object, **kwargs: object) -> list[tuple[Any, ...]]:
        raise OSError("no dns")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text=html_page())

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)
    raw, _final = await WebClipAdapter(transport=mock_transport(handler)).fetch(
        "https://example.com/article"
    )
    assert b"<html>" in raw


@pytest.mark.anyio
async def test_assert_resolves_public_literal_and_empty() -> None:
    await assert_resolves_public("93.184.216.34")
    await assert_resolves_public("")
