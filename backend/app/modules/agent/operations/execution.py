"""受控执行：入口差异留在内部 adapter，动作应用与成功记账共用一条流程。"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.agent.auth_mode import effective_session_auth_mode
from app.modules.agent.operations.registry import (
    OPERATION_TRANSIENT_ERROR,
    TRANSIENT_MAX_RETRIES,
    OperationSpec,
    direct_authorization,
    is_transient_exception,
    operation_payload_dict,
    parse_operation_payload,
    run_operation_applier,
    should_execute_directly,
)
from app.modules.agent.runs.bindings import operation_params, resolve_step_refs
from app.modules.agent.runs.models import AgentOperation, AgentRun
from app.modules.agent.runs.schemas import (
    OPERATION_DEPENDENCY_FAILED,
    AuthMode,
    BatchPlanOut,
    OperationAuthorization,
    OperationStatus,
    params_output_refs,
)
from app.modules.agent.runs.service import (
    record_confirmed_operation,
    record_direct_execution,
)
from app.modules.agent.runtime import CHAT_TURN_CANCELLED, AgentRuntimeContext
from app.modules.agent.turns.effects import EffectPreparation, complete_effect
from app.modules.library.models import AgentProposal
from app.shared.errors import CodedHTTPException


async def operation_snapshot_stale(
    session: AsyncSession,
    spec: OperationSpec[Any, Any],
    operation: AgentOperation,
    params: dict[str, Any],
) -> bool:
    """执行前快照重验（spec 决策 12，推进 worker 每步与手动重试共用的口径）：
    当前态与固化快照不一致即失效（缺失 / 坏值同样失效＝保守方向）。快照按
    字典比对（不依赖序列化字节一致）。"""
    if spec.capture_state is None:
        return False
    if operation.snapshot_json is None:
        return True
    try:
        stored: object = json.loads(operation.snapshot_json)
    except ValueError:
        return True
    current = (
        await spec.capture_state(session, spec.payload_schema.model_validate(params))
    ).model_dump(mode="json")
    return current != stored


class _Execution(Protocol):
    @property
    def execution_id(self) -> str: ...

    async def prepare(self, session: AsyncSession, spec: OperationSpec[Any, Any]) -> BaseModel: ...

    async def record(
        self, session: AsyncSession, spec: OperationSpec[Any, Any], result: BaseModel
    ) -> None: ...


async def _execute(
    session: AsyncSession, spec: OperationSpec[Any, Any], entry: _Execution
) -> BaseModel:
    payload = await entry.prepare(session, spec)
    result = await run_operation_applier(session, spec, payload, entry.execution_id)
    await entry.record(session, spec, result)
    return result


@dataclass
class _ConfirmedExecution:
    proposal: AgentProposal

    @property
    def execution_id(self) -> str:
        return self.proposal.id

    async def prepare(self, session: AsyncSession, spec: OperationSpec[Any, Any]) -> BaseModel:
        if spec.capture_state is not None:
            payload = spec.payload_schema.model_validate(
                operation_payload_dict(self.proposal.payload_json)
            )
            current = (await spec.capture_state(session, payload)).model_dump_json()
            if self.proposal.snapshot_json is None or self.proposal.snapshot_json != current:
                raise CodedHTTPException(
                    code="OPERATION_SNAPSHOT_STALE",
                    status_code=409,
                    detail="目标已发生变化，提案已失效，请重新预览确认",
                )
            return payload
        return parse_operation_payload(self.proposal.payload_json, spec.payload_schema)

    async def record(
        self, session: AsyncSession, spec: OperationSpec[Any, Any], result: BaseModel
    ) -> None:
        await record_confirmed_operation(
            session,
            proposal=self.proposal,
            action=spec.action,
            level=spec.level.value,
            result_dict=result.model_dump(mode="json"),
            snapshot_json=self.proposal.snapshot_json,
        )


async def execute_confirmed_operation(
    session: AsyncSession, spec: OperationSpec[Any, Any], proposal: AgentProposal
) -> dict[str, Any]:
    result = await _execute(session, spec, _ConfirmedExecution(proposal))
    return result.model_dump(mode="json")


def _run_operation_authorized(run: AgentRun, spec: OperationSpec[Any, Any]) -> bool:
    """显式批准计划保留批准依据；档位授权只允许取更严格的会话覆盖。"""
    if run.proposal_id is not None:
        return True
    mode = AuthMode(run.auth_mode)
    if run.session_id is not None:
        mode = effective_session_auth_mode(run.session_id, mode)
    return should_execute_directly(mode, spec.level)


def _record_existing(operation: AgentOperation, result: BaseModel, now: datetime) -> None:
    operation.status = OperationStatus.SUCCEEDED.value
    operation.result_json = json.dumps(
        result.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")
    )
    operation.error_code = None
    operation.updated_at = now
    operation.finished_at = now


@dataclass
class RunOperationBlocked(Exception):
    """执行前拒绝；由 Run 在原事务内落失败/跳过与等待投影。"""

    code: str


@dataclass
class _RunExecution:
    run: AgentRun
    operation: AgentOperation
    plan: BatchPlanOut
    now: datetime
    execution_id: str

    async def prepare(self, session: AsyncSession, spec: OperationSpec[Any, Any]) -> BaseModel:
        if not _run_operation_authorized(self.run, spec):
            raise RunOperationBlocked("OPERATION_APPROVAL_REQUIRED")
        operation = self.operation
        params = operation_params(operation)
        if params_output_refs(params):
            resolved = await resolve_step_refs(session, self.plan, params)
            if resolved is None:
                raise RunOperationBlocked(OPERATION_DEPENDENCY_FAILED)
            params = resolved
            operation.payload_json = json.dumps(params, ensure_ascii=False, separators=(",", ":"))
            if spec.capture_state is not None and operation.snapshot_json in (None, "{}"):
                operation.snapshot_json = (
                    await spec.capture_state(session, spec.payload_schema.model_validate(params))
                ).model_dump_json()
        if not params_output_refs(params) and await operation_snapshot_stale(
            session, spec, operation, params
        ):
            raise RunOperationBlocked("OPERATION_SNAPSHOT_STALE")
        return parse_operation_payload(operation.payload_json, spec.payload_schema)

    async def record(
        self, session: AsyncSession, spec: OperationSpec[Any, Any], result: BaseModel
    ) -> None:
        _record_existing(self.operation, result, self.now)


async def execute_run_operation(
    session: AsyncSession,
    spec: OperationSpec[Any, Any],
    run: AgentRun,
    operation: AgentOperation,
    plan: BatchPlanOut,
    now: datetime,
) -> BaseModel:
    return await _execute(session, spec, _RunExecution(run, operation, plan, now, str(uuid4())))


@dataclass
class _RetryExecution:
    operation: AgentOperation
    execution_id: str

    async def prepare(self, session: AsyncSession, spec: OperationSpec[Any, Any]) -> BaseModel:
        if await operation_snapshot_stale(
            session, spec, self.operation, operation_payload_dict(self.operation.payload_json)
        ):
            raise CodedHTTPException(
                code="OPERATION_SNAPSHOT_STALE",
                status_code=409,
                detail="目标已发生变化，请重新发起操作",
            )
        return parse_operation_payload(self.operation.payload_json, spec.payload_schema)

    async def record(
        self, session: AsyncSession, spec: OperationSpec[Any, Any], result: BaseModel
    ) -> None:
        _record_existing(self.operation, result, utcnow())
        self.operation.attempts += 1


async def execute_retry_operation(
    session: AsyncSession, spec: OperationSpec[Any, Any], operation: AgentOperation
) -> None:
    await _execute(session, spec, _RetryExecution(operation, str(uuid4())))


@dataclass
class _DirectExecution:
    runtime: AgentRuntimeContext
    payload: BaseModel
    auth_mode: AuthMode
    basis_json: str | None
    target: tuple[str, str] | None
    authorization: OperationAuthorization
    payload_json: str
    baseline_snapshot: str | None = None
    basis_stale: bool = False
    snapshot_json: str | None = None
    attempt: int = 0
    attempts_json: str | None = None
    effect_args: dict[str, Any] | None = None
    execution_id: str = ""
    operation: AgentOperation | None = None

    async def prepare(self, session: AsyncSession, spec: OperationSpec[Any, Any]) -> BaseModel:
        self.snapshot_json = None
        if spec.capture_state is not None:
            self.snapshot_json = (await spec.capture_state(session, self.payload)).model_dump_json()
            if (
                self.attempt > 0
                and self.baseline_snapshot is not None
                and self.snapshot_json != self.baseline_snapshot
            ):
                raise CodedHTTPException(
                    code="OPERATION_SNAPSHOT_STALE",
                    status_code=409,
                    detail="目标在自动重试期间被修改，请重新发起操作",
                )
            if (
                self.attempt == 0
                and self.basis_json is not None
                and self.snapshot_json != self.basis_json
            ):
                self.basis_stale = True
                raise CodedHTTPException(
                    code="OPERATION_SNAPSHOT_STALE",
                    status_code=409,
                    detail="生成期间目标或计划已被修改，请重新发起操作",
                )
        if self.attempt == 0:
            self.baseline_snapshot = self.snapshot_json
        if spec.submission_validator is not None:
            await spec.submission_validator(session, self.payload)
        return self.payload

    async def record(
        self, session: AsyncSession, spec: OperationSpec[Any, Any], result: BaseModel
    ) -> None:
        self.operation = await record_direct_execution(
            session,
            action=spec.action,
            level=spec.level.value,
            target=self.target,
            payload_json=self.payload_json,
            authorization=self.authorization,
            result_dict=result.model_dump(mode="json"),
            snapshot_json=self.snapshot_json,
            attempts=1 + self.attempt,
            attempts_json=self.attempts_json,
        )
        if self.effect_args is not None:
            await complete_effect(
                session,
                self.runtime,
                spec.action,
                self.effect_args,
                result={
                    "ok": True,
                    "executed": _direct_execution_body(
                        self.operation, spec, self.auth_mode, self.payload, result
                    ),
                },
            )


async def _failure_snapshot(
    session: AsyncSession, spec: OperationSpec[Any, Any], validated: BaseModel
) -> str | None:
    """失败记账小事务内补固化执行前快照（工单 06）：主事务回滚后目标态＝初试
    执行前态；目标不可达（如已删除）时快照缺席，重试由快照重验保守拒绝。"""
    if spec.capture_state is None:
        return None
    try:
        return (await spec.capture_state(session, validated)).model_dump_json()
    except CodedHTTPException:
        return None


def _final_attempts_json(
    transient_history: list[dict[str, Any]], attempt: int, error_code: str
) -> str:
    """失败落定时补记最终尝试（工单 06：attempts_json 逐次尝试错误历史可查，
    与推进 worker 的 append_attempt 同形）。"""
    history = [
        *transient_history,
        {
            "attempt": 1 + attempt,
            "error_code": error_code,
            "at": utcnow().isoformat(),
        },
    ]
    return json.dumps(history, ensure_ascii=False, separators=(",", ":"))


def _direct_execution_body(
    operation: AgentOperation,
    spec: OperationSpec[Any, Any],
    auth_mode: AuthMode,
    validated: BaseModel,
    result: BaseModel,
) -> dict[str, Any]:
    """直执行成功回执的 executed 载荷（工具返回与效果行可恢复结果同构）。"""
    return {
        "operation_id": operation.id,
        "action": spec.action,
        "level": spec.level.value,
        "auth_mode": auth_mode.value,
        "payload": validated.model_dump(mode="json"),
        "result": result.model_dump(mode="json"),
    }


async def execute_direct_operation(
    runtime: AgentRuntimeContext,
    spec: OperationSpec[Any, Any],
    validated: BaseModel,
    auth_mode: AuthMode,
    *,
    basis_json: str | None = None,
    preparation: EffectPreparation | None = None,
    effect_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """自动档直执行（spec 决策 11）：单事务写 operation＋业务结果。

    auth_mode 是本次提交的生效档（会话覆盖与本轮起点取更严格者），
    授权依据与回执载荷如实记录执行时实际生效档。成功：应用器领域写入与
    operation 行（SUCCEEDED＋result 回填＋授权依据）同一事务原子提交；
    失败：业务事务整体回滚（＝未发生），独立小事务落 FAILED operation＋
    稳定错误码（_mark_failed 先例，诊断不断链；**各失败分支统一补固化
    执行前快照**——快照缺席会让修改类操作的手动重试被保守拒绝，无法
    恢复）。返回工具 JSON 载荷：
    成功 {ok, executed}；失败 {ok: False, error, operation_id}（模型转述
    原因，operation_id 供消息流锚点与手动重试定位）。

    瞬时故障自动重试（工单 06，spec 决策 20）：SQLITE_BUSY 等锁竞争在原
    operation 身份下小睡重试 ≤2 次（attempts／attempts_json 如实累计），
    **每轮重验授权与版本**（与推进 worker 同口径）——重试轮先重检会话
    覆盖档位（同进程降档即时约束，不满足直执行 → FAILED＋
    OPERATION_APPROVAL_REQUIRED），再比对快照与首次尝试基线（锁竞争窗口
    内目标被修改 → FAILED＋OPERATION_SNAPSHOT_STALE，不覆盖手改）；耗尽
    落 FAILED＋OPERATION_TRANSIENT_ERROR。业务拒绝（CodedHTTPException）
    不自动重试。run 取消（spec 决策 20 第三项）为 run 概念；轮次持久取消
    （ChatTurn 规格 §2/§14）在直执行主事务开头原子校验，命中即拒绝且不落
    FAILED 回执（取消后禁止新增任何副作用）。

    失败载荷携带 operation_id（工单 06 review 修复）：FAILED 行已在独立小
    事务落库，id 随载荷返回——消息流锚点据此定位失败回执，回执卡的手动
    重试入口才真实可达（否则锚点只覆盖成功路径）。
    """
    payload_json = validated.model_dump_json()
    target = spec.target_resolver(validated) if spec.target_resolver is not None else None
    authorization = direct_authorization(runtime, auth_mode)
    # 首次尝试的执行前快照＝重试轮版本重验基线（首试事务回滚不吞该值）。
    entry = _DirectExecution(
        runtime, validated, auth_mode, basis_json, target, authorization, payload_json
    )
    async with runtime.session_factory() as session:
        attempt = 0
        transient_history: list[dict[str, Any]] = []
        while True:
            if attempt > 0 and not should_execute_directly(
                effective_session_auth_mode(runtime.session_id, runtime.auth_mode),
                spec.level,
            ):
                # 重试轮授权重检（spec 决策 20）：会话在锁竞争窗口内降档 →
                # 原授权失效，停止重试（Run adapter 同口径）。
                async with session.begin():
                    failed = await record_direct_execution(
                        session,
                        action=spec.action,
                        level=spec.level.value,
                        target=target,
                        payload_json=payload_json,
                        authorization=authorization,
                        result_dict=None,
                        error_code="OPERATION_APPROVAL_REQUIRED",
                        snapshot_json=await _failure_snapshot(session, spec, validated),
                        attempts=1 + attempt,
                        attempts_json=_final_attempts_json(
                            transient_history, attempt, "OPERATION_APPROVAL_REQUIRED"
                        ),
                    )
                return {
                    "ok": False,
                    "error": "OPERATION_APPROVAL_REQUIRED",
                    "operation_id": failed.id,
                }
            attempts_json = (
                json.dumps(transient_history, ensure_ascii=False, separators=(",", ":"))
                if transient_history
                else None
            )
            try:
                async with session.begin():
                    # 业务提交处最终校验（ChatTurn 规格 §2/§14）：持久取消先
                    # 落库或执行身份失配 → 拒绝执行，不落任何行（取消不是操作
                    # 失败，FAILED 回执本身也是新增副作用）。重试轮同位重查。
                    if not await runtime.turn_write_allowed(session):
                        return {"ok": False, "error": CHAT_TURN_CANCELLED}
                    entry.attempt = attempt
                    entry.attempts_json = attempts_json
                    entry.effect_args = effect_args if preparation is not None else None
                    entry.execution_id = str(uuid4())
                    result = await _execute(session, spec, entry)
                    operation = entry.operation
                    assert operation is not None
            except CodedHTTPException as exc:
                async with session.begin():
                    failed = await record_direct_execution(
                        session,
                        action=spec.action,
                        level=spec.level.value,
                        target=target,
                        payload_json=payload_json,
                        authorization=authorization,
                        result_dict=None,
                        error_code=exc.code,
                        snapshot_json=(
                            basis_json
                            if entry.basis_stale and basis_json is not None
                            else await _failure_snapshot(session, spec, validated)
                        ),
                        attempts=1 + attempt,
                        attempts_json=_final_attempts_json(transient_history, attempt, exc.code),
                    )
                return {"ok": False, "error": exc.code, "operation_id": failed.id}
            except OperationalError as exc:
                if is_transient_exception(exc) and attempt < TRANSIENT_MAX_RETRIES:
                    attempt += 1
                    transient_history.append(
                        {
                            "attempt": attempt,
                            "error_code": OPERATION_TRANSIENT_ERROR,
                            "at": utcnow().isoformat(),
                        }
                    )
                    await asyncio.sleep(0.05 * attempt)
                    continue
                async with session.begin():
                    failed = await record_direct_execution(
                        session,
                        action=spec.action,
                        level=spec.level.value,
                        target=target,
                        payload_json=payload_json,
                        authorization=authorization,
                        result_dict=None,
                        error_code=OPERATION_TRANSIENT_ERROR,
                        # 失败记账统一保留执行基线（review P2）：重试轮版本
                        # 重验通过＝目标未变，回滚后当前态＝初试前态——快照
                        # 缺席会让手动重试被快照重验保守拒绝（无法恢复）。
                        snapshot_json=await _failure_snapshot(session, spec, validated),
                        attempts=1 + attempt,
                        attempts_json=_final_attempts_json(
                            transient_history, attempt, OPERATION_TRANSIENT_ERROR
                        ),
                    )
                return {
                    "ok": False,
                    "error": OPERATION_TRANSIENT_ERROR,
                    "operation_id": failed.id,
                }
            except Exception:
                # 非编码异常（bug / 环境故障）：原子回滚＝未发生，落 INTERNAL 稳定
                # 错误码（先例：提案框架非编码异常路径）；快照同口径保留。
                async with session.begin():
                    failed = await record_direct_execution(
                        session,
                        action=spec.action,
                        level=spec.level.value,
                        target=target,
                        payload_json=payload_json,
                        authorization=authorization,
                        result_dict=None,
                        error_code="INTERNAL",
                        snapshot_json=await _failure_snapshot(session, spec, validated),
                        attempts=1 + attempt,
                        attempts_json=_final_attempts_json(transient_history, attempt, "INTERNAL"),
                    )
                return {"ok": False, "error": "INTERNAL", "operation_id": failed.id}
            break  # 成功（各失败分支均已在 except 内返回）
    return {
        "ok": True,
        "executed": _direct_execution_body(operation, spec, auth_mode, validated, result),
    }
