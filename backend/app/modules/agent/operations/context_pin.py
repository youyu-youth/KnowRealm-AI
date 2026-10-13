"""固定设置复用 L1 提案、直执行和持久回执。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.context_budget.pins import (
    PinStateSnapshot,
    capture_pin_state,
    change_pins_core,
)
from app.modules.agent.context_budget.schemas import ContextPinPayload, ContextPinsOut
from app.modules.agent.operations.registry import OperationLevel, OperationSpec, register_operation
from app.modules.agent.runtime import current_agent_runtime
from app.modules.library.schemas import ProposalType
from app.shared.errors import CodedHTTPException

CONTEXT_PIN_ACTION = "change_context_pin"


async def capture_state(session: AsyncSession, payload: ContextPinPayload) -> PinStateSnapshot:
    runtime = current_agent_runtime()
    if runtime and runtime.session_id != payload.session_id:
        raise CodedHTTPException(
            code="CONTEXT_SOURCE_UNAVAILABLE", status_code=409, detail="不能修改其他会话的固定设置"
        )
    return await capture_pin_state(session, payload.session_id, payload)


async def apply_pin(
    session: AsyncSession, payload: ContextPinPayload, _execution_id: str
) -> ContextPinsOut:
    return await change_pins_core(session, payload.session_id, payload)


register_operation(
    OperationSpec(
        action=CONTEXT_PIN_ACTION,
        proposal_type=ProposalType.OP_CONTEXT_PIN,
        level=OperationLevel.L1,
        payload_schema=ContextPinPayload,
        result_schema=ContextPinsOut,
        applier=apply_pin,
        capture_state=capture_state,
        target_resolver=lambda payload: ("chat_session", payload.session_id),
        undo_reason="固定设置可通过解除或重新固定恢复",
    )
)
