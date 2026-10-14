"""设置操作绑定当前运行会话；旧历史枚举仅提供身份，不泄露旧段正文。"""

import json
from typing import Any

from langchain_core.tools import tool

from app.modules.agent.budget.service import budgeted, format_output
from app.modules.agent.context_budget.rules import history_turns
from app.modules.agent.context_budget.schemas import ContextRuleChange
from app.modules.agent.operations import (
    context_rules as _registration,  # noqa: F401  # pyright: ignore[reportUnusedImport]
)
from app.modules.agent.operations.registry import lenient_tool_args_schema, submit_operation
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.tools.context_retrieval import bounded_context_output
from app.shared.errors import CodedHTTPException


@tool
@budgeted(lambda: json.dumps({"ok": False, "error": "TOOL_CALL_LIMIT"}))
async def list_context_history(offset: int = 0, expected_version: int | None = None) -> str:
    """列出当前会话轮次的身份、段和状态，供明确选择排除或纳入范围，不返回历史正文。

    用户没说明纳入哪些旧轮时先追问，不能默认全部恢复。next_offset 续页须传设置版本。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps({"ok": False, "error": "AGENT_CONTEXT_UNBOUND"})
    if offset < 0:
        return json.dumps({"ok": False, "error": "CONTEXT_CURSOR_INVALID"})
    try:
        result = await history_turns(
            runtime.session_factory, runtime.session_id, offset, expected_version
        )
    except CodedHTTPException as exc:
        return json.dumps({"ok": False, "error": exc.code})
    body = result.model_dump(mode="json")
    for row in body["turns"]:
        row.pop("title")
    return await format_output(lambda budget: bounded_context_output(body, budget))


@tool(args_schema=lenient_tool_args_schema(ContextRuleChange))
async def change_context_rules(**kwargs: Any) -> str:
    """用户明确要求排除/恢复、重置或纳入旧历史时使用，单会话可恢复 L1，默认确认卡。

    先 get_context_settings 取得 expected_version。EXCLUDE_TURN/RESTORE_TURN 传明确 turn_ids，
    EXCLUDE_SOURCE 传先前 read_context 获得的 record:/library: source_id 和 source_version；
    RESTORE_SOURCE 传已排除的 source_id。RESET 不传范围，开启新段但保留固定/排除/资料范围/记忆，
    不取消后台任务。INCLUDE_HISTORY 必须明确选择本会话已完成旧轮的 turn_ids（身份可用
    list_context_history 查看），未指定范围必须追问，不得默认全部。排除优先于固定与纳入，
    不保证消除其他消息内无来源标记的转述。仅下一轮生效，不改变授权或删除原数据。
    """
    runtime = current_agent_runtime()
    if runtime is None:
        return json.dumps({"ok": False, "error": "AGENT_CONTEXT_UNBOUND", "proposals": []})
    result = await submit_operation(
        runtime,
        "change_context_rules",
        {
            **{key: value for key, value in kwargs.items() if value is not None},
            "session_id": runtime.session_id,
        },
    )
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
