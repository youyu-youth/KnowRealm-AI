"""执行事实服务：operation 回写、查询分层、显式清理与 Run 唤醒（spec 决策 2/4/7/21）。

- 确认路径回接：操作路径应用器执行成功后在同一确认事务内写 operation 行
  （run_id 空、proposal_id 关联、payload 投影、result 回填、authorization_json
  授权依据）——由注册表适配器调用（只传基本值，避免 registry↔service 环），
  领域应用器零感知；
- 查询：runs / operations / activity 的只读列表与 run 详情；
- 清理：按终态 run 删除（FK 级联其 operations）＋批量清理已结束（终态 runs
  ＋终态单步 operations）；活动项拒绝（稳定错误码）；提案审批事实永不删；
- 唤醒与取消（工单 05）：显式动作（继续指令 / 失败项重试 / 取消）走原子抢占
  条件 UPDATE＋rowcount 判定，推进 worker 只认 RUNNING（spec 决策 7）。
"""

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.base import utcnow
from app.modules.agent.runs.models import AgentActivity, AgentOperation, AgentRun
from app.modules.agent.runs.schemas import (
    OPERATION_DEPENDENCY_FAILED,
    OPERATION_TERMINAL_STATUSES,
    RUN_TERMINAL_STATUSES,
    ActivityScope,
    ActivityType,
    OperationAuthorization,
    OperationStatus,
    RunStatus,
    parse_plan_out,
    plan_dependencies,
)
from app.modules.agent.turns.models import ChatTurn, ChatTurnRun, ChatTurnWait
from app.modules.agent.turns.schemas import ChatTurnStatus
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.schemas import ProcessingJobStatus, ProcessingJobType
from app.modules.library.models import AgentProposal
from app.shared.errors import CodedHTTPException

if TYPE_CHECKING:
    # 仅类型标注（运行时导入会构成 registry↔service 环：registry 引用本模块的
    # operation 回写函数）。
    from app.modules.agent.operations.registry import OperationSpec

# AGENT_RUN 触发 job 的类型值（Run 推进 worker 的 job_type；无状态触发器）。
AGENT_RUN_JOB_TYPE = ProcessingJobType.AGENT_RUN


def protected_run_ids() -> Select[tuple[str]]:
    return (
        select(ChatTurnRun.run_id)
        .join(ChatTurn, ChatTurn.id == ChatTurnRun.turn_id)
        .where(ChatTurn.status.notin_([s.value for s in ChatTurnStatus if s.is_terminal]))
    )


def protected_operation() -> ColumnElement[bool]:
    triggered = (
        select(ChatTurn.id)
        .where(
            ChatTurn.status.notin_([s.value for s in ChatTurnStatus if s.is_terminal]),
            func.json_extract(AgentOperation.authorization_json, "$.message_id")
            == ChatTurn.user_message_id,
        )
        .exists()
    )
    awaited = (
        select(ChatTurnWait.source_operation_id)
        .join(ChatTurn, ChatTurn.id == ChatTurnWait.turn_id)
        .where(
            ChatTurn.status.notin_([s.value for s in ChatTurnStatus if s.is_terminal]),
            ChatTurnWait.source_operation_id.is_not(None),
        )
    )
    return triggered | AgentOperation.id.in_(awaited)


def append_attempt(operation: AgentOperation, error_code: str, *, now: datetime) -> None:
    """逐次尝试错误历史（attempts_json）：失败尝试留痕，重试沿用原 operation
    身份（工单 06，spec 决策 20；推进 worker 与手动重试共用口径）。"""
    history: list[object] = []
    if operation.attempts_json:
        try:
            parsed: object = json.loads(operation.attempts_json)
        except ValueError:
            parsed = None
        if isinstance(parsed, list):
            history = cast("list[object]", parsed)
    history.append({"attempt": operation.attempts, "error_code": error_code, "at": now.isoformat()})
    operation.attempts_json = json.dumps(history, ensure_ascii=False, separators=(",", ":"))


def _job_run_id_column() -> ColumnElement[Any]:
    """触发 job 的 run_id 投影列（run_id 只存 input_json；json_extract 无存根，
    cast 收口为列表达式，先例见 settings/usage.py）。"""
    return cast(
        "ColumnElement[Any]",
        func.json_extract(ProcessingJob.input_json, "$.run_id"),
    )


async def list_nonterminal_runs(
    session: AsyncSession, session_id: str, *, limit: int | None = None
) -> list[AgentRun]:
    """本会话未结束（非终态）Run，最近在前——上下文摘要与活跃 Run 判定共用。"""
    terminal = [status.value for status in RUN_TERMINAL_STATUSES]
    stmt = (
        select(AgentRun)
        .where(AgentRun.session_id == session_id, AgentRun.status.not_in(terminal))
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list((await session.scalars(stmt)).all())


async def find_active_run(session: AsyncSession, session_id: str) -> AgentRun | None:
    """本会话当前活跃 Run（非终态、最新一个）——计划追加与固定计划约束的锚点
    （活跃 Run 上新增目标升回确认）；批量阈值的累计口径见
    :func:`count_session_operations`（不以活跃 Run 为界）。
    """
    runs = await list_nonterminal_runs(session, session_id, limit=1)
    return runs[0] if runs else None


async def count_session_operations(session: AsyncSession, session_id: str) -> int:
    """本会话全部 Run 的 operation 行数（含终态 Run 与已完成 / 失败 / 跳过项；
    重试沿用原行不新增）——帮我批准档阈值的直接业务目标数与写操作数（本阶段批量
    动作一目标一写操作同值）。

    计数按会话累计、不按活跃 Run 划界（spec 决策 11：计入已完成项，拆调用 /
    分段 / 重启不重置）——首批完成（Run 终态）后再提交同样计入，阈值不因任务
    落定而重置；单步操作（run_id 空）不属批量计划，不计入。
    """
    return int(
        await session.scalar(
            select(func.count())
            .select_from(AgentOperation)
            .join(AgentRun, AgentRun.id == AgentOperation.run_id)
            .where(AgentRun.session_id == session_id)
        )
        or 0
    )


async def has_active_trigger(session: AsyncSession, run_id: str) -> bool:
    """该 Run 是否已有活动触发 job（PENDING/RUNNING；领取守卫判定）。"""
    job = await session.scalar(
        select(ProcessingJob.id).where(
            ProcessingJob.job_type == AGENT_RUN_JOB_TYPE.value,
            ProcessingJob.status.in_(
                (ProcessingJobStatus.PENDING.value, ProcessingJobStatus.RUNNING.value)
            ),
            _job_run_id_column() == run_id,
        )
    )
    return job is not None


async def enqueue_trigger(session: AsyncSession, run_id: str) -> None:
    """投递 AGENT_RUN 触发 job（无状态触发器：input 仅 run_id，不承载任务状态）。

    同 Run 已有活动触发 job 时不重复投递（唤醒走原子抢占；存储层另有部分唯一
    索引作纵深防御，迁移 0033）。job 无 record/library_item 主体，record_id 空。
    """
    if await has_active_trigger(session, run_id):
        return
    now = utcnow()
    session.add(
        ProcessingJob(
            id=str(uuid4()),
            record_id=None,
            library_item_id=None,
            job_type=AGENT_RUN_JOB_TYPE,
            status=ProcessingJobStatus.PENDING,
            progress=0,
            attempts=0,
            max_attempts=1,
            next_run_at=None,
            input_json=json.dumps({"run_id": run_id}, separators=(",", ":")),
            result_json=None,
            error_code=None,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
    )
    await session.flush()


async def list_run_operations(session: AsyncSession, run_id: str) -> list[AgentOperation]:
    """取该 Run 的操作行（created_at + id 序，稳定但同批提交会打平——呈现与推进
    顺序由 :func:`order_run_operations` 按计划项索引收敛）。"""
    return list(
        (
            await session.scalars(
                select(AgentOperation)
                .where(AgentOperation.run_id == run_id)
                .order_by(AgentOperation.created_at.asc(), AgentOperation.id.asc())
            )
        ).all()
    )


def order_run_operations(
    operations: list[AgentOperation], plan_json: str | None, plan_version: int
) -> list[AgentOperation]:
    """按计划顺序排序：步骤顺序的权威来源是计划（spec 决策 13「逐项列出」）——
    同一批提交的操作 created_at 相同，仅靠时间序会打平。不在计划内的操作
    （异常数据）保持原相对顺序排在末尾。

    读取 / 展示口径（坏计划降级为时间序，不炸查询）；执行路径不受其影响——
    worker 在排序前已严格校验计划（工单 05 review）。"""
    order = {
        item.operation_id: item.index for item in parse_plan_out(plan_json, plan_version).items
    }
    tail = len(order)
    return sorted(
        operations,
        key=lambda operation: (order.get(operation.id, tail), operation.created_at, operation.id),
    )


async def record_confirmed_operation(
    session: AsyncSession,
    *,
    proposal: AgentProposal,
    action: str,
    level: str,
    result_dict: dict[str, Any],
    snapshot_json: str | None = None,
) -> AgentOperation:
    """确认事务内回接写 operation（spec 决策 4：执行事实唯一源）。

    单步操作不建 run（run_id 空）；失败路径不落 operation（应用器异常时整个
    确认事务回滚＝未发生，可安全重试）。快照原样随提案行转入 operation
    （工单 03：Undo 补偿数据）；提案 result_json 是本行结果的单向投影缓存
    （同事务同值，AgentProposalOut 契约零变化）。
    """
    now = utcnow()
    operation = AgentOperation(
        id=str(uuid4()),
        run_id=None,
        proposal_id=proposal.id,
        action=action,
        level=level,
        target_type=proposal.target_type,
        target_id=proposal.target_id,
        payload_json=proposal.payload_json,
        snapshot_json=snapshot_json,
        authorization_json=OperationAuthorization(
            session_id=proposal.session_id, message_id=proposal.message_id
        ).model_dump_json(),
        status=OperationStatus.SUCCEEDED.value,
        attempts=1,
        result_json=json.dumps(result_dict, ensure_ascii=False),
        created_at=now,
        updated_at=now,
        finished_at=now,
    )
    session.add(operation)
    await session.flush()
    return operation


async def record_direct_execution(
    session: AsyncSession,
    *,
    action: str,
    level: str,
    target: tuple[str, str] | None,
    payload_json: str,
    authorization: OperationAuthorization,
    result_dict: dict[str, Any] | None,
    error_code: str | None = None,
    snapshot_json: str | None = None,
    attempts: int = 1,
    attempts_json: str | None = None,
) -> AgentOperation:
    """自动档直执行写 operation（工单 02，spec 决策 10/11）。

    成功：调用方执行事务内与业务结果同事务提交（SUCCEEDED＋result 回填＋
    执行前快照，工单 03）；失败：业务事务已回滚（＝未发生），调用方在独立
    小事务再调本函数落 FAILED＋稳定错误码（提案 _mark_failed 先例）。
    authorization 是直执行的授权依据（档位＋触发指令摘录＋消息引用），单步
    无 run 时为本行授权事实的唯一载体（ADR-0026）。attempts／attempts_json
    随瞬时自动重试累计（工单 06，spec 决策 20：重试沿用原 operation 身份）。
    """
    now = utcnow()
    operation = AgentOperation(
        id=str(uuid4()),
        run_id=None,
        proposal_id=None,
        action=action,
        level=level,
        target_type=target[0] if target is not None else None,
        target_id=target[1] if target is not None else None,
        payload_json=payload_json,
        snapshot_json=snapshot_json,
        authorization_json=authorization.model_dump_json(),
        status=OperationStatus.SUCCEEDED.value
        if result_dict is not None
        else OperationStatus.FAILED.value,
        attempts=attempts,
        attempts_json=attempts_json,
        result_json=json.dumps(result_dict, ensure_ascii=False)
        if result_dict is not None
        else None,
        error_code=error_code,
        created_at=now,
        updated_at=now,
        finished_at=now,
    )
    session.add(operation)
    await session.flush()
    return operation


async def record_auth_mode_switch(
    session: AsyncSession,
    *,
    from_mode: str,
    to_mode: str,
    scope: ActivityScope,
    session_id: str | None = None,
) -> AgentActivity:
    """模式切换审计行（工单 02，spec 决策 22）：from / to / 作用域 / 会话 / 时间。

    返回落库行（全局切档编排的失败补偿按 id 定位删除）。
    """
    activity = AgentActivity(
        id=str(uuid4()),
        activity_type=ActivityType.AUTH_MODE_SWITCH.value,
        from_mode=from_mode,
        to_mode=to_mode,
        scope=scope.value,
        session_id=session_id,
        created_at=utcnow(),
    )
    session.add(activity)
    await session.flush()
    return activity


def _json_list(raw: str | None) -> list[dict[str, Any]] | None:
    """attempts_json 列的投影（逐次尝试错误历史，坏值降级为 None 不炸查询）。"""
    if raw is None:
        return None
    try:
        value: object = json.loads(raw)
    except ValueError:
        return None
    return cast("list[dict[str, Any]]", value) if isinstance(value, list) else None


def _json_dict(raw: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        value: object = json.loads(raw)
    except ValueError:
        return None
    return cast("dict[str, Any]", value) if isinstance(value, dict) else None


def operation_out(operation: AgentOperation) -> dict[str, Any]:
    """行→输出投影（JSON 列解析为 dict，坏值降级为空/None 不炸查询）。

    可撤销性从注册表派生（工单 06：可撤销性在注册项声明，工具结果与回执
    透出）——函数内 import 规避 service↔registry 循环依赖（registry 引用
    本模块的 operation 回写函数）。"""
    from app.modules.agent.operations.registry import get_operation

    spec = get_operation(operation.action)
    undoable = spec is not None and spec.undoer is not None
    return {
        "id": operation.id,
        "run_id": operation.run_id,
        "proposal_id": operation.proposal_id,
        "action": operation.action,
        "level": operation.level,
        "target_type": operation.target_type,
        "target_id": operation.target_id,
        "payload": _json_dict(operation.payload_json) or {},
        "snapshot": _json_dict(operation.snapshot_json),
        "authorization": _json_dict(operation.authorization_json),
        "status": operation.status,
        "attempts": operation.attempts,
        "attempts_history": _json_list(operation.attempts_json),
        "result": _json_dict(operation.result_json),
        "error_code": operation.error_code,
        "undoable": undoable,
        "undo_reason": None if undoable else _undo_reason(spec),
        "undo_of": operation.undo_of,
        "undone_by": operation.undone_by,
        "created_at": operation.created_at,
        "updated_at": operation.updated_at,
        "finished_at": operation.finished_at,
    }


def _undo_reason(spec: "OperationSpec[Any, Any] | None") -> str:
    """不可撤销原因（注册项声明；未注册动作的兜底文案）。"""
    reason = getattr(spec, "undo_reason", None) if spec is not None else None
    return str(reason) if reason else "该操作不提供撤销"


def _run_out(run: AgentRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "session_id": run.session_id,
        "auth_mode": run.auth_mode,
        "instruction_text": run.instruction_text,
        "proposal_id": run.proposal_id,
        "status": run.status,
        "plan": _json_dict(run.plan_json),
        "plan_version": run.plan_version,
        "waiting_reason": run.waiting_reason,
        "cancel_requested": bool(run.cancel_requested),
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "finished_at": run.finished_at,
    }


class RunHistoryService:
    """操作历史查询与清理（只读 + 终态守卫删除）。"""

    @staticmethod
    async def list_runs(
        session: AsyncSession,
        *,
        status: str | None = None,
        session_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        stmt = select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit).offset(offset)
        if status is not None:
            stmt = stmt.where(AgentRun.status == status)
        if session_id is not None:
            stmt = stmt.where(AgentRun.session_id == session_id)
        runs = list((await session.scalars(stmt)).all())
        return [_run_out(run) for run in runs]

    @staticmethod
    async def get_run_detail(session: AsyncSession, run_id: str) -> dict[str, Any]:
        run = await session.get(AgentRun, run_id)
        if run is None:
            raise CodedHTTPException(
                code="AGENT_RUN_NOT_FOUND", status_code=404, detail="任务不存在"
            )
        operations = order_run_operations(
            await list_run_operations(session, run_id), run.plan_json, run.plan_version
        )
        return {**_run_out(run), "operations": [operation_out(op) for op in operations]}

    @staticmethod
    async def list_operations(
        session: AsyncSession,
        *,
        status: str | None = None,
        session_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(AgentOperation)
            .order_by(AgentOperation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            stmt = stmt.where(AgentOperation.status == status)
        if session_id is not None:
            # 会话关联只存在于授权依据列（决策 2 列集无 session_id），JSON1
            # 投影过滤（json_valid CHECK 保证列恒可解析；迁移 0030 已在用）。
            stmt = stmt.where(
                func.json_extract(AgentOperation.authorization_json, "$.session_id") == session_id
            )
        operations = list((await session.scalars(stmt)).all())
        return [operation_out(op) for op in operations]

    @staticmethod
    async def list_activity(
        session: AsyncSession, *, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        stmt = (
            select(AgentActivity)
            .order_by(AgentActivity.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        activities = list((await session.scalars(stmt)).all())
        return [
            {
                "id": activity.id,
                "activity_type": activity.activity_type,
                "from_mode": activity.from_mode,
                "to_mode": activity.to_mode,
                "scope": activity.scope,
                "session_id": activity.session_id,
                "created_at": activity.created_at,
            }
            for activity in activities
        ]

    @staticmethod
    async def delete_run_history(session: AsyncSession, run_id: str) -> None:
        """按终态 run 删除历史（run＋其 operations，FK 级联）。

        活动 run 拒绝清理（先结束或取消再清理）；提案审批事实永不删。
        """
        async with session.begin():
            # 与新等待登记串行，检查后不能被迟到的 ORM DELETE 级联删除。
            await session.execute(
                update(AgentRun).where(AgentRun.id == run_id).values(updated_at=AgentRun.updated_at)
            )
            run = await session.get(AgentRun, run_id)
            if run is None:
                raise CodedHTTPException(
                    code="AGENT_RUN_NOT_FOUND", status_code=404, detail="任务不存在"
                )
            if run.status not in {status.value for status in RUN_TERMINAL_STATUSES}:
                raise CodedHTTPException(
                    code="AGENT_RUN_NOT_FINISHED",
                    status_code=409,
                    detail="任务尚未结束，不能清理历史",
                )
            if (
                await session.scalar(
                    select(AgentRun.id).where(
                        AgentRun.id == run_id, AgentRun.id.in_(protected_run_ids())
                    )
                )
                is not None
            ):
                raise CodedHTTPException(
                    code="AGENT_RUN_NOT_FINISHED",
                    status_code=409,
                    detail="回答仍依赖此任务，暂不能清理历史",
                )
            await session.delete(run)

    @staticmethod
    async def purge_finished(session: AsyncSession) -> dict[str, int]:
        """批量清理已结束任务的历史（spec 决策 21）：终态 runs（级联其
        operations）＋终态单步 operations；活动项不触碰；提案永不删。"""
        terminal_run_statuses = [status.value for status in RUN_TERMINAL_STATUSES]
        terminal_op_statuses = [status.value for status in OPERATION_TERMINAL_STATUSES]
        async with session.begin():
            await session.execute(
                update(AgentRun)
                .where(AgentRun.status.in_(terminal_run_statuses))
                .values(updated_at=AgentRun.updated_at)
            )
            cascading = cast(
                int,
                await session.scalar(
                    select(func.count())
                    .select_from(AgentOperation)
                    .where(
                        AgentOperation.run_id.in_(
                            select(AgentRun.id).where(
                                AgentRun.status.in_(terminal_run_statuses),
                                AgentRun.id.notin_(protected_run_ids()),
                            )
                        )
                    )
                ),
            )
            runs_claimed = await session.execute(
                delete(AgentRun).where(
                    AgentRun.status.in_(terminal_run_statuses),
                    AgentRun.id.notin_(protected_run_ids()),
                )
            )
            steps_claimed = await session.execute(
                delete(AgentOperation).where(
                    AgentOperation.run_id.is_(None),
                    AgentOperation.status.in_(terminal_op_statuses),
                    ~protected_operation(),
                )
            )
            # DELETE 结果必为 CursorResult（proposals.confirm 抢占判定同收窄方式）。
            assert isinstance(runs_claimed, CursorResult)
            assert isinstance(steps_claimed, CursorResult)
            runs_deleted = int(runs_claimed.rowcount or 0)
            steps_deleted = int(steps_claimed.rowcount or 0)
        return {
            "runs_deleted": runs_deleted,
            "operations_deleted": steps_deleted + cascading,
        }


async def _require_run(session: AsyncSession, run_id: str) -> AgentRun:
    run = await session.get(AgentRun, run_id)
    if run is None:
        raise CodedHTTPException(code="AGENT_RUN_NOT_FOUND", status_code=404, detail="任务不存在")
    return run


async def _require_active_run(session: AsyncSession, run_id: str) -> AgentRun:
    """取消的 Run 守卫：只有未收尾的任务（进行中 / 等待用户 / 等待后台 job）
    可以取消。"""
    run = await _require_run(session, run_id)
    if run.status not in (
        RunStatus.RUNNING.value,
        RunStatus.WAITING_USER.value,
        RunStatus.WAITING_JOB.value,
    ):
        raise CodedHTTPException(
            code="AGENT_RUN_ALREADY_FINISHED",
            status_code=409,
            detail="任务已结束，不能取消或重试",
        )
    return run


async def _require_live_run(session: AsyncSession, run_id: str) -> AgentRun:
    """重试的 Run 守卫：COMPLETED 与 CANCELLED 是终局（取消不冒充撤销、完成的
    任务没有可重试项）；PARTIAL_COMPLETED / FAILED 允许失败项重试并重开推进
    （唤醒只由显式动作触发，spec 决策 7）。"""
    run = await _require_run(session, run_id)
    if run.status in (RunStatus.COMPLETED.value, RunStatus.CANCELLED.value):
        raise CodedHTTPException(
            code="AGENT_RUN_ALREADY_FINISHED",
            status_code=409,
            detail="任务已结束，不能取消或重试",
        )
    return run


async def cancel_pending_operations(session: AsyncSession, run: AgentRun) -> int:
    """取消：未执行项置 CANCELLED（已提交结果保留，取消不冒充撤销，spec 用户故事 26）。"""
    now = utcnow()
    operations = await list_run_operations(session, run.id)
    cancelled = 0
    for operation in operations:
        if operation.status != OperationStatus.PLANNED.value:
            continue
        operation.status = OperationStatus.CANCELLED.value
        operation.updated_at = now
        operation.finished_at = now
        cancelled += 1
    return cancelled


def settle_run(run: AgentRun, status: RunStatus, *, now: datetime | None = None) -> None:
    """落 Run 终态（推进终态判定与取消共用；清等待原因与等待 job）。"""
    moment = utcnow() if now is None else now
    run.status = status.value
    run.waiting_reason = None
    run.waiting_job_id = None
    run.finished_at = moment
    run.updated_at = moment


class RunControlService:
    """Run 唤醒与取消（spec 决策 7/15）：唤醒仅由显式动作触发（继续指令 /
    失败项重试 / 取消），全部走原子抢占的条件 UPDATE＋rowcount 判定；推进
    worker 只认 RUNNING，不自动猜测 WAITING_USER 可否继续。
    """

    @staticmethod
    async def cancel_in_transaction(session: AsyncSession, run: AgentRun) -> None:
        """共用取消提交边界，调用方已持有写事务；不撤销已提交的领域 Job。"""
        run.cancel_requested = True
        run.updated_at = utcnow()
        if run.status in (RunStatus.WAITING_USER.value, RunStatus.WAITING_JOB.value):
            await cancel_pending_operations(session, run)
            settle_run(run, RunStatus.CANCELLED)
        else:
            await enqueue_trigger(session, run.id)

    @staticmethod
    async def cancel_run(session: AsyncSession, run_id: str) -> dict[str, Any]:
        """取消（持久化端点）：置 cancel_requested；推进中由 worker 每步检查后
        收尾，等待态无 worker 在跑则就地落 CANCELLED（不新增动作、已提交保留）。

        等待后台 job（WAITING_JOB，工单 06）的取消同「等待用户」就地收尾：未
        执行步骤置 CANCELLED、已提交的后台 job（如网页抓取）不杀保留回执、
        PENDING 触发 job 由领取闸门静默作废；断开 SSE / 关页面不是业务取消
        （推进独立于连接，二阶段语义）。已收尾的任务（部分完成 / 失败 / 完成 /
        已取消）拒绝取消——终局不可改，取消不冒充撤销；重试失败项另有端点。
        """
        async with session.begin():
            await session.execute(
                update(AgentRun).where(AgentRun.id == run_id).values(updated_at=AgentRun.updated_at)
            )
            run = await _require_active_run(session, run_id)
            await RunControlService.cancel_in_transaction(session, run)
        return _run_out(run)

    @staticmethod
    async def resume_run(session: AsyncSession, run_id: str) -> dict[str, Any]:
        """继续指令（显式唤醒）：WAITING_USER → RUNNING 原子抢占并重投触发。

        抢占用条件 UPDATE（提案确认先例）：并发继续只有一个请求拿到执行权，
        其余 rowcount=0 → 409。不自动重试失败项（重试是独立显式动作）。
        """
        now = utcnow()
        async with session.begin():
            claimed = await session.execute(
                update(AgentRun)
                .where(
                    AgentRun.id == run_id,
                    AgentRun.status == RunStatus.WAITING_USER.value,
                )
                .values(status=RunStatus.RUNNING.value, waiting_reason=None, updated_at=now)
            )
            if not isinstance(claimed, CursorResult) or claimed.rowcount != 1:
                await _require_run(session, run_id)
                raise CodedHTTPException(
                    code="AGENT_RUN_NOT_WAITING",
                    status_code=409,
                    detail="任务当前不在等待用户处理，无需继续",
                )
            await enqueue_trigger(session, run_id)
        return _run_out(await _require_run(session, run_id))

    @staticmethod
    async def retry_operation(
        session: AsyncSession, *, run_id: str, operation_id: str
    ) -> dict[str, Any]:
        """失败 / 跳过项重试（沿用原 operation 身份，attempts 递增）并唤醒。

        依赖该项而跳过的后续步骤一并恢复为待执行（阻塞原因已修复）——不重复
        已成功项；终态 Run 与未失败项拒绝（稳定错误码）。补偿行（undo_of
        非空，批次撤销的留痕 / 补偿）拒绝：重试会按其 payload 重放正向操作
        语义，失败补偿的正确路径是重新发起撤销（工单 06 review P2）。
        """
        now = utcnow()
        async with session.begin():
            run = await _require_live_run(session, run_id)
            operation = await session.get(AgentOperation, operation_id)
            if operation is None or operation.run_id != run_id:
                raise CodedHTTPException(
                    code="AGENT_RUN_OPERATION_NOT_FOUND",
                    status_code=404,
                    detail="任务中的操作不存在",
                )
            if operation.undo_of is not None:
                raise CodedHTTPException(
                    code="AGENT_RUN_OPERATION_NOT_RETRYABLE",
                    status_code=409,
                    detail="补偿操作不能经任务重试，请重新发起撤销",
                )
            if operation.status not in (
                OperationStatus.FAILED.value,
                OperationStatus.SKIPPED.value,
            ):
                raise CodedHTTPException(
                    code="AGENT_RUN_OPERATION_NOT_RETRYABLE",
                    status_code=409,
                    detail="仅失败或跳过的步骤可以重试",
                )
            operation.status = OperationStatus.PLANNED.value
            operation.attempts += 1
            operation.error_code = None
            operation.finished_at = None
            operation.updated_at = now
            for blocked in await _blocked_by(session, run, operation_id):
                blocked.status = OperationStatus.PLANNED.value
                blocked.error_code = None
                blocked.finished_at = None
                blocked.updated_at = now
            # 唤醒：等待态原子抢占；已收尾（部分完成 / 失败）的任务重开推进。
            # waiting_job_id 随 waiting_reason 同清（口径对称：可重试的终态在
            # 等待分流时已清列，此处防御异常残留）。
            await session.execute(
                update(AgentRun)
                .where(
                    AgentRun.id == run_id,
                    AgentRun.status.in_(
                        (
                            RunStatus.WAITING_USER.value,
                            RunStatus.PARTIAL_COMPLETED.value,
                            RunStatus.FAILED.value,
                        )
                    ),
                )
                .values(
                    status=RunStatus.RUNNING.value,
                    waiting_reason=None,
                    waiting_job_id=None,
                    finished_at=None,
                    updated_at=now,
                )
            )
            await enqueue_trigger(session, run_id)
        return _run_out(await _require_run(session, run_id))


async def _blocked_by(
    session: AsyncSession, run: AgentRun, operation_id: str
) -> list[AgentOperation]:
    """依赖该项（传递）而被跳过的步骤：重试时一并恢复为待执行。

    读取口径与 order_run_operations 同源（坏计划降级为「无依赖」）；重试即便
    放行也执行不了——worker 会在推进前严格校验计划并落 AGENT_RUN_PLAN_INVALID
    （工单 05 review），此处不重复拦截（前端重试失败无错误呈现，拦截反而静默）。"""
    plan = parse_plan_out(run.plan_json, run.plan_version)
    reverse: dict[str, list[str]] = {}
    for block_id, dependencies in plan_dependencies(plan).items():
        for dependency in dependencies:
            reverse.setdefault(dependency, []).append(block_id)
    affected: set[str] = set()
    frontier = [operation_id]
    while frontier:
        current = frontier.pop()
        for dependent in reverse.get(current, []):
            if dependent in affected or dependent == operation_id:
                continue
            affected.add(dependent)
            frontier.append(dependent)
    if not affected:
        return []
    operations = await list_run_operations(session, run.id)
    return [
        operation
        for operation in operations
        if operation.id in affected
        and operation.status == OperationStatus.SKIPPED.value
        and operation.error_code == OPERATION_DEPENDENCY_FAILED
    ]
