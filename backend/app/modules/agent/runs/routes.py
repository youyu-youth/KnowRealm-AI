"""操作历史查询与清理端点（spec 决策 21；设置页「操作历史」分区消费）
＋ Run 唤醒与取消端点（工单 05：继续指令 / 失败项重试 / 取消，spec 决策 7）。

唤醒仅由显式动作触发并经原子抢占；推进由 AGENT_RUN 触发 job 内的 worker 完成，
端点只改 Run 状态并投递触发（不承载任务状态，spec 决策 6）。
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.runs.schemas import (
    ActivityListQuery,
    AgentActivityOut,
    AgentOperationOut,
    AgentRunDetailOut,
    AgentRunOut,
    OperationListQuery,
    PurgeResultOut,
    RunListQuery,
)
from app.modules.agent.runs.service import RunControlService, RunHistoryService
from app.shared.deps import get_db, require_launch_token
from app.shared.schemas import ErrorResponse

router = APIRouter(
    prefix="/api/agent",
    tags=["agent-runs"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)


@router.get("/runs", response_model=list[AgentRunOut])
async def list_runs(
    query: RunListQuery = Depends(),
    session: AsyncSession = Depends(get_db),
) -> list[AgentRunOut]:
    return [
        AgentRunOut.model_validate(run)
        for run in await RunHistoryService.list_runs(
            session,
            status=query.status.value if query.status is not None else None,
            session_id=query.session_id,
            limit=query.limit,
            offset=query.offset,
        )
    ]


@router.get("/runs/{run_id}", response_model=AgentRunDetailOut)
async def get_run(
    run_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> AgentRunDetailOut:
    return AgentRunDetailOut.model_validate(
        await RunHistoryService.get_run_detail(session, str(run_id))
    )


@router.delete("/runs/{run_id}", status_code=204)
async def delete_run_history(
    run_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> None:
    await RunHistoryService.delete_run_history(session, str(run_id))


@router.post("/runs/purge-finished", response_model=PurgeResultOut)
async def purge_finished(session: AsyncSession = Depends(get_db)) -> PurgeResultOut:
    """批量清理已结束任务的历史（终态 runs＋终态单步 operations）；提案永不删。"""
    return PurgeResultOut.model_validate(await RunHistoryService.purge_finished(session))


@router.post("/runs/{run_id}/cancel", response_model=AgentRunOut)
async def cancel_run(
    run_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> AgentRunOut:
    """取消任务（显式动作）：已结束拒绝；等待态就地落 CANCELLED，运行态由推进
    每步检查后收尾——取消后不再新增动作、已提交结果保留（不冒充撤销）。"""
    return AgentRunOut.model_validate(await RunControlService.cancel_run(session, str(run_id)))


@router.post("/runs/{run_id}/resume", response_model=AgentRunOut)
async def resume_run(
    run_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> AgentRunOut:
    """继续指令（显式唤醒）：仅等待态可继续，原子抢占 WAITING_USER → RUNNING
    并重投触发；不自动重试失败项（重试是独立显式动作）。"""
    return AgentRunOut.model_validate(await RunControlService.resume_run(session, str(run_id)))


@router.post("/runs/{run_id}/operations/{operation_id}/retry", response_model=AgentRunOut)
async def retry_run_operation(
    run_id: UUID,
    operation_id: UUID,
    session: AsyncSession = Depends(get_db),
) -> AgentRunOut:
    """失败 / 跳过项重试（沿用原 operation 身份，attempts 递增）：依赖该项而
    跳过的后续步骤一并恢复待执行，并唤醒任务继续推进。"""
    return AgentRunOut.model_validate(
        await RunControlService.retry_operation(
            session, run_id=str(run_id), operation_id=str(operation_id)
        )
    )


@router.get("/operations", response_model=list[AgentOperationOut])
async def list_operations(
    query: OperationListQuery = Depends(),
    session: AsyncSession = Depends(get_db),
) -> list[AgentOperationOut]:
    return [
        AgentOperationOut.model_validate(op)
        for op in await RunHistoryService.list_operations(
            session,
            status=query.status.value if query.status is not None else None,
            session_id=query.session_id,
            limit=query.limit,
            offset=query.offset,
        )
    ]


@router.get("/activity", response_model=list[AgentActivityOut])
async def list_activity(
    query: ActivityListQuery = Depends(),
    session: AsyncSession = Depends(get_db),
) -> list[AgentActivityOut]:
    return [
        AgentActivityOut.model_validate(activity)
        for activity in await RunHistoryService.list_activity(
            session, limit=query.limit, offset=query.offset
        )
    ]
