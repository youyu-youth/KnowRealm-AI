"""「记住」记忆提案工具（工单 06，ADR-0025）：模型受控写路径的唯一记忆入口。

用户在对话中明确要求记住某个学习偏好时，模型调用本工具创建 EXPLICIT MEMORY
提案（创建不改任何事实）；提案经前端就地确认卡 HITL 确认后，由 learner 域
应用器写入 learner_preferences。普通聊天零静默提取：docstring 明确约束只在
用户说「记住…」时调用。运行期上下文（session_factory / session_id）由统一
Agent 运行时上下文承载（工单 01 起，见 agent/runtime.py），AgentConfig 变体
保持常量（先例 search_library）。
"""

import json

from langchain_core.tools import tool

from app.modules.agent.runtime import CHAT_TURN_CANCELLED, current_agent_runtime
from app.modules.agent.turns.effects import (
    EffectExecutionError,
    complete_effect,
    prepare_effect,
)
from app.modules.library.proposals import ProposalService
from app.modules.library.schemas import ProposalCreateRequest, ProposalType

# 单次提案条数上限（对齐 MemoryProposalPayload 判别校验，超限拒绝而非截断：
# 截断会让确认卡出现半句偏好，用户确认的是被改写过的内容）。
PROPOSE_MEMORY_ITEMS_LIMIT = 5
# 单条偏好限长（对齐 MemoryProposalPayload）。
PROPOSE_MEMORY_ITEM_MAX_CHARS = 100

# 工具名（langchain @tool 注册名 = 函数名）：流式分发按名识别本工具的返回。
PROPOSE_MEMORY_TOOL_NAME = "propose_memory"


@tool
async def propose_memory(items: list[str]) -> str:
    """当用户明确要求记住某个学习偏好时使用（如「记住我喜欢先看例题」）。

    只在用户明确说「记住…」并给出了偏好内容时调用；禁止主动总结、推断或
    静默提取聊天内容为记忆。创建的是待用户确认的记忆提案，用户确认后才会
    生效；调用成功后告知用户已生成记忆提案、等待其确认。
    """
    context = current_agent_runtime()
    if context is None:
        return json.dumps({"ok": False, "error": "MEMORY_CONTEXT_UNBOUND"}, ensure_ascii=False)
    cleaned = [item.strip() for item in items if item.strip()]
    if not cleaned:
        return json.dumps(
            {"ok": False, "error": "MEMORY_ITEMS_EMPTY", "detail": "没有可记忆的偏好内容"},
            ensure_ascii=False,
        )
    if len(cleaned) > PROPOSE_MEMORY_ITEMS_LIMIT or any(
        len(item) > PROPOSE_MEMORY_ITEM_MAX_CHARS for item in cleaned
    ):
        return json.dumps(
            {
                "ok": False,
                "error": "MEMORY_ITEMS_TOO_LONG",
                "detail": (
                    f"一次最多记忆 {PROPOSE_MEMORY_ITEMS_LIMIT} 条、"
                    f"每条不超过 {PROPOSE_MEMORY_ITEM_MAX_CHARS} 字，请拆分或概括后重试"
                ),
            },
            ensure_ascii=False,
        )
    # 幂等前置（票 02，规格 §9）：轮次上下文下按逻辑调用身份恢复——已成功
    # 项复用原提案 ID，不重复创建；指纹冲突拒绝执行。
    try:
        preparation = await prepare_effect(context, PROPOSE_MEMORY_TOOL_NAME, cleaned)
    except EffectExecutionError as exc:
        return json.dumps(
            {"ok": False, "error": exc.code, "detail": exc.detail}, ensure_ascii=False
        )
    if preparation is not None and preparation.replay is not None:
        return json.dumps(preparation.replay, ensure_ascii=False, separators=(",", ":"))
    payload: dict[str, object]
    async with context.session_factory() as session, session.begin():
        # 业务提交处最终校验（ChatTurn 规格 §2/§14）：持久取消先落库则同事务
        # 拒绝创建（取消后禁止新增副作用）；create_core 先例＝调用方拥有事务。
        if not await context.turn_write_allowed(session):
            return json.dumps({"ok": False, "error": CHAT_TURN_CANCELLED}, ensure_ascii=False)
        proposal = await ProposalService.create_core(
            session,
            ProposalCreateRequest(
                proposal_type=ProposalType.MEMORY,
                payload={"kind": "EXPLICIT", "items": cleaned},
                session_id=context.session_id,
            ),
        )
        payload = {
            "ok": True,
            "proposal_id": proposal.id,
            "items": cleaned,
            "status": "PENDING",
        }
        # 效果行与业务写入同事务收口（票 02）：恢复命中即复用原提案 ID。
        if preparation is not None:
            await complete_effect(
                session, context, PROPOSE_MEMORY_TOOL_NAME, cleaned, result=payload
            )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
