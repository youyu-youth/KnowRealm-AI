"""授权档位端点与运行时覆盖（通用 Agent 第二阶段工单 02，spec 决策 9/22）。

三档授权的持久侧入口：全局默认档读写 settings.json 偏离项（默认档不写键，
learner_memory 外发开关先例）；全局与会话切换均写 agent_activity 审计行
（from / to / 作用域 / 会话 / 时间）。会话档位本身是前端按会话内存
（web_search 开关先例），重启回落全局默认——后端只记审计不持久会话档。

会话覆盖的进程内注册表（spec 用户故事 6）：流式生成中途降档必须约束本轮
后续工具提交——档位在受理时随 runtime 固化，中途切档经注册表传达；读取取
「覆盖档与本轮起点档中更严格者」（降档即时收紧、升档自下一轮生效：下一轮
请求体携带新档，两端一致）。sidecar 单进程内状态（ChatStreamRegistry 先例），
重启清空＝回落全局默认（安全方向）。

落位 agent 域根而非 runs 子包：本端点消费 settings 配置域（message_service
先例），runs 子包维持「执行事实存储零领域 import」的 AST 防线口径。
"""

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from loguru import logger
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.agent.runs.models import AgentActivity
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

# 档位严格度偏序（REQUEST_APPROVAL 最严）：运行中回合取更严格者。
_AUTH_MODE_STRICTNESS = {
    AuthMode.REQUEST_APPROVAL: 0,
    AuthMode.AUTO_APPROVE: 1,
    AuthMode.FULL_ACCESS: 2,
}

# 会话授权覆盖注册表（session_id → 覆盖档）：会话切档端点写入，操作提交
# 路径读取；进程内状态随重启清空。
_SESSION_AUTH_OVERRIDES: dict[str, AuthMode] = {}


def set_session_auth_override(session_id: str, mode: AuthMode) -> None:
    """记录会话当前生效的授权覆盖（会话切档端点在审计落定后调用）。"""
    _SESSION_AUTH_OVERRIDES[session_id] = mode


def clear_session_auth_override(session_id: str) -> None:
    """清除会话覆盖（测试隔离用）。"""
    _SESSION_AUTH_OVERRIDES.pop(session_id, None)


def effective_session_auth_mode(session_id: str, turn_mode: AuthMode) -> AuthMode:
    """生效档：覆盖档与传入档取更严格者。

    无覆盖（未切过档 / 重启后）＝传入档，与每轮请求携带语义一致；中途降档
    即时收紧（用户故事 6「后续动作重新检查授权」）；中途升档不放宽本轮
    （与「升档不自动执行既有动作序列」同一安全精神），下一轮请求携带新档后
    生效。

    两个读取方同源：工具提交路径传入本轮起点档（registry.submit_operation /
    plans.submit_batch_plan）；推进 worker 每步授权重检传入 Run 固化档
    （worker._authorized）——同进程降档同样即时约束运行中任务的后续步骤。
    """
    override = _SESSION_AUTH_OVERRIDES.get(session_id)
    if override is None:
        return turn_mode
    return min(
        (override, turn_mode),
        key=lambda mode: _AUTH_MODE_STRICTNESS[mode],
    )


def clamp_resume_auth_mode(
    session_id: str, turn_mode: AuthMode, current_default: AuthMode
) -> AuthMode:
    """恢复轮次（attempt>1）的注入档（ChatTurn 规格 §11/T13）。

    会话覆盖仍在（同进程 resume，临时授权意图未消失）＝原固化档照用，
    中途升降档约束交提交点 effective 实时取严格者（既有口径）；覆盖缺席
    （重启清空 / 从未切档）＝会话临时高权限依据已消失，与当前全局默认
    取更严格者——原授权是上限、全局档位恢复按当前配置重验且不升档，
    高权限写回落提案确认卡等显式重新授权。
    """
    if _SESSION_AUTH_OVERRIDES.get(session_id) is not None:
        return turn_mode
    return min(
        (turn_mode, current_default),
        key=lambda mode: _AUTH_MODE_STRICTNESS[mode],
    )


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


# ---------------------------------------------------------------------------
# 切档编排（service 边界，fastapi.md 薄路由：事务与领域约束不上路由函数）


async def switch_global_auth_mode(
    data_dir: Path,
    session_factory: async_sessionmaker[AsyncSession],
    to_mode: AuthMode,
) -> AuthMode:
    """全局切档编排：读当前档（审计权威 from）→ 写审计行 → 改 settings 偏离项。

    两步终究非原子，顺序「审计先行」＋settings 写失败补偿删审计：
    - 审计失败（DB 故障）＝档未变，客户端重试即可（不反向：先改档后审计
      失败会产生档已变而审计链缺行的口径裂缝）；
    - settings 写失败＝补偿删除刚写的审计行后整体抛错，不留「未实际生效
      的切档审计」（补偿再失败仅记日志，残留行语义＝一次未完成的切换）。
    只影响之后的新会话与未携带覆盖的请求。
    """
    from_mode = AuthMode(await asyncio.to_thread(agent_default_auth_mode, data_dir))
    async with session_factory() as session, session.begin():
        activity = await record_auth_mode_switch(
            session,
            from_mode=from_mode.value,
            to_mode=to_mode.value,
            scope=ActivityScope.GLOBAL,
        )
    try:
        await asyncio.to_thread(set_agent_default_auth_mode, data_dir, to_mode.value)
    except Exception:
        try:
            async with session_factory() as session, session.begin():
                await session.execute(delete(AgentActivity).where(AgentActivity.id == activity.id))
        except Exception:
            logger.error("auth_mode_switch_compensation_failed", activity_id=activity.id)
        raise
    return to_mode


async def record_session_switch_audit(
    session: AsyncSession,
    *,
    session_id: str,
    from_mode: str,
    to_mode: str,
) -> None:
    """会话切档留痕：会话存在校验＋审计行同事务，随后同步运行时覆盖。

    会话不存在拒绝写审计（避免悬挂溯源）；from 由客户端按其看到的当前
    生效档上报（会话覆盖 ?? 全局默认，后端无从得知前端内存态）。
    """
    # 校验与写入同一事务（Session autobegin：先 SELECT 再显式 begin 会撞
    # "transaction already begun"，confirm 先例是 begin 内统一做）。
    async with session.begin():
        chat = await ChatSessionService.get(session, session_id)
        if chat is None:
            raise CodedHTTPException(
                code="CHAT_SESSION_NOT_FOUND", status_code=404, detail="对话不存在或已删除"
            )
        await record_auth_mode_switch(
            session,
            from_mode=from_mode,
            to_mode=to_mode,
            scope=ActivityScope.SESSION,
            session_id=session_id,
        )
    # 审计落定后同步运行时覆盖：在途流的后续工具提交立即按新档检查授权
    # （降档即时收紧；升档经 effective 读取自下一轮放宽）。
    set_session_auth_override(session_id, AuthMode(to_mode))


@router.get("/auth-mode", response_model=AgentAuthModeOut)
async def get_auth_mode(request: Request) -> AgentAuthModeOut:
    """当前全局默认授权档（设置页「Agent 自动化」分区与新会话缺省档）。"""
    mode = await asyncio.to_thread(agent_default_auth_mode, request.app.state.data_dir)
    return AgentAuthModeOut(auth_mode=AuthMode(mode))


@router.put("/auth-mode", response_model=AgentAuthModeOut)
async def put_auth_mode(body: AgentAuthModeSwitch, request: Request) -> AgentAuthModeOut:
    """切换全局默认档（编排见 switch_global_auth_mode，只影响新会话与未携带覆盖的请求）。"""
    mode = await switch_global_auth_mode(
        request.app.state.data_dir, request.app.state.session_factory, body.to_mode
    )
    return AgentAuthModeOut(auth_mode=mode)


@router.post("/auth-mode/sessions", status_code=204)
async def post_session_auth_mode_switch(
    body: AgentAuthModeSessionSwitch,
    session: AsyncSession = Depends(get_db),
) -> None:
    """会话内临时切档的审计行（会话档位在前端内存，本端点只留痕）。"""
    await record_session_switch_audit(
        session,
        session_id=body.session_id,
        from_mode=body.from_mode.value,
        to_mode=body.to_mode.value,
    )
