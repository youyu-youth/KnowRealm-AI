"""执行事实服务：operation 回写、查询分层与显式清理（spec 决策 2/4/21）。

- 确认路径回接：操作路径应用器执行成功后在同一确认事务内写 operation 行
  （run_id 空、proposal_id 关联、payload 投影、result 回填、authorization_json
  授权依据）——由注册表适配器调用（只传基本值，避免 registry↔service 环），
  领域应用器零感知；
- 查询：runs / operations / activity 的只读列表与 run 详情；
- 清理：按终态 run 删除（FK 级联其 operations）＋批量清理已结束（终态 runs
  ＋终态单步 operations）；活动项拒绝（稳定错误码）；提案审批事实永不删。
"""

import json
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.agent.runs.models import AgentActivity, AgentOperation, AgentRun
from app.modules.agent.runs.schemas import (
    OPERATION_TERMINAL_STATUSES,
    RUN_TERMINAL_STATUSES,
    ActivityScope,
    ActivityType,
    OperationAuthorization,
    OperationStatus,
)
from app.modules.library.models import AgentProposal
from app.shared.errors import CodedHTTPException


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
) -> AgentOperation:
    """自动档直执行写 operation（工单 02，spec 决策 10/11）。

    成功：调用方执行事务内与业务结果同事务提交（SUCCEEDED＋result 回填＋
    执行前快照，工单 03）；失败：业务事务已回滚（＝未发生），调用方在独立
    小事务再调本函数落 FAILED＋稳定错误码（提案 _mark_failed 先例）。
    authorization 是直执行的授权依据（档位＋触发指令摘录＋消息引用），单步
    无 run 时为本行授权事实的唯一载体（ADR-0026）。
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
        attempts=1,
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


def _json_dict(raw: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        value: object = json.loads(raw)
    except ValueError:
        return None
    return cast("dict[str, Any]", value) if isinstance(value, dict) else None


def _operation_out(operation: AgentOperation) -> dict[str, Any]:
    """行→输出投影（JSON 列解析为 dict，坏值降级为空/None 不炸查询）。"""
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
        "result": _json_dict(operation.result_json),
        "error_code": operation.error_code,
        "undo_of": operation.undo_of,
        "undone_by": operation.undone_by,
        "created_at": operation.created_at,
        "updated_at": operation.updated_at,
        "finished_at": operation.finished_at,
    }


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
        operations = list(
            (
                await session.scalars(
                    select(AgentOperation)
                    .where(AgentOperation.run_id == run_id)
                    .order_by(AgentOperation.created_at.asc())
                )
            ).all()
        )
        return {**_run_out(run), "operations": [_operation_out(op) for op in operations]}

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
        return [_operation_out(op) for op in operations]

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
            await session.delete(run)

    @staticmethod
    async def purge_finished(session: AsyncSession) -> dict[str, int]:
        """批量清理已结束任务的历史（spec 决策 21）：终态 runs（级联其
        operations）＋终态单步 operations；活动项不触碰；提案永不删。"""
        terminal_run_statuses = [status.value for status in RUN_TERMINAL_STATUSES]
        terminal_op_statuses = [status.value for status in OPERATION_TERMINAL_STATUSES]
        async with session.begin():
            cascading = cast(
                int,
                await session.scalar(
                    select(func.count())
                    .select_from(AgentOperation)
                    .where(
                        AgentOperation.run_id.in_(
                            select(AgentRun.id).where(AgentRun.status.in_(terminal_run_statuses))
                        )
                    )
                ),
            )
            runs_claimed = await session.execute(
                delete(AgentRun).where(AgentRun.status.in_(terminal_run_statuses))
            )
            steps_claimed = await session.execute(
                delete(AgentOperation).where(
                    AgentOperation.run_id.is_(None),
                    AgentOperation.status.in_(terminal_op_statuses),
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
