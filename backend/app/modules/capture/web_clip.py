"""网页剪藏受限抓取适配器（工单 03）：SSRF 防护 + trafilatura 正文提取。

安全边界（spec「网页剪藏安全边界」）：仅 HTTP(S)；拒绝 loopback/私网/链路
本地/云元数据地址；每次连接（含每跳重定向后）都在传输层重新解析并校验目标，
且解析、校验、直连同一结果（钉住 IP，防 DNS rebinding）；限制响应体（解压后）
大小、重定向次数、连接/读取超时与 Content-Type 白名单。不执行 JS、不加载
第三方子资源、不持久化原始 HTML——trafilatura 只见解码后的文本，产出净化
Markdown 快照。测试经 transport 注入 fake（不发真实网络，DNS guard 不参与）。
"""

import asyncio
import ipaddress
import os
import re
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpcore
import httpx
from trafilatura import extract as trafilatura_extract
from trafilatura import extract_metadata
from trafilatura.utils import detect_encoding

MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 1024 * 1024
MAX_REDIRECTS = 5
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 20.0
ALLOWED_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml"})

# 垃圾正文判定阈值：登录墙/占位页常表现为过短或大量重复行。
MIN_CONTENT_CHARS = 200
MAX_DUPLICATE_LINE_RATIO = 0.8


class WebClipError(Exception):
    """受限抓取/提取失败的稳定分类；code 值域与 ProcessingJobErrorCode 对齐。"""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ClipContent:
    text: str
    title: str | None
    metadata: dict[str, Any]


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        # 云元数据服务端点（169.254.169.254 等）已由 is_link_local 覆盖；
        # IPv4-mapped IPv6（::ffff:10.0.0.1）按映射前地址判定。
        or (
            isinstance(ip, ipaddress.IPv6Address)
            and ip.ipv4_mapped is not None
            and not _is_public_ip(ip.ipv4_mapped)
        )
    )


def _assert_public_literal(host: str) -> None:
    """按字面解析校验 host：IP 直连立即拒绝内网地址（域名解析校验见 backend guard）。"""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    if not _is_public_ip(ip):
        raise WebClipError("WEB_FETCH_BLOCKED_URL", "目标地址属于受限网络范围")


def validate_public_http_url(url: str) -> str:
    """ingest 预检与每跳重定向共用的 URL 校验：仅 http(s) 且主机可解析。"""
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https"):
        raise WebClipError("WEB_FETCH_INVALID_URL", "仅支持 http(s) 地址")
    host = parsed.hostname
    if not host:
        raise WebClipError("WEB_FETCH_INVALID_URL", "地址缺少主机名")
    _assert_public_literal(host)
    return url


class GuardedNetworkBackend(httpcore.AsyncNetworkBackend):
    """DNS guard：连接前解析域名、校验全部候选 IP，并直连首个公网结果。

    httpcore 的 TLS 握手以请求原始域名做 SNI，与连接 IP 解耦——因此解析、
    校验、连接在同一处完成后不存在 rebinding 窗口（上层不会二次解析）。
    """

    def __init__(self, inner: httpcore.AsyncNetworkBackend) -> None:
        self._inner = inner

    async def connect_tcp(  # type: ignore[override]
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            loop = asyncio.get_running_loop()
            infos = await loop.getaddrinfo(
                host,
                port,
                type=socket.SOCK_STREAM,  # type: ignore[arg-type]
            )
            candidates = [sockaddr[0] for _family, _kind, _proto, _canon, sockaddr in infos]
            for candidate in candidates:
                try:
                    address = ipaddress.ip_address(candidate)
                except ValueError:
                    continue
                if not _is_public_ip(address):
                    raise WebClipError(
                        "WEB_FETCH_BLOCKED_URL", "目标域名解析到受限网络地址"
                    ) from None
            if not candidates:
                raise WebClipError("WEB_FETCH_UNREACHABLE", "目标域名无法解析") from None
            ip = ipaddress.ip_address(candidates[0])
        if not _is_public_ip(ip):
            raise WebClipError("WEB_FETCH_BLOCKED_URL", "目标地址属于受限网络范围")
        return await self._inner.connect_tcp(
            str(ip),
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(  # type: ignore[override]
        self, path: str, timeout: float | None = None, socket_options: Any = None
    ) -> httpcore.AsyncNetworkStream:
        raise WebClipError("WEB_FETCH_UNREACHABLE", "不支持 Unix socket 连接")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


def _decode_html(raw: bytes) -> str:
    """以原始 bytes 做编码识别：meta charset 声明优先（GBK/EUC 系字节范围重叠，
    sniff 短文本易误判），声明缺失或解码失败再退 charset_normalizer 候选。"""
    declared = re.search(rb'charset=["\']?([A-Za-z0-9_.:-]+)', raw[:2048], re.IGNORECASE)
    candidates: list[str] = []
    if declared is not None:
        candidates.append(declared.group(1).decode("ascii", errors="ignore"))
    candidates.extend((detect_encoding(raw) or ("utf-8",))[:3])
    for encoding in candidates:
        if not encoding:
            continue
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    raise WebClipError("WEB_FETCH_EXTRACT_FAILED", "无法识别页面编码")


def _assert_meaningful(text: str) -> None:
    """垃圾正文判定：None/过短/重复行占比过高（登录墙与占位页的典型形态）。"""
    if len(text.strip()) < MIN_CONTENT_CHARS:
        raise WebClipError("WEB_FETCH_EXTRACT_FAILED", "页面正文过短或为空")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines:
        duplicate_ratio = 1 - len(set(lines)) / len(lines)
        if duplicate_ratio > MAX_DUPLICATE_LINE_RATIO:
            raise WebClipError("WEB_FETCH_EXTRACT_FAILED", "页面正文重复内容过多")


def extract_clip(raw: bytes, url: str) -> ClipContent:
    """编码识别 + trafilatura 抽取正文与元数据 + 垃圾判定；原始 HTML 不出本函数。"""
    html = _decode_html(raw)
    metadata = extract_metadata(html, default_url=url)
    text = (trafilatura_extract(html, url=url, output_format="markdown") or "").strip()
    _assert_meaningful(text)
    if len(text.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
        raise WebClipError("WEB_FETCH_CONTENT_TOO_LARGE", "页面正文超过 1 MiB 上限")
    meta: dict[str, Any] = {"kind": "web", "url": url}
    for key in ("title", "author", "date", "description", "sitename"):
        value = getattr(metadata, key, None)
        if value:
            meta[key] = value
    return ClipContent(text=text, title=meta.get("title"), metadata=meta)


def _production_transport() -> httpx.AsyncBaseTransport:
    """生产 transport：环境有代理时尊重系统代理（代理=可信出口，对齐 B1 trust_env
    语义）；直连时换 DNS guard 连接池（逐连接解析校验 + IP 钉住）。"""
    proxy_env = any(
        os.environ.get(name)
        for name in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        )
    )
    if proxy_env:
        return httpx.AsyncHTTPTransport(trust_env=True)

    class _GuardedTransport(httpx.AsyncHTTPTransport):
        def __init__(self) -> None:
            super().__init__()
            self._pool = httpcore.AsyncConnectionPool(  # type: ignore[reportPrivateUsage]
                network_backend=GuardedNetworkBackend(httpcore.AsyncNetworkBackend())
            )

    return _GuardedTransport()


class WebClipAdapter:
    """受限抓取 + 正文提取；transport 注入供测试替换（生产走 DNS guarded backend）。"""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        timeout = httpx.Timeout(connect=CONNECT_TIMEOUT, read=READ_TIMEOUT, write=10, pool=10)
        if self._transport is not None:
            return httpx.AsyncClient(
                transport=self._transport, follow_redirects=False, timeout=timeout
            )
        return httpx.AsyncClient(
            transport=_production_transport(), follow_redirects=False, timeout=timeout
        )

    async def fetch(self, url: str) -> tuple[bytes, str]:
        """受限抓取：手动跟随重定向（每跳重新校验目标），流式读取限制解压后大小。"""
        current = validate_public_http_url(url)
        try:
            return await self._fetch_following(current)
        except WebClipError:
            raise
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise WebClipError("WEB_FETCH_UNREACHABLE", "目标站点无法访问") from exc

    async def _fetch_following(self, current: str) -> tuple[bytes, str]:
        async with self._client() as client:
            for _redirect in range(MAX_REDIRECTS + 1):
                async with client.stream("GET", current) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise WebClipError("WEB_FETCH_UNREACHABLE", "重定向响应缺少目标地址")
                        current = validate_public_http_url(urljoin(current, location))
                        continue
                    if response.status_code >= 400:
                        raise WebClipError(
                            "WEB_FETCH_UNREACHABLE", f"目标返回 HTTP {response.status_code}"
                        )
                    media_type = (
                        response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    )
                    if media_type not in ALLOWED_CONTENT_TYPES:
                        raise WebClipError(
                            "WEB_FETCH_UNSUPPORTED_CONTENT_TYPE",
                            f"不支持的页面类型 {media_type or '未知'}",
                        )
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_RESPONSE_BYTES:
                            raise WebClipError(
                                "WEB_FETCH_CONTENT_TOO_LARGE", "页面响应体超过 5 MiB 上限"
                            )
                        chunks.append(chunk)
                    return b"".join(chunks), current
        raise WebClipError("WEB_FETCH_UNREACHABLE", "重定向次数超过上限")

    async def fetch_and_extract(self, url: str) -> ClipContent:
        raw, final_url = await self.fetch(url)
        return extract_clip(raw, final_url)
