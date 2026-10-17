"""练习准备受控入口；业务要求只能由人工确认的提案保存。"""

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.auth_mode import effective_session_auth_mode
from app.modules.agent.operations.registry import OperationLevel, OperationSpec, register_operation
from app.modules.agent.runs.models import AgentOperation, AgentRun
from app.modules.agent.runs.schemas import AuthMode, OperationAuthorization
from app.modules.agent.turns.models import ChatTurn
from app.modules.learning_plan import practice, practice_round
from app.modules.learning_plan.practice_schemas import (
    PracticePreparationOut,
    PracticePrepareRequest,
    PracticeRequirementsOut,
    PracticeRequirementsUpdate,
    PracticeRoundOut,
    PracticeRoundStart,
)
from app.modules.library.models import AgentProposal
from app.modules.library.schemas import ProposalType


class PracticeRequirementsPayload(PracticeRequirementsUpdate):
    item_id: str = Field(description="get_plan 查询的目标计划项 id")


class PracticePreparePayload(PracticePrepareRequest):
    item_id: str = Field(description="已保存练习要求的计划项 id")


class PracticeCancelPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str = Field(description="目标计划项 id")
    preparation_id: str = Field(description="要取消的准备请求 id")


class PracticeRoundStartPayload(PracticeRoundStart):
    item_id: str = Field(description="已完成题集准备的计划项 id")


async def confirm(
    session: AsyncSession, payload: PracticeRequirementsPayload, execution_id: str
) -> PracticeRequirementsOut:
    proposal = await session.get(AgentProposal, execution_id)
    # 执行档位不是用户的业务确认；即使通过其他入口直执行也不得保存要求。
    if proposal is None or proposal.proposal_type != ProposalType.OP_PRACTICE_REQUIREMENTS:
        raise practice.conflict("PRACTICE_CONFIRMATION_REQUIRED")
    core = PracticeRequirementsUpdate.model_validate(payload.model_dump(exclude={"item_id"}))
    return await practice.confirm_requirements(session, payload.item_id, core)


async def prepare(
    session: AsyncSession, payload: PracticePreparePayload, _execution_id: str
) -> PracticePreparationOut:
    core = PracticePrepareRequest.model_validate(payload.model_dump(exclude={"item_id"}))
    return await practice.prepare(session, payload.item_id, core, authority="AGENT")


async def cancel(
    session: AsyncSession, payload: PracticeCancelPayload, _execution_id: str
) -> PracticePreparationOut:
    return await practice.cancel(session, payload.item_id, payload.preparation_id)


async def start_round_op(
    session: AsyncSession, payload: PracticeRoundStartPayload, _execution_id: str
) -> PracticeRoundOut:
    core = PracticeRoundStart.model_validate(payload.model_dump(exclude={"item_id"}))
    return await practice_round.start_round(session, payload.item_id, core)


class PracticeSnapshot(BaseModel):
    plan_content: str
    revision: int
    source_titles: dict[str, str]
    source_versions: dict[str, str]


async def capture(session: AsyncSession, payload: PracticeRequirementsPayload) -> PracticeSnapshot:
    from sqlalchemy import select

    from app.modules.record.models import Record

    item, _plan, goal = await practice.load_context(session, payload.item_id, writable=True)
    await practice.require_sources(
        session, goal.course_id, [str(id_) for id_ in payload.record_ids]
    )
    latest = await practice.latest_requirements(session, payload.item_id)
    rows = (
        await session.execute(
            select(Record.id, Record.title)
            .where(Record.id.in_([str(id_) for id_ in payload.record_ids]))
            .order_by(Record.id)
        )
    ).all()
    return PracticeSnapshot(
        plan_content=item.content,
        revision=latest.revision if latest else 0,
        source_titles={id_: title for id_, title in rows},
        source_versions=await practice.source_versions(
            session, [str(id_) for id_ in payload.record_ids]
        ),
    )


register_operation(
    OperationSpec(
        action="confirm_practice_requirements",
        proposal_type=ProposalType.OP_PRACTICE_REQUIREMENTS,
        level=OperationLevel.L1,
        payload_schema=PracticeRequirementsPayload,
        result_schema=PracticeRequirementsOut,
        applier=confirm,
        capture_state=capture,
        target_resolver=lambda p: ("plan_item", p.item_id),
        undo_reason="已确认要求保留历史修订，可重新确认修改",
    )
)
register_operation(
    OperationSpec(
        action="prepare_plan_practice",
        proposal_type=ProposalType.OP_PRACTICE_PREPARE,
        level=OperationLevel.L1,
        payload_schema=PracticePreparePayload,
        result_schema=PracticePreparationOut,
        applier=prepare,
        target_resolver=lambda p: ("plan_item", p.item_id),
        undo_reason="匹配任务可通过取消入口停止",
    )
)
register_operation(
    OperationSpec(
        action="cancel_practice_preparation",
        proposal_type=ProposalType.OP_PRACTICE_CANCEL,
        level=OperationLevel.L1,
        payload_schema=PracticeCancelPayload,
        result_schema=PracticePreparationOut,
        applier=cancel,
        target_resolver=lambda p: ("plan_item", p.item_id),
        undo_reason="取消保留要求，可显式重试",
    )
)
register_operation(
    OperationSpec(
        action="start_plan_practice",
        proposal_type=ProposalType.OP_PRACTICE_ROUND_START,
        level=OperationLevel.L1,
        payload_schema=PracticeRoundStartPayload,
        result_schema=PracticeRoundOut,
        applier=start_round_op,
        target_resolver=lambda p: ("plan_item", p.item_id),
        undo_reason="轮次由用户在页面作答，开始不产生需撤销的写入",
    )
)


async def validate_preparation_authority(session: AsyncSession, job_id: str) -> None:
    operation = await session.scalar(
        select(AgentOperation).where(
            AgentOperation.action == "prepare_plan_practice",
            AgentOperation.status == "SUCCEEDED",
            func.json_extract(AgentOperation.result_json, "$.job_id") == job_id,
        )
    )
    if operation is None or operation.authorization_json is None:
        raise practice.conflict("OPERATION_APPROVAL_REQUIRED")
    auth = OperationAuthorization.model_validate_json(operation.authorization_json)
    if auth.trigger == "AUTO_EXECUTED" and (
        auth.session_id is None
        or effective_session_auth_mode(auth.session_id, auth.auth_mode) == AuthMode.REQUEST_APPROVAL
    ):
        raise practice.conflict("OPERATION_APPROVAL_REQUIRED")
    if operation.run_id:
        run = await session.get(AgentRun, operation.run_id)
        if run is None or run.cancel_requested or run.status == "CANCELLED":
            raise practice.conflict("PRACTICE_EXECUTION_CANCELLED")
    if auth.message_id:
        turn = await session.scalar(
            select(ChatTurn).where(ChatTurn.user_message_id == auth.message_id)
        )
        if turn and (turn.cancel_requested or turn.status == "CANCELLED"):
            raise practice.conflict("PRACTICE_EXECUTION_CANCELLED")


practice.register_preparation_authorizer(validate_preparation_authority)
