"""受限原文取回共用业务读取与工具预算。"""

import json

from langchain_core.tools import tool
from pydantic import ValidationError

from app.modules.agent.budget.service import budgeted, format_output, mark_output
from app.modules.agent.context_budget.retrieval import read_context as read_source
from app.modules.agent.context_budget.retrieval import search_context as find_sources
from app.modules.agent.context_budget.schemas import ContextReadRequest, ContextSearchRequest
from app.modules.agent.runtime import ToolCallBudget, current_agent_runtime
from app.modules.agent.tools.search_library import (
    TOOL_RESULT_MAX_CHARS,
    TOOL_ROUND_OUTPUT_MAX_CHARS,
)
from app.shared.errors import CodedHTTPException


def _rejection() -> str:
    return json.dumps({"ok": False, "error": "TOOL_CALL_LIMIT"})


def _bounded(body: dict[str, object], budget: ToolCallBudget) -> str:
    limit = min(TOOL_RESULT_MAX_CHARS, TOOL_ROUND_OUTPUT_MAX_CHARS - budget.chars_fed)
    payload = json.dumps(body, ensure_ascii=False)
    if len(payload) > limit:
        content = body.get("content")
        if isinstance(content, str):
            # 按更小尺寸重新读取才能得到正确的继续游标，绝不伪造进度。
            return json.dumps(
                {
                    "ok": False,
                    "error": "CONTEXT_READ_BUDGET_EXHAUSTED",
                    "message": "本轮字符额度不足，请减少 max_chars 或下一轮继续读取。",
                },
                ensure_ascii=False,
            )
        return json.dumps({"ok": False, "error": "CONTEXT_READ_BUDGET_EXHAUSTED"})
    mark_output(payload)
    return payload


@tool
@budgeted(_rejection)
async def search_context(query: str = "", cursor: str | None = None, limit: int = 4) -> str:
    """查找当前会话、当前上下文段的原消息和大工具输出，返回可读取来源及版本。

    追问摘要省略的细节时使用关键词查找；空 query 列出来源，next_cursor 继续查找。
    资料细节优先 search_library。结果是定位，不能当成逐字证据，不跨会话/段。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps({"ok": False, "error": "AGENT_CONTEXT_UNBOUND"})
    try:
        result = await find_sources(
            runtime.session_factory,
            runtime.session_id,
            ContextSearchRequest(query=query, cursor=cursor, limit=limit),
        )
    except (CodedHTTPException, ValidationError) as exc:
        return json.dumps(
            {
                "ok": False,
                "error": exc.code
                if isinstance(exc, CodedHTTPException)
                else "REQUEST_VALIDATION_FAILED",
            }
        )
    return await format_output(lambda budget: _bounded(result.model_dump(), budget))


@tool
@budgeted(_rejection)
async def read_context(
    source_id: str,
    version: str | None = None,
    cursor: str | None = None,
    max_chars: int = 1600,
    quote: str | None = None,
    offset: int | None = None,
) -> str:
    """限长读取当前会话/段的原文。source_id 来自摘要 source_ids 或 search_context。

    支持 message:/output: 身份，以及挂载范围内的 record:/library: 身份；传入 version
    校验来源未变。返回原文、定位、remaining 和 next_cursor；继续必须原样传回游标。
    quote 可定位最多80字的逐字命中。工具 JSON 片段不是业务回执，摘要不是原文或授权。
    失效/旧记录缺正文须如实反馈。不能传文件路径、SQL、会话 id 或扩大资料范围。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps({"ok": False, "error": "AGENT_CONTEXT_UNBOUND"})
    try:
        result = await read_source(
            runtime.session_factory,
            runtime.session_id,
            ContextReadRequest(
                source_id=source_id,
                version=version,
                cursor=cursor,
                max_chars=max_chars,
                quote=quote,
                offset=offset,
            ),
        )
    except (CodedHTTPException, ValidationError) as exc:
        return json.dumps(
            {
                "ok": False,
                "error": exc.code
                if isinstance(exc, CodedHTTPException)
                else "REQUEST_VALIDATION_FAILED",
            }
        )
    return await format_output(lambda budget: _bounded(result.model_dump(), budget))
