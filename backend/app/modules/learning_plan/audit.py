"""页面直改计划项的 Operation 审计钩子（通用 Agent 第三阶段工单 03）。

spec 用户故事 14：就地编辑「改动立即生效并有操作审计」——页面路径不经提案
档位（按钮点击即用户授权，USER_UNDO 先例），但每次改动与 Agent 路径一样
落 agent_operations 行（action / 目标 / 载荷 / 结果 / trigger=USER_MANUAL）。

方向约束（fastapi.md：agent 是下游模块）：learning_plan 路由不能直接 import
agent 执行机制，钩子由 agent 侧注册反转（register_applier 同模式）；未注册
（无 agent 装配的隔离单元导入）时静默跳过，不影响领域写入本身。
"""

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

# (session, action, target, payload, result) → 审计行写入（调用方事务内）。
type ManualAuditRecorder = Callable[
    [AsyncSession, str, tuple[str, str], dict[str, Any], dict[str, Any]],
    Awaitable[None],
]

_recorder: ManualAuditRecorder | None = None


def register_manual_audit_recorder(recorder: ManualAuditRecorder) -> None:
    """agent 侧注册审计写入器（应用装配时执行一次）。"""
    global _recorder
    _recorder = recorder


async def record_manual_audit(
    session: AsyncSession,
    *,
    action: str,
    target: tuple[str, str],
    payload: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """页面直改的审计入口（调用方事务内；未注册时零行为）。"""
    if _recorder is not None:
        await _recorder(session, action, target, payload, result)
