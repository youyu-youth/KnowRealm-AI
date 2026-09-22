"""外部联网搜索（B1）：薄 SearchProvider 抽象与统一结果类型。

仅 Tavily 一家实现（落 integrations/tavily.py），不做注册表/工厂
（博查/智谱真接入时再扩）。
"""

from dataclasses import dataclass
from typing import Protocol


class WebSearchError(Exception):
    """搜索服务返回不可用响应（非 200 / 坏 JSON），message 面向模型与用户可读。"""

    def __init__(
        self,
        message: str,
        *,
        code: str = "WEB_SEARCH_PROVIDER_ERROR",
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class WebSearchHit:
    """统一搜索结果条目（SearchProvider 抽象的结果类型）。"""

    title: str
    url: str
    content: str


class SearchProvider(Protocol):
    async def search(self, query: str, *, max_results: int) -> list[WebSearchHit]: ...
