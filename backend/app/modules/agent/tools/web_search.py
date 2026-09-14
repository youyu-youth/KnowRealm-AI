"""chat 联网搜索工具（B1）：模型自行决定搜索时机与关键词，Tavily 检索网络。

运行期凭据经 ContextVar 每轮生成前绑定（模式同 search_transcript）：仅在
本轮 web_search 生效时绑定并挂载工具，AgentConfig 常量语义因此维持。请求
失败不抛错——返回错误 JSON 载荷让模型可向用户说明，流不中断。
"""

import json
from contextvars import ContextVar, Token

import httpx
from langchain_core.tools import tool

from app.modules.search.web_search import SearchProvider, WebSearchError

WEB_SEARCH_LIMIT = 5
# 单条 content 摘要截断长度，控制工具结果回喂体积。
WEB_SEARCH_CONTENT_MAX_CHARS = 400


_web_search_context: ContextVar[SearchProvider | None] = ContextVar(
    "chat_web_search_context", default=None
)


def bind_web_search(provider: SearchProvider) -> Token[SearchProvider | None]:
    return _web_search_context.set(provider)


def reset_web_search(token: Token[SearchProvider | None]) -> None:
    _web_search_context.reset(token)


def _payload(hits: list[dict[str, object]], *, ok: bool = True, message: str = "") -> str:
    body: dict[str, object] = {"hits": hits, "ok": ok}
    if message:
        body["message"] = message
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


@tool
async def web_search(query: str) -> str:
    """联网搜索公开网络信息。

    当问题涉及最新版本、行业动态、时效性新闻，或你不确定的知识背景时使用：
    用简洁的搜索词描述要查的内容，可多次搜索、逐步细化。结果包含网页标题、
    URL 与内容摘要；引用搜索得到的结论时，须在回答末尾引用块中以
    「[n] 标题 — URL」格式注明来源，不要编造搜索结果里不存在的内容。
    """
    provider = _web_search_context.get()
    if provider is None:
        return _payload([], ok=False, message="本轮对话未启用联网搜索。")
    try:
        hits = await provider.search(query, max_results=WEB_SEARCH_LIMIT)
    except WebSearchError as exc:
        return _payload([], ok=False, message=str(exc))
    except httpx.RequestError:
        return _payload([], ok=False, message="网络请求失败，无法连接搜索服务，请稍后重试。")
    if not hits:
        return _payload([], message="未找到相关结果；可换同义词或相关关键词重试。")
    return _payload(
        [
            {
                "title": hit.title,
                "url": hit.url,
                "content": hit.content[:WEB_SEARCH_CONTENT_MAX_CHARS],
            }
            for hit in hits
        ]
    )
