"""Tavily 搜索集成（B1 唯一 SearchProvider 实现）：httpx 直连单端点 REST，零新依赖。

与 LLM 端点 trust_env=False 的动机不同：api.tavily.com 需外网，
trust_env=True 尊重系统代理（国内用户常挂代理）——spec 根决策 3 定稿。
"""

from typing import cast

import httpx

from app.modules.search.web_search import WebSearchError, WebSearchHit

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
# 单次搜索请求超时；联网工具在模型循环内同步执行，过长会拖住整轮回答。
WEB_SEARCH_TIMEOUT_SECONDS = 10.0
_TERMINAL_STATUS_CODES = frozenset({401, 432, 433})
_HTTP_ERRORS: dict[int, tuple[str, bool, str]] = {
    401: (
        "WEB_SEARCH_AUTH_FAILED",
        False,
        "Tavily API 密钥无效，请在设置中重新配置。",
    ),
    429: (
        "WEB_SEARCH_RATE_LIMITED",
        True,
        "Tavily 请求过于频繁，请稍后重试。",
    ),
    432: (
        "WEB_SEARCH_PLAN_LIMIT_EXCEEDED",
        False,
        "Tavily 套餐额度已用尽，请前往 Tavily Dashboard 检查用量或升级套餐。",
    ),
    433: (
        "WEB_SEARCH_PAYG_LIMIT_EXCEEDED",
        False,
        "Tavily 按量付费额度已用尽，请前往 Tavily Dashboard 提高限额。",
    ),
}


class TavilySearchClient:
    """Tavily REST 直连客户端：POST /search + Bearer key，每次调用独立建连。"""

    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = WEB_SEARCH_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._transport = transport
        self._terminal_error: WebSearchError | None = None

    async def search(self, query: str, *, max_results: int) -> list[WebSearchHit]:
        if self._terminal_error is not None:
            raise self._terminal_error
        async with httpx.AsyncClient(
            timeout=self._timeout, trust_env=True, transport=self._transport
        ) as client:
            response = await client.post(
                TAVILY_SEARCH_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"query": query, "max_results": max_results},
            )
        if response.status_code != 200:
            code, retryable, message = _HTTP_ERRORS.get(
                response.status_code,
                (
                    "WEB_SEARCH_PROVIDER_UNAVAILABLE"
                    if response.status_code >= 500
                    else "WEB_SEARCH_PROVIDER_ERROR",
                    response.status_code >= 500,
                    "Tavily 搜索服务暂时不可用，请稍后重试。"
                    if response.status_code >= 500
                    else f"Tavily 搜索服务返回 HTTP {response.status_code}。",
                ),
            )
            error = WebSearchError(message, code=code, retryable=retryable)
            if response.status_code in _TERMINAL_STATUS_CODES:
                self._terminal_error = error
            raise error
        try:
            payload: object = response.json()
        except ValueError as exc:
            raise WebSearchError("搜索服务返回了无法解析的响应") from exc
        return _parse_results(payload)


def _parse_results(payload: object) -> list[WebSearchHit]:
    if not isinstance(payload, dict):
        raise WebSearchError("搜索服务响应缺少 results 字段")
    results = cast(dict[str, object], payload).get("results")
    if not isinstance(results, list):
        raise WebSearchError("搜索服务响应缺少 results 字段")
    hits: list[WebSearchHit] = []
    for item in cast(list[object], results):
        if not isinstance(item, dict):
            continue
        entry = cast(dict[str, object], item)
        title = entry.get("title")
        url = entry.get("url")
        if not isinstance(title, str) or not title or not isinstance(url, str) or not url:
            continue
        content = entry.get("content")
        hits.append(
            WebSearchHit(title=title, url=url, content=content if isinstance(content, str) else "")
        )
    return hits
