"""先原子准入，再执行；输出计量在 handler 返回框架前提交。"""

import json
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from inspect import signature
from typing import ParamSpec, cast
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.agent.budget.models import BudgetCall, BudgetOutput
from app.modules.agent.budget.policy import (
    MAX_TOOL_CALLS_PER_TURN,
    POLICIES,
    POLICY_VERSION,
    ToolCallBudget,
    budget_snapshot,
)
from app.modules.agent.runtime import AgentRuntimeContext, current_agent_runtime
from app.modules.agent.turns.effects import current_tool_call_identity, effect_args_fingerprint
from app.modules.agent.turns.models import ChatTurn

P = ParamSpec("P")


@dataclass
class _Consumption:
    tool_name: str
    call_id: str | None
    output_id: str
    chars: int = 0


_consumption: ContextVar[_Consumption | None] = ContextVar("tool_budget", default=None)


def mark_output(payload: str) -> None:
    """原工具计量分支标记实际载荷；持久提交由统一执行边界完成。"""
    consumption = _consumption.get()
    if consumption is not None:
        consumption.chars = len(payload)


async def totals(session: AsyncSession, turn_id: str) -> tuple[int, int]:
    calls = await session.scalar(
        select(func.count()).select_from(BudgetCall).where(BudgetCall.turn_id == turn_id)
    )
    chars = await session.scalar(
        select(func.coalesce(func.sum(BudgetOutput.chars_fed), 0))
        .join(BudgetCall, BudgetOutput.call_id == BudgetCall.id)
        .where(BudgetCall.turn_id == turn_id)
    )
    return int(calls or 0), int(chars or 0)


async def restore(
    session_factory: async_sessionmaker[AsyncSession], turn_id: str
) -> tuple[int, int]:
    async with session_factory() as session:
        return await totals(session, turn_id)


async def cleanup(session: AsyncSession, turn: ChatTurn) -> None:
    from app.modules.agent.turns.schemas import ChatTurnStatus

    if ChatTurnStatus(turn.status).is_terminal:
        await session.execute(delete(BudgetCall).where(BudgetCall.turn_id == turn.id))


class BudgetRejected(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


async def admit(runtime: AgentRuntimeContext, tool_name: str, args: object) -> str | None:
    identity = current_tool_call_identity()
    if runtime.execution_id is not None and runtime.turn_id is None:
        raise BudgetRejected("AGENT_CONTEXT_UNBOUND")
    if runtime.turn_id is None:
        if runtime.budget.calls_used >= MAX_TOOL_CALLS_PER_TURN:
            raise BudgetRejected("TOOL_CALL_LIMIT")
        runtime.budget.calls_used += 1
        return None
    if identity is None:
        raise BudgetRejected("AGENT_CONTEXT_UNBOUND")
    if (
        runtime.execution_id is not None
        and identity.namespace != f"agent-delegation-{runtime.execution_id}"
    ):
        raise BudgetRejected("AGENT_CONTEXT_UNBOUND")
    fingerprint = effect_args_fingerprint(args)
    async with runtime.session_factory() as session, session.begin():
        # 条件 UPDATE 先取得写锁：身份、取消、最后名额裁决与消费同事务。
        if not await runtime.turn_write_allowed(session):
            raise BudgetRejected("CHAT_TURN_CANCELLED")
        turn = await session.get(ChatTurn, runtime.turn_id)
        assert turn is not None
        if json.loads(turn.execution_json).get("budget_policy_version") != POLICY_VERSION:
            raise BudgetRejected("AGENT_CONTEXT_UNBOUND")
        existing = await session.scalar(
            select(BudgetCall).where(
                BudgetCall.turn_id == runtime.turn_id,
                BudgetCall.namespace == identity.namespace,
                BudgetCall.logical_call_id == identity.logical_call_id,
            )
        )
        calls, chars = await totals(session, runtime.turn_id)
        runtime.budget.calls_used, runtime.budget.chars_fed = calls, chars
        if existing is not None:
            if (
                existing.tool_name,
                existing.args_fingerprint,
                existing.policy_version,
                existing.execution_id,
            ) != (
                tool_name,
                fingerprint,
                POLICY_VERSION,
                runtime.execution_id,
            ):
                raise BudgetRejected("TOOL_CALL_IDENTITY_CONFLICT")
            return existing.id
        if calls >= MAX_TOOL_CALLS_PER_TURN:
            raise BudgetRejected("TOOL_CALL_LIMIT")
        call_id = str(uuid4())
        session.add(
            BudgetCall(
                id=call_id,
                turn_id=runtime.turn_id,
                namespace=identity.namespace,
                logical_call_id=identity.logical_call_id,
                tool_name=tool_name,
                args_fingerprint=fingerprint,
                policy_version=POLICY_VERSION,
                execution_id=runtime.execution_id,
            )
        )
        await session.flush()
    runtime.budget.calls_used = calls + 1
    return call_id


async def _measure(
    runtime: AgentRuntimeContext,
    consumption: _Consumption,
    producer: Callable[[ToolCallBudget], str] | None = None,
) -> str | None:
    if not consumption.chars and producer is None:
        return
    if consumption.call_id is None:
        payload = producer(runtime.budget) if producer is not None else None
        runtime.budget.chars_fed += consumption.chars
        consumption.chars = 0
        return payload
    async with runtime.session_factory() as session, session.begin():
        if not await runtime.turn_write_allowed(session):
            raise BudgetRejected("CHAT_TURN_CANCELLED")
        assert runtime.turn_id is not None
        payload: str | None = None
        if producer is not None:
            # 检索裁剪与字符提交使用同一写锁，不能并发读取旧的剩余额度。
            runtime.budget.calls_used, runtime.budget.chars_fed = await totals(
                session, runtime.turn_id
            )
            payload = producer(runtime.budget)
        if consumption.chars and await session.get(BudgetOutput, consumption.output_id) is None:
            session.add(
                BudgetOutput(
                    id=consumption.output_id,
                    call_id=consumption.call_id,
                    chars_fed=consumption.chars,
                )
            )
            await session.flush()
        runtime.budget.calls_used, runtime.budget.chars_fed = await totals(session, runtime.turn_id)
    consumption.chars = 0
    return payload


async def format_output(producer: Callable[[ToolCallBudget], str]) -> str:
    """按当前消费裁剪并提交输出；adapter 只做同步序列化，不执行网络/领域查询。"""
    runtime = current_agent_runtime()
    consumption = _consumption.get()
    if runtime is None or consumption is None:
        raise RuntimeError("Tool output requires budget admission")
    payload = await _measure(runtime, consumption, producer)
    assert payload is not None
    return payload


async def execute[T](tool_name: str, args: object, handler: Callable[[], Awaitable[T]]) -> T | str:
    runtime = current_agent_runtime()
    if runtime is None:
        return await handler()
    try:
        call_id = await admit(runtime, tool_name, args)
    except BudgetRejected as exc:
        if exc.code == "TOOL_CALL_LIMIT":
            rejected = cast(dict[str, object], json.loads(POLICIES[tool_name]()))
            rejected.update(
                ok=False,
                error=exc.code,
                retryable=False,
                tool_budget=budget_snapshot(runtime.budget),
            )
            return json.dumps(rejected, ensure_ascii=False, separators=(",", ":"))
        return json.dumps({"ok": False, "error": exc.code})
    consumption = _Consumption(tool_name, call_id, str(uuid4()))
    token = _consumption.set(consumption)
    try:
        result = await handler()
        await _measure(runtime, consumption)
        return result
    finally:
        _consumption.reset(token)


def budgeted(
    rejection: Callable[[], str],
) -> Callable[[Callable[P, Awaitable[str]]], Callable[P, Awaitable[str]]]:
    def decorate(fn: Callable[P, Awaitable[str]]) -> Callable[P, Awaitable[str]]:
        POLICIES[fn.__name__] = rejection
        fn_signature = signature(fn)

        @wraps(fn)
        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> str:
            consumption = _consumption.get()
            if consumption is not None and consumption.tool_name == fn.__name__:
                return await fn(*args, **kwargs)
            bound = fn_signature.bind(*args, **kwargs)
            bound.apply_defaults()
            return await execute(fn.__name__, bound.arguments, lambda: fn(*args, **kwargs))

        return wrapped

    return decorate
