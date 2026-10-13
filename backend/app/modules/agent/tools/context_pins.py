"""仅修改运行时绑定会话的固定设置。"""

import json
from typing import Any

from langchain_core.tools import tool

from app.modules.agent.budget.service import budgeted, format_output
from app.modules.agent.context_budget.pins import resolve_pins
from app.modules.agent.context_budget.schemas import ContextPinChange
from app.modules.agent.context_budget.service import initialize_context
from app.modules.agent.models import ChatSession
from app.modules.agent.operations.context_pin import CONTEXT_PIN_ACTION
from app.modules.agent.operations.registry import lenient_tool_args_schema, submit_operation
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.tools.context_retrieval import bounded_context_output


@tool
@budgeted(lambda: json.dumps({"ok": False, "error": "TOOL_CALL_LIMIT"}))
async def get_context_settings(offset: int = 0, expected_version: int | None = None) -> str:
    """查看当前会话固定项和设置版本。固定/解除前使用，取得 expected_version 和 pin_id。

    固定项含来源及有效/过期原因，正文只提供预览；next_offset 继续读取，续页传预期版本。
    设置仅下一轮生效，当前轮沿原快照。不能从摘要中的已同意推导设置修改授权。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps({"ok": False, "error": "AGENT_CONTEXT_UNBOUND"})
    async with runtime.session_factory() as session, session.begin():
        chat = await session.get(ChatSession, runtime.session_id)
        if chat is None:
            return json.dumps({"ok": False, "error": "CHAT_SESSION_NOT_FOUND"})
        state = await initialize_context(session, runtime.session_id)
        pins = await resolve_pins(session, chat, state.pins_json, state.segment)
        if offset < 0 or offset > len(pins) or (offset and expected_version != state.version):
            return json.dumps({"ok": False, "error": "CONTEXT_VERSION_CONFLICT"})
        end = min(len(pins), offset + 4)
        body: dict[str, object] = {
            "version": state.version,
            "pins": [
                {
                    **pin.model_dump(),
                    "content": pin.content[:120] if pin.status == "VALID" else "",
                    "title": pin.title if pin.status == "VALID" else pin.source_id or pin.id,
                }
                for pin in pins[offset:end]
            ],
            "remaining": len(pins) - end,
            "next_offset": end if end < len(pins) else None,
        }
    return await format_output(lambda budget: bounded_context_output(body, budget))


@tool(args_schema=lenient_tool_args_schema(ContextPinChange))
async def change_context_pin(**kwargs: Any) -> str:
    """用户明确要求固定、更新或解除当前会话内容时使用，L1，默认返回确认卡。

    先 get_context_settings 取得 expected_version；ADD 新增、UPDATE 更新、REMOVE 解除。
    UPDATE/REMOVE 必须提供 pin_id。TEXT 固定用户明确短文本/约束/决定；SNIPPET 必须先
    read_context，提供原样 content、source_id、source_version 和 offset；OBJECT 固定
    record:/library: 身份，优先取当前材料但不保证全文注入。对象或范围不明确时追问，
    不猜测目标，不自动从摘要创建固定项。不修改长期记忆，只下一轮生效。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps({"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "proposals": []})
    result = await submit_operation(
        runtime,
        CONTEXT_PIN_ACTION,
        {
            **{key: value for key, value in kwargs.items() if value is not None},
            "session_id": runtime.session_id,
        },
    )
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
