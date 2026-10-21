"""大临时输出的受控快照；模型投影与业务回执、checkpoint 内容分开。"""

import json
from collections.abc import Awaitable, Callable
from typing import Any, cast
from uuid import uuid4

from langchain.agents.middleware.types import (  # pyright: ignore[reportMissingTypeStubs]
    AgentMiddleware,
    ToolCallRequest,
)
from langchain_core.messages import AnyMessage, ToolMessage
from sqlalchemy import select

from app.modules.agent.context_budget.models import ChatContextOutput
from app.modules.agent.context_budget.retrieval import digest
from app.modules.agent.middleware.cancel_guard import TurnCancelledError
from app.modules.agent.runtime import AgentRuntimeContext, current_agent_runtime
from app.modules.agent.turns.effects import current_tool_call_identity, effect_args_fingerprint
from app.shared.errors import CodedHTTPException

OUTPUT_INLINE_CHARS = 4000
# 原文由领域读取重建；操作/提案回执保留完整 JSON，不卸载业务结果。
REBUILDABLE_TOOLS = frozenset(
    {
        "search_library",
        "search_courses",
        "list_course_records",
        "list_library_items",
        "list_shared_refs",
        "search_transcript",
        "search_context",
        "read_context",
    }
)


async def save_web_output(query: str, content: str, inline: str) -> str:
    """网页摘要裁剪前保存不可重建正文，恢复复用同一逻辑调用的原结果。"""
    runtime, identity = current_agent_runtime(), current_tool_call_identity()
    if (
        runtime is None
        or runtime.turn_id is None
        or identity is None
        or len(content) <= OUTPUT_INLINE_CHARS
    ):
        return inline
    async with runtime.session_factory() as session, session.begin():
        if not await runtime.turn_write_allowed(session):
            raise TurnCancelledError
        row = await session.scalar(
            select(ChatContextOutput).where(
                ChatContextOutput.turn_id == runtime.turn_id,
                ChatContextOutput.namespace == identity.namespace,
                ChatContextOutput.logical_call_id == identity.logical_call_id,
            )
        )
        if row:
            return row.inline_content or inline
        source_id = str(uuid4())
        version = digest(content)
        body: dict[str, object] = json.loads(inline)
        body.update(
            {
                "source_id": f"output:{source_id}",
                "version": version,
                "total_chars": len(content),
                "truncated": True,
                "message": "完整搜索结果已保存，可用 read_context 分段取回。",
            }
        )
        inline = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        session.add(
            ChatContextOutput(
                id=source_id,
                turn_id=runtime.turn_id,
                namespace=identity.namespace,
                logical_call_id=identity.logical_call_id,
                tool_name="web_search",
                args_fingerprint=effect_args_fingerprint({"query": query}),
                content=content,
                content_hash=version,
                inline_content=inline,
            )
        )
    return inline


class ContextOutputMiddleware(AgentMiddleware[Any, Any, Any]):  # pyright: ignore[reportMissingTypeStubs]
    async def awrap_tool_call(  # pyright: ignore[reportMissingTypeStubs]
        self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], Awaitable[Any]]
    ) -> Any:
        runtime, identity = current_agent_runtime(), current_tool_call_identity()
        if runtime is None or runtime.turn_id is None or identity is None:
            return await handler(request)
        call = request.tool_call
        fingerprint = effect_args_fingerprint(call["args"])
        async with runtime.session_factory() as session:
            cached = await session.scalar(
                select(ChatContextOutput).where(
                    ChatContextOutput.turn_id == runtime.turn_id,
                    ChatContextOutput.namespace == identity.namespace,
                    ChatContextOutput.logical_call_id == identity.logical_call_id,
                )
            )
        if cached:
            if cached.tool_name != call["name"] or cached.args_fingerprint != fingerprint:
                raise CodedHTTPException(
                    code="TOOL_CALL_IDENTITY_CONFLICT",
                    status_code=409,
                    detail="原工具输出与调用身份不匹配",
                )
            return ToolMessage(
                content=cached.inline_content or cached.content,
                tool_call_id=call["id"],
                name=call["name"],
            )
        result = await handler(request)
        if isinstance(result, ToolMessage) and result.status == "error":
            return result
        content = result.content if isinstance(result, ToolMessage) else result
        if not isinstance(content, str) or len(content) <= OUTPUT_INLINE_CHARS:
            return result
        try:
            payload = json.loads(content)
        except ValueError:
            payload = None
        if (
            call["name"] in REBUILDABLE_TOOLS
            or (isinstance(payload, dict) and cast(dict[str, object], payload).get("ok") is False)
            or (
                isinstance(payload, dict)
                and any(
                    key in payload
                    for key in ("executed", "operation_id", "proposal_id", "proposals", "receipt")
                )
            )
        ):
            return result
        async with runtime.session_factory() as session, session.begin():
            if not await runtime.turn_write_allowed(session):
                raise TurnCancelledError
            existing = await session.scalar(
                select(ChatContextOutput).where(
                    ChatContextOutput.turn_id == runtime.turn_id,
                    ChatContextOutput.namespace == identity.namespace,
                    ChatContextOutput.logical_call_id == identity.logical_call_id,
                )
            )
            if existing is None:
                session.add(
                    ChatContextOutput(
                        turn_id=runtime.turn_id,
                        namespace=identity.namespace,
                        logical_call_id=identity.logical_call_id,
                        tool_name=call["name"],
                        args_fingerprint=fingerprint,
                        content=content,
                        content_hash=digest(content),
                    )
                )
        return result


def output_projection(row: ChatContextOutput) -> dict[str, object]:
    return {
        "ok": True,
        "source_id": f"output:{row.id}",
        "version": row.content_hash,
        "total_chars": len(row.content),
        "preview": row.content[:240],
        "truncated": True,
        "message": "大输出已保存，使用 read_context(source_id, version) 分段取回。",
    }


async def project_outputs(
    runtime: AgentRuntimeContext, messages: list[AnyMessage]
) -> list[AnyMessage]:
    async with runtime.session_factory() as session:
        # 工具调用 id 只在原轮次内唯一；历史工具消息保留原文/既有受控指针。
        rows = (
            await session.scalars(
                select(ChatContextOutput).where(ChatContextOutput.turn_id == runtime.turn_id)
            )
        ).all()
    outputs = {row.logical_call_id: row for row in rows}
    result: list[AnyMessage] = []
    for message in messages:
        row = outputs.get(message.tool_call_id) if isinstance(message, ToolMessage) else None
        if row and message.content == row.content:
            content = json.dumps(output_projection(row), ensure_ascii=False)
            result.append(message.model_copy(update={"content": content}))
        else:
            result.append(message)
    return result
