"""操作历史查询与清理端点（spec 决策 21；设置页「操作历史」分区消费）。

Run 推进与 activity 写入随 02/05 票接入；本票阶段 runs / activity 恒空态，
operations 由第一阶段两类动作确认执行回写。
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
from app.modules.agent.runs.service import RunHistoryService
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
