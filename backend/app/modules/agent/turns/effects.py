"""副作用幂等执行框架（切换会话不中断任务，票 02，规格 §9）。

工具调用身份来自已持久化的调用计划：稳定执行归属（turn_id）+ checkpoint
namespace + 逻辑调用身份（模型 tool_call id，图续跑时同一 pending 调用稳定）；
attempt 不进入来源键。一次逻辑调用产生多项副作用时按 effect_index 逐项记录。

接入点（覆盖全部有副作用的工具，不以 Operation 工具名单代替）：
- ``operations/registry.submit_operation``：Operation 写入 / 直执行 / Job 投递
  （generate_plan_draft、library_item_ingest、record_move_course 等）；
- ``tools/propose_memory``：记忆提案；
- ``tools/propose_ingest``：研究入库提案（多结果逐项）；
- ``runs/plans.submit_batch_plan``：批量计划 / Run 创建；
- ``runs/undo.submit_undo``：撤销（补偿）。

两段式契约（适配既有自管事务的提交入口）：
1. ``prepare_effect``：副作用执行前的原子登记——来源键先落 PLANNED（计划
   持久化后才允许副作用执行）；已成功项返回原持久结果（恢复复用，不再写
   业务）；同身份参数指纹变化拒绝执行；多结果工具逐项调用（effect_index
   区分、args 含序号区分）；
2. ``complete_effect``：业务提交事务内调用——效果行翻 SUCCEEDED 并记录
   可恢复结构化结果，与业务写入同事务提交（业务提交后、效果行保存前的
   崩溃窗口不存在：重放见 PLANNED 即重新执行，业务未提交故无重复）。

取消与执行身份的原子校验沿用各业务事务内的 ``runtime.turn_write_allowed``
（业务提交处兜底，规格 §2/§14）。
"""

import json
from contextvars import ContextVar, Token
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.modules.agent.runtime import AgentRuntimeContext
from app.modules.agent.turns.models import ChatTurnToolEffect


class EffectStatus(StrEnum):
    """效果行状态：PLANNED＝计划已固定（副作用未执行）；SUCCEEDED＝业务与
    回执已同事务提交（恢复复用原结果）；FAILED＝保留位（当前失败不落效果行，
    重放重新执行——不把失败当成功跳过）。"""

    PLANNED = "PLANNED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class EffectExecutionError(Exception):
    """幂等执行无法继续（取消已受理 / 参数指纹冲突）；载荷由工具转述给模型。"""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ToolCallIdentity:
    """当前工具调用的稳定逻辑身份（wrap_tool_call 中间件绑定）。"""

    namespace: str
    logical_call_id: str


@dataclass(frozen=True)
class EffectPreparation:
    """副作用执行前置结果；replay 非 None＝命中已成功项，直接复用。"""

    replay: dict[str, Any] | None


_tool_call_identity: ContextVar[ToolCallIdentity | None] = ContextVar(
    "tool_call_identity", default=None
)


def bind_tool_call_identity(identity: ToolCallIdentity) -> Token[ToolCallIdentity | None]:
    return _tool_call_identity.set(identity)


def reset_tool_call_identity(token: Token[ToolCallIdentity | None]) -> None:
    _tool_call_identity.reset(token)


def current_tool_call_identity() -> ToolCallIdentity | None:
    return _tool_call_identity.get()


def effect_args_fingerprint(args: object) -> str:
    """参数规范化指纹：JSON 键序稳定后哈希；不可序列化值先字符串化。"""
    normalized = json.dumps(
        args, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    )
    return sha256(normalized.encode("utf-8")).hexdigest()


def _effect_row_id(turn_id: str, namespace: str, logical_call_id: str, effect_index: int) -> str:
    digest = sha256(f"{turn_id}|{namespace}|{logical_call_id}|{effect_index}".encode()).hexdigest()
    return f"{digest[:12]}-{effect_index}"


def _parse_result(row: ChatTurnToolEffect) -> dict[str, Any] | None:
    if row.result_json is None:
        return None
    try:
        loaded: object = json.loads(row.result_json)
    except ValueError:
        return None
    if not isinstance(loaded, dict):
        return None
    return cast(dict[str, Any], loaded)


async def _load_effect_row(
    session: AsyncSession,
    *,
    turn_id: str,
    identity: ToolCallIdentity,
    effect_index: int,
    fingerprint: str,
) -> ChatTurnToolEffect | None:
    """读效果行并核对参数指纹（同身份参数变化拒绝执行）。"""
    row = await session.scalar(
        select(ChatTurnToolEffect).where(
            ChatTurnToolEffect.turn_id == turn_id,
            ChatTurnToolEffect.namespace == identity.namespace,
            ChatTurnToolEffect.logical_call_id == identity.logical_call_id,
            ChatTurnToolEffect.effect_index == effect_index,
        )
    )
    if row is not None and row.args_fingerprint != fingerprint:
        raise EffectExecutionError(
            code="EFFECT_FINGERPRINT_CONFLICT",
            detail="同一工具调用的参数与上次执行不一致，已拒绝执行",
        )
    return row


async def prepare_effect(
    runtime: AgentRuntimeContext,
    tool_name: str,
    args: object,
    *,
    effect_index: int = 0,
) -> EffectPreparation | None:
    """副作用执行前置：来源键先落 PLANNED；命中已成功项返回原持久结果。

    返回 None＝非轮次上下文（不幂等，调用方直接执行）；replay 非 None＝恢复
    复用（不再写业务）。EffectExecutionError＝指纹冲突。args 即指纹源：多结果
    工具逐项调用时把逐项参数（含序号区分）作为 args 传入，complete 侧同源。
    """
    identity = current_tool_call_identity()
    if identity is None or runtime.turn_id is None:
        return None
    fingerprint = effect_args_fingerprint(args)
    async with runtime.session_factory() as session, session.begin():
        row = await _load_effect_row(
            session,
            turn_id=runtime.turn_id,
            identity=identity,
            effect_index=effect_index,
            fingerprint=fingerprint,
        )
        if row is not None and row.status == EffectStatus.SUCCEEDED:
            return EffectPreparation(replay=_parse_result(row) or {})
        if row is None:
            session.add(
                ChatTurnToolEffect(
                    id=_effect_row_id(
                        runtime.turn_id, identity.namespace, identity.logical_call_id, effect_index
                    ),
                    turn_id=runtime.turn_id,
                    namespace=identity.namespace,
                    logical_call_id=identity.logical_call_id,
                    effect_index=effect_index,
                    tool_name=tool_name,
                    args_fingerprint=fingerprint,
                    status=EffectStatus.PLANNED,
                )
            )
    return EffectPreparation(replay=None)


async def complete_effect(
    session: AsyncSession,
    runtime: AgentRuntimeContext,
    tool_name: str,
    args: object,
    *,
    effect_index: int = 0,
    result: dict[str, Any],
) -> None:
    """业务提交事务内收口：效果行翻 SUCCEEDED 并记录可恢复结果（同事务提交）。

    非轮次上下文（无绑定身份或 turn_id）零操作。调用点必须在已通过
    turn_write_allowed 的业务事务内；args 与 prepare_effect 同源（指纹一致）。
    """
    identity = current_tool_call_identity()
    if identity is None or runtime.turn_id is None:
        return
    fingerprint = effect_args_fingerprint(args)
    row = await _load_effect_row(
        session,
        turn_id=runtime.turn_id,
        identity=identity,
        effect_index=effect_index,
        fingerprint=fingerprint,
    )
    now = utcnow()
    if row is None:
        row = ChatTurnToolEffect(
            id=_effect_row_id(
                runtime.turn_id, identity.namespace, identity.logical_call_id, effect_index
            ),
            turn_id=runtime.turn_id,
            namespace=identity.namespace,
            logical_call_id=identity.logical_call_id,
            effect_index=effect_index,
            tool_name=tool_name,
            args_fingerprint=fingerprint,
            status=EffectStatus.SUCCEEDED,
            result_json=json.dumps(result, ensure_ascii=False, separators=(",", ":")),
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        return
    row.status = EffectStatus.SUCCEEDED
    row.result_json = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    row.updated_at = now


async def count_turn_effects(
    session: AsyncSession,
    turn_id: str,
    *,
    tool_names: frozenset[str] | set[str] | None = None,
) -> int:
    """轮次已登记副作用数：恢复时重建 operations_created 预算（规格 §10）。

    tool_names 给定时只数名单内效果行＝操作预算口径（与递增
    operations_created 的提交入口效果行对齐）；None＝全部副作用行
    （checkpoint 缺失分流的「已登记副作用」口径，含记忆与入库逐项）。
    """
    stmt = (
        select(func.count())
        .select_from(ChatTurnToolEffect)
        .where(ChatTurnToolEffect.turn_id == turn_id)
    )
    if tool_names is not None:
        stmt = stmt.where(ChatTurnToolEffect.tool_name.in_(tool_names))
    count = await session.scalar(stmt)
    return int(count or 0)


__all__ = [
    "EffectExecutionError",
    "EffectPreparation",
    "EffectStatus",
    "ToolCallIdentity",
    "bind_tool_call_identity",
    "complete_effect",
    "count_turn_effects",
    "current_tool_call_identity",
    "effect_args_fingerprint",
    "prepare_effect",
    "reset_tool_call_identity",
]
