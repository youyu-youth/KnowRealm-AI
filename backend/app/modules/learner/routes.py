"""learner 域路由（工单 06）：学习画像「AI 记忆」读写与长期记忆外发开关。

契约 §2.5：GET/PUT preferences、DELETE observed/{key}、PUT memory-outbound。
模块导入即注册 MEMORY 提案应用器（先例：library/organize）——提案确认后由
learner 域在调用方事务内写入 learner_preferences。
"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.learner.schemas import (
    LearnerPreferenceOut,
    LearnerPreferenceUpdate,
    MemoryOutboundOut,
    MemoryOutboundUpdate,
)
from app.modules.learner.service import LearnerProfileService, apply_memory_proposal
from app.modules.library.proposals import register_applier
from app.modules.library.schemas import ProposalType
from app.shared.deps import get_db, require_launch_token
from app.shared.schemas import ErrorResponse

learner_router = APIRouter(
    prefix="/api/learner",
    tags=["learner"],
    dependencies=[Depends(require_launch_token)],
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)

register_applier(ProposalType.MEMORY, apply_memory_proposal)


@learner_router.get("/preferences", response_model=LearnerPreferenceOut)
async def get_learner_preferences(
    request: Request, session: Annotated[AsyncSession, Depends(get_db)]
) -> LearnerPreferenceOut:
    """学习画像「AI 记忆」单例视图（惰性建行）。"""
    return await LearnerProfileService.get_preferences(session, request.app.state.data_dir)


@learner_router.put("/preferences", response_model=LearnerPreferenceOut)
async def put_learner_preferences(
    request: Request,
    body: LearnerPreferenceUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> LearnerPreferenceOut:
    """编辑显式偏好（全量替换、立即生效）；观察偏好不受影响。"""
    return await LearnerProfileService.update_preferences(session, body, request.app.state.data_dir)


@learner_router.delete("/preferences/observed/{key}", status_code=204)
async def delete_observed_preference(
    key: str, session: Annotated[AsyncSession, Depends(get_db)]
) -> Response:
    """删除单条观察偏好（按 entries 键）；未确认的观察结果随删即失。"""
    await LearnerProfileService.delete_observed(session, key)
    return Response(status_code=204)  # type: ignore[return-value]


@learner_router.put("/memory-outbound", response_model=MemoryOutboundOut)
async def put_memory_outbound(request: Request, body: MemoryOutboundUpdate) -> MemoryOutboundOut:
    """长期记忆外发开关：关闭=记忆保留本地、不注入发给 LLM 的上下文。"""
    data_dir = request.app.state.data_dir
    return await asyncio.to_thread(
        LearnerProfileService.set_memory_outbound, data_dir, body.enabled
    )
