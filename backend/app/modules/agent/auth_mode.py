"""授权档位端点（通用 Agent 第二阶段工单 02，spec 决策 9/22）。

三档授权的持久侧入口：全局默认档读写 settings.json 偏离项（默认档不写键，
learner_memory 外发开关先例）；全局与会话切换均写 agent_activity 审计行
（from / to / 作用域 / 会话 / 时间）。会话档位本身是前端按会话内存
（web_search 开关先例），重启回落全局默认——后端只记审计不存会话档。

落位 agent 域根而非 runs 子包：本端点消费 settings 配置域（message_service
先例），runs 子包维持「执行事实存储零领域 import」的 AST 防线口径。
"""

import asyncio

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.runs.schemas import (
    ActivityScope,
    AgentAuthModeOut,
    AgentAuthModeSessionSwitch,
    AgentAuthModeSwitch,
    AuthMode,
)
from app.modules.agent.runs.service import record_auth_mode_switch
from app.modules.agent.session_service import ChatSessionService
from app.modules.settings.config import (
    agent_default_auth_mode,
    set_agent_default_auth_mode,
)
from app.shared.deps import get_db, require_launch_token
from app.shared.errors import CodedHTTPException
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


@router.get("/auth-mode", response_model=AgentAuthModeOut)
async def get_auth_mode(request: Request) -> AgentAuthModeOut:
    """当前全局默认授权档（设置页「Agent 自动化」分区与新会话缺省档）。"""
    mode = await asyncio.to_thread(agent_default_auth_mode, request.app.state.data_dir)
    return AgentAuthModeOut(auth_mode=AuthMode(mode))


@router.put("/auth-mode", response_model=AgentAuthModeOut)
async def put_auth_mode(body: AgentAuthModeSwitch, request: Request) -> AgentAuthModeOut:
    """切换全局默认档：先写审计行、后改 settings.json 偏离项。

    两步终究非原子，顺序选「审计先行」让失败方向落在安全侧——审计失败
    （DB 故障）时档未变、客户端重试即可；不反向（先改档后审计失败会产生
    档已变而审计链缺行的口径裂缝）。from 后端自读 settings.json 权威值。
    只影响之后的新会话与未携带覆盖的请求。
    """
    from_mode = AuthMode(
        await asyncio.to_thread(agent_default_auth_mode, request.app.state.data_dir)
    )
    async with request.app.state.session_factory() as session, session.begin():
        await record_auth_mode_switch(
            session,
            from_mode=from_mode.value,
            to_mode=body.to_mode.value,
            scope=ActivityScope.GLOBAL,
        )
    await asyncio.to_thread(
        set_agent_default_auth_mode, request.app.state.data_dir, body.to_mode.value
    )
    return AgentAuthModeOut(auth_mode=body.to_mode)


@router.post("/auth-mode/sessions", status_code=204)
async def post_session_auth_mode_switch(
    body: AgentAuthModeSessionSwitch,
    session: AsyncSession = Depends(get_db),
) -> None:
    """会话内临时切档的审计行（会话档位在前端内存，本端点只留痕）。

    会话不存在拒绝写审计（避免悬挂溯源）；from 由客户端按其看到的当前
    生效档上报（会话覆盖 ?? 全局默认，后端无从得知前端内存态）。
    """
    # 校验与写入同一事务（Session autobegin：先 SELECT 再显式 begin 会撞
    # "transaction already begun"，confirm 先例是 begin 内统一做）。
    async with session.begin():
        chat = await ChatSessionService.get(session, body.session_id)
        if chat is None:
            raise CodedHTTPException(
                code="CHAT_SESSION_NOT_FOUND", status_code=404, detail="对话不存在或已删除"
            )
        await record_auth_mode_switch(
            session,
            from_mode=body.from_mode.value,
            to_mode=body.to_mode.value,
            scope=ActivityScope.SESSION,
            session_id=body.session_id,
        )
