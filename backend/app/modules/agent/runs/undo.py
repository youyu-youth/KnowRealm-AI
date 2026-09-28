"""有限 Undo（通用 Agent 第二阶段工单 06，spec 决策 19/20）。

撤销＝新的受控补偿操作（undo_of 链、保留原执行历史）：补偿器由各动作注册项
声明（registry.OperationSpec.undoer），执行前重验「目标当前态 == 原操作执行后
的预期态」（不覆盖用户后续修改，OPERATION_UNDO_CONFLICT），恢复值来自原
operation 固化的执行前快照（before 值即恢复目标，快照一份三用的第三用）。

三条执行路径共用同一核心 :func:`execute_undo_core`：

- UI 显式动作（回执卡 / 操作历史 / 任务面板按钮）：POST operations/{id}/undo
  与 POST runs/{id}/undo——按钮点击即用户授权（trigger=USER_UNDO），直接建
  补偿 operation 同步执行；批次撤销按依赖逆序补偿、逐项结果如实呈现（单项
  补偿失败不谎报整体成功）；
- Agent undo 工具（undo_operation 薄工具）：走三档授权——分流按**原操作
  level**（撤销的授权强度与正向动作对称），默认档落 OP_UNDO 提案等确认、
  自动档直执行回执；
- OP_UNDO 提案确认路径：apply_undo_proposal 在确认事务内执行核心。

取消不冒充撤销（取消只停止后续、不补偿已完成，spec 决策 19）；记录软删、
课程软删与课程级联删除不提供 Undo（注册项 undo_reason 明确告知原因）。
"""

import json
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.agent.auth_mode import effective_session_auth_mode
from app.modules.agent.operations.registry import (
    OperationLevel,
    UndoOperationResult,
    direct_authorization,
    get_operation,
    should_execute_directly,
)
from app.modules.agent.runs.models import AgentOperation, AgentRun
from app.modules.agent.runs.schemas import (
    RUN_TERMINAL_STATUSES,
    OperationAuthorization,
    OperationStatus,
    RunUndoItemOut,
    RunUndoResultOut,
    UndoOperationPayload,
)
from app.modules.agent.runs.service import (
    list_run_operations,
    operation_out,
    order_run_operations,
)
from app.modules.agent.runtime import (
    MAX_OPERATION_PROPOSALS_PER_TURN,
    AgentRuntimeContext,
)
from app.modules.library.models import AgentProposal
from app.modules.library.proposals import (
    ProposalService,
    register_applier,
    register_payload_schema,
)
from app.modules.library.schemas import ProposalCreateRequest, ProposalType
from app.shared.errors import CodedHTTPException


def _not_undoable(action: str) -> CodedHTTPException:
    spec = get_operation(action)
    reason = spec.undo_reason if spec is not None and spec.undo_reason else "该操作不提供撤销"
    return CodedHTTPException(
        code="OPERATION_NOT_UNDOABLE",
        status_code=409,
        detail=reason,
    )


async def _require_undoable_operation(session: AsyncSession, operation_id: str) -> AgentOperation:
    """撤销前置校验（三条路径共用）：存在、终态 SUCCEEDED、未被撤销、可撤销。"""
    operation = await session.get(AgentOperation, operation_id)
    if operation is None:
        raise CodedHTTPException(
            code="AGENT_OPERATION_NOT_FOUND", status_code=404, detail="操作不存在"
        )
    if operation.status != OperationStatus.SUCCEEDED.value:
        raise CodedHTTPException(
            code="OPERATION_NOT_UNDOABLE",
            status_code=409,
            detail="仅已成功的操作可以撤销",
        )
    if operation.undone_by is not None:
        raise CodedHTTPException(
            code="OPERATION_ALREADY_UNDONE",
            status_code=409,
            detail="该操作已被撤销",
        )
    spec = get_operation(operation.action)
    if spec is None or spec.undoer is None:
        raise _not_undoable(operation.action)
    return operation


def _user_undo_authorization() -> OperationAuthorization:
    """UI 显式撤销的授权依据：按钮点击即用户授权（不经提案档位）。"""
    return OperationAuthorization(trigger="USER_UNDO")


async def execute_undo_core(
    session: AsyncSession,
    original: AgentOperation,
    *,
    authorization: OperationAuthorization,
) -> AgentOperation:
    """撤销执行核心（调用方事务内、不得自行 begin）：补偿器＋补偿行＋原行标记。

    调用方负责前置校验（_require_undoable_operation）。本函数：

    1. 固化 undo 快照＝补偿执行前的目标当前态（补偿操作行的 snapshot_json，
       供审计与再撤销——撤销补偿即恢复到撤销前）；
    2. 执行补偿器（undoer 内先撤销前重验：目标已偏离原操作执行后的预期态 →
       OPERATION_UNDO_CONFLICT，整个事务回滚＝未发生）；
    3. 写补偿 operation 行（undo_of 指向原操作；run_id / payload / target 沿
       原行——补偿行挂同一 run，操作历史 run 展开可见完整故事）；
    4. 原操作标记 undone_by（历史保留，spec 决策 19）。
    """
    spec = get_operation(original.action)
    # 前置校验已由调用方完成，此处仅窄化（pyright 终态收窄）。
    assert spec is not None and spec.undoer is not None
    undo_snapshot_json: str | None = None
    if spec.capture_state is not None:
        payload = spec.payload_schema.model_validate(json.loads(original.payload_json))
        undo_snapshot_json = (await spec.capture_state(session, payload)).model_dump_json()
    result = UndoOperationResult.model_validate(await spec.undoer(session, original))
    now = utcnow()
    compensation = AgentOperation(
        id=str(uuid4()),
        run_id=original.run_id,
        proposal_id=None,
        action=original.action,
        level=original.level,
        target_type=original.target_type,
        target_id=original.target_id,
        payload_json=original.payload_json,
        snapshot_json=undo_snapshot_json,
        authorization_json=authorization.model_dump_json(),
        status=OperationStatus.SUCCEEDED.value,
        attempts=1,
        result_json=result.model_dump_json(),
        undo_of=original.id,
        created_at=now,
        updated_at=now,
        finished_at=now,
    )
    session.add(compensation)
    await session.flush()
    original.undone_by = compensation.id
    original.updated_at = now
    return compensation


class UndoService:
    """撤销服务（工单 06）：单步撤销与 run 级批次撤销（UI 显式动作）。"""

    @staticmethod
    async def undo_operation(session: AsyncSession, operation_id: str) -> dict[str, Any]:
        """单步撤销（POST operations/{id}/undo）：UI 显式动作即用户授权，
        直接建补偿 operation 同步执行。"""
        async with session.begin():
            original = await _require_undoable_operation(session, operation_id)
            compensation = await execute_undo_core(
                session, original, authorization=_user_undo_authorization()
            )
        return operation_out(compensation)

    @staticmethod
    async def undo_run(session: AsyncSession, run_id: str) -> RunUndoResultOut:
        """run 级批次 Undo（POST runs/{id}/undo）：按依赖逆序补偿全部可撤销
        成功项，逐项独立小事务（单项补偿失败不谎报整体成功、不阻断其余项），
        结果如实呈现。终态守卫：任务尚未结束（仍在推进 / 等待）不可整批撤销。

        失败留痕（工单 06 review P2 修复）：补偿失败整体回滚＝业务未发生，
        但失败结果不能只活在 HTTP 响应里——独立小事务落 FAILED 补偿行
        （undo_of 挂原行、error_code 记失败原因），刷新后 run 展开仍可见；
        原行保持 SUCCEEDED 且无 undone_by，可再次发起撤销。
        """
        async with session:
            run = await session.get(AgentRun, run_id)
            if run is None:
                raise CodedHTTPException(
                    code="AGENT_RUN_NOT_FOUND", status_code=404, detail="任务不存在"
                )
            if run.status not in {status.value for status in RUN_TERMINAL_STATUSES}:
                raise CodedHTTPException(
                    code="AGENT_RUN_NOT_FINISHED",
                    status_code=409,
                    detail="任务尚未结束，不能整批撤销",
                )
            operations = order_run_operations(
                await list_run_operations(session, run_id),
                run.plan_json,
                run.plan_version,
            )
        items: list[RunUndoItemOut] = []
        undone = failed = 0
        # 依赖逆序＝计划顺序倒转（计划结构保证依赖项索引早于自身）：后执行的
        # 先补偿；已撤销 / 非成功项不参与（失败与跳过项本就未发生业务写）。
        for operation in reversed(operations):
            if operation.status != OperationStatus.SUCCEEDED.value:
                continue
            spec = get_operation(operation.action)
            if spec is None or spec.undoer is None:
                # 不可撤销的成功项如实呈现为跳过（原因在注册项声明）。
                items.append(
                    RunUndoItemOut(
                        operation_id=operation.id,
                        action=operation.action,
                        status="SKIPPED",
                    )
                )
                continue
            if operation.undone_by is not None:
                continue
            item = RunUndoItemOut(
                operation_id=operation.id, action=operation.action, status="SUCCEEDED"
            )
            try:
                async with session.begin():
                    original = await _require_undoable_operation(session, operation.id)
                    compensation = await execute_undo_core(
                        session, original, authorization=_user_undo_authorization()
                    )
                item = item.model_copy(update={"compensation_id": compensation.id})
                undone += 1
            except CodedHTTPException as exc:
                item = item.model_copy(update={"status": "FAILED", "error_code": exc.code})
                failed += 1
                now = utcnow()
                async with session.begin():
                    session.add(
                        AgentOperation(
                            id=str(uuid4()),
                            run_id=operation.run_id,
                            proposal_id=None,
                            action=operation.action,
                            level=operation.level,
                            target_type=operation.target_type,
                            target_id=operation.target_id,
                            payload_json=operation.payload_json,
                            snapshot_json=None,
                            authorization_json=_user_undo_authorization().model_dump_json(),
                            status=OperationStatus.FAILED.value,
                            attempts=1,
                            error_code=exc.code,
                            undo_of=operation.id,
                            created_at=now,
                            updated_at=now,
                            finished_at=now,
                        )
                    )
            items.append(item)
        return RunUndoResultOut(
            run_id=run_id,
            undone_count=undone,
            failed_count=failed,
            items=items,
        )


async def submit_undo(runtime: AgentRuntimeContext, operation_id: str) -> dict[str, Any]:
    """撤销工具公共提交入口（走三档授权，spec 决策 19）。

    分流按**原操作的 level**（撤销的授权强度与正向动作对称：L1 的补偿在
    帮我批准档自动执行、L2 的补偿仍出确认卡）。返回工具 JSON 载荷：

    - 前置校验失败 → {ok: False, error, detail}（模型转述，如不可撤销原因）；
    - 直执行 → {ok, executed}（六键与正向直执行回执同形，回执卡复用）；
    - 落提案 → {ok, proposals: [{proposal_id, action, payload, status}]}。
    """
    if runtime.budget.operations_created >= MAX_OPERATION_PROPOSALS_PER_TURN:
        return {
            "ok": False,
            "error": "OPERATION_PROPOSAL_LIMIT",
            "detail": f"每轮最多执行 {MAX_OPERATION_PROPOSALS_PER_TURN} 条操作",
            "proposals": [],
        }
    async with runtime.session_factory() as session:
        try:
            async with session.begin():
                original = await _require_undoable_operation(session, operation_id)
                # 提交时固化 undo 快照（默认档确认卡预览＝目标当前态；
                # 确认时的撤销前重验由补偿器执法）。
                undo_snapshot_json = await _capture_undo_snapshot(session, original)
        except CodedHTTPException as exc:
            return {
                "ok": False,
                "error": exc.code,
                "detail": exc.detail,
                "proposals": [],
            }
    runtime.budget.operations_created += 1
    effective_mode = effective_session_auth_mode(runtime.session_id, runtime.auth_mode)
    if should_execute_directly(effective_mode, OperationLevel(original.level)):
        authorization = direct_authorization(runtime, effective_mode)
        compensation: AgentOperation
        async with runtime.session_factory() as session:
            try:
                async with session.begin():
                    original = await _require_undoable_operation(session, operation_id)
                    compensation = await execute_undo_core(
                        session, original, authorization=authorization
                    )
            except CodedHTTPException as exc:
                return {"ok": False, "error": exc.code, "executed": None}
        return {
            "ok": True,
            "executed": {
                "operation_id": compensation.id,
                "action": compensation.action,
                "level": compensation.level,
                "auth_mode": effective_mode.value,
                "payload": {"operation_id": operation_id},
                "result": {"undone_operation_id": operation_id},
            },
        }
    async with runtime.session_factory() as session, session.begin():
        proposal = await ProposalService.create_core(
            session,
            ProposalCreateRequest(
                proposal_type=ProposalType.OP_UNDO,
                payload={"operation_id": operation_id},
                session_id=runtime.session_id,
                message_id=runtime.message_id,
                target_type=original.target_type,
                target_id=original.target_id,
            ),
            snapshot_json=undo_snapshot_json,
        )
    return {
        "ok": True,
        "proposals": [
            {
                "proposal_id": proposal.id,
                "action": "undo_operation",
                "payload": {"operation_id": operation_id},
                "status": proposal.status.value,
            }
        ],
    }


async def _capture_undo_snapshot(session: AsyncSession, original: AgentOperation) -> str | None:
    """读原操作目标的当前态（默认档确认卡预览）；无快照读取器的动作返回 None。"""
    spec = get_operation(original.action)
    if spec is None or spec.capture_state is None:
        return None
    payload = spec.payload_schema.model_validate(json.loads(original.payload_json))
    return (await spec.capture_state(session, payload)).model_dump_json()


async def apply_undo_proposal(session: AsyncSession, proposal: AgentProposal) -> dict[str, Any]:
    """OP_UNDO 应用器（提案框架契约：调用方确认事务内、不得自行 begin）。

    确认即用户授权撤销：重读原操作做全套前置校验（提交后目标被撤销过 /
    已变更的情况在此拦截），执行撤销核心，补偿结果投影回提案 result_json。
    """
    try:
        payload = UndoOperationPayload.model_validate(json.loads(proposal.payload_json))
    except ValueError as exc:
        raise CodedHTTPException(
            code="PROPOSAL_PAYLOAD_INVALID",
            status_code=422,
            detail="提案载荷不符合该类型的结构要求",
        ) from exc
    original = await _require_undoable_operation(session, payload.operation_id)
    compensation = await execute_undo_core(
        session,
        original,
        authorization=OperationAuthorization(
            session_id=proposal.session_id, message_id=proposal.message_id
        ),
    )
    return {
        "operation_id": compensation.id,
        "undone_operation_id": original.id,
        "action": original.action,
    }


register_payload_schema(ProposalType.OP_UNDO, UndoOperationPayload)
register_applier(ProposalType.OP_UNDO, apply_undo_proposal)
