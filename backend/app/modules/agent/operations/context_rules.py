"""上下文排除/重置/纳入复用单会话 L1 授权与提交校验。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.context_budget.rules import (
    RuleStateSnapshot,
    capture_rule_state,
    change_rules_core,
)
from app.modules.agent.context_budget.schemas import ContextRulePayload, ContextRulesOut
from app.modules.agent.operations.registry import OperationLevel, OperationSpec, register_operation
from app.modules.agent.runtime import current_agent_runtime
from app.modules.library.schemas import ProposalType
from app.shared.errors import CodedHTTPException


async def capture_state(session: AsyncSession, payload: ContextRulePayload) -> RuleStateSnapshot:
    runtime = current_agent_runtime()
    if runtime and runtime.session_id != payload.session_id:
        raise CodedHTTPException(
            code="CONTEXT_SOURCE_UNAVAILABLE", status_code=409, detail="不能修改其他会话的上下文"
        )
    return await capture_rule_state(session, payload.session_id, payload)


async def apply_rules(
    session: AsyncSession, payload: ContextRulePayload, _execution_id: str
) -> ContextRulesOut:
    return await change_rules_core(session, payload.session_id, payload)


register_operation(
    OperationSpec(
        action="change_context_rules",
        proposal_type=ProposalType.OP_CONTEXT_RULES,
        level=OperationLevel.L1,
        payload_schema=ContextRulePayload,
        result_schema=ContextRulesOut,
        applier=apply_rules,
        capture_state=capture_state,
        target_resolver=lambda payload: ("chat_session", payload.session_id),
        undo_reason="排除可恢复，重置后可明确选择旧轮重新纳入",
    )
)
