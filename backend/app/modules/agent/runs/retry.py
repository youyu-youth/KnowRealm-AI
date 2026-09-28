"""单步失败操作的手动重试（通用 Agent 第二阶段工单 06，spec 决策 20）。

手动重试沿用原 operation 身份（attempts 递增、不新建行——用户明确要求重复
执行才新建 operation）：直执行路径落下的 FAILED 单步行在此同步重执行；确认
路径失败不落 operation 行（提案框架 FAILED 可重试）；run 内操作走既有
runs/{id}/operations/{op}/retry 端点（重试会重开推进）。

执行前快照重验（service.operation_snapshot_stale，与推进 worker 同口径）：
目标已变 → FAILED＋OPERATION_SNAPSHOT_STALE（旧批准失效，需重新发起操作，
不覆盖用户后续修改）。失败尝试经 append_attempt 留痕 attempts_json。
"""

import json
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.agent.operations.registry import (
    get_operation,
    run_operation_applier,
)
from app.modules.agent.runs.models import AgentOperation
from app.modules.agent.runs.schemas import OperationStatus
from app.modules.agent.runs.service import (
    append_attempt,
    operation_out,
    operation_snapshot_stale,
)
from app.shared.errors import CodedHTTPException


def _operation_params(payload_json: str) -> dict[str, Any]:
    """操作载荷 JSON → dict（坏值＝空 dict，由注册项 schema 校验兜底）。"""
    try:
        value: object = json.loads(payload_json)
    except ValueError:
        return {}
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


async def retry_standalone_operation(
    session: AsyncSession, operation_id: str | UUID
) -> dict[str, Any]:
    """单步（直执行）失败操作手动重试：沿用原身份同步重执行（attempts 递增）。

    返回重试后的 operation 投影（成功＝SUCCEEDED＋新 result；失败＝FAILED＋
    稳定错误码，如实呈现重试结局）。run 内操作与非失败态拒绝（稳定错误码）。
    """
    operation_id = str(operation_id)
    async with session:
        initial = await session.get(AgentOperation, operation_id)
        if initial is None:
            raise CodedHTTPException(
                code="AGENT_OPERATION_NOT_FOUND", status_code=404, detail="操作不存在"
            )
        if initial.run_id is not None:
            raise CodedHTTPException(
                code="OPERATION_NOT_RETRYABLE",
                status_code=409,
                detail="任务中的操作请从任务面板重试（重试会重开任务推进）",
            )
        if initial.status != OperationStatus.FAILED.value:
            raise CodedHTTPException(
                code="OPERATION_NOT_RETRYABLE",
                status_code=409,
                detail="仅失败的操作可以重试",
            )
        action = initial.action
    spec = get_operation(action)
    if spec is None:
        raise CodedHTTPException(
            code="OPERATION_NOT_REGISTERED",
            status_code=409,
            detail="操作类型未注册",
        )
    try:
        async with session.begin():
            operation = await session.get(AgentOperation, operation_id)
            assert operation is not None
            if await operation_snapshot_stale(
                session, spec, operation, _operation_params(operation.payload_json)
            ):
                raise CodedHTTPException(
                    code="OPERATION_SNAPSHOT_STALE",
                    status_code=409,
                    detail="目标已发生变化，请重新发起操作",
                )
            result = await run_operation_applier(session, spec, operation.payload_json)
            now = utcnow()
            operation.status = OperationStatus.SUCCEEDED.value
            operation.result_json = json.dumps(
                result.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")
            )
            operation.error_code = None
            operation.attempts += 1
            operation.updated_at = now
            operation.finished_at = now
    except CodedHTTPException as exc:
        # 业务写已回滚（＝未发生，不会重复成功部分）；独立小事务落 FAILED＋
        # 本次尝试错误码（attempts 递增、attempts_json 留痕）。
        failed: AgentOperation | None = None
        async with session.begin():
            fresh = await session.get(AgentOperation, operation_id)
            if fresh is not None and fresh.status == OperationStatus.FAILED.value:
                now = utcnow()
                fresh.attempts += 1
                fresh.error_code = exc.code
                fresh.updated_at = now
                fresh.finished_at = now
                append_attempt(fresh, exc.code, now=now)
                failed = fresh
        if failed is None:
            # 并发下他方已改动该行（非 FAILED 态）：如实返回当前投影。
            fresh2 = await session.get(AgentOperation, operation_id)
            assert fresh2 is not None
            return operation_out(fresh2)
        return operation_out(failed)
    return operation_out(operation)
