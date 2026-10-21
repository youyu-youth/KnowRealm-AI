"""子执行体；候选、领取、失败及恢复全部由原 CHAT_TURN 双槽调用。"""

from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import uuid4

import openai
from langchain_core.messages import AnyMessage, messages_from_dict
from langgraph.checkpoint.base import BaseCheckpointSaver  # pyright: ignore[reportMissingTypeStubs]
from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.modules.agent.budget.policy import POLICY_VERSION, ToolCallBudget
from app.modules.agent.budget.service import restore
from app.modules.agent.citations import parse_library_citation_reply
from app.modules.agent.context_budget.retrieval import validate_evidence
from app.modules.agent.context_budget.schemas import ContextPolicy, ContextRules
from app.modules.agent.delegations.models import AgentDelegation
from app.modules.agent.delegations.schemas import KnowledgeResult
from app.modules.agent.delegations.service import (
    TERMINAL,
    commit_result,
    emit_state,
    thread_id,
    unresolved_requests,
)
from app.modules.agent.graph import ChatStreamOutcome, TurnCheckpointMissingError, stream_chat_reply
from app.modules.agent.message_service import load_library_materials, validate_sendable_chat
from app.modules.agent.middleware.cancel_guard import TurnCancelledError
from app.modules.agent.models import ChatSession
from app.modules.agent.runtime import AgentRuntimeContext
from app.modules.agent.schemas import AgentId, ChatCitationOut, ChatMode, ChatScope
from app.modules.agent.turns.models import ChatTurn
from app.modules.agent.turns.runtime import TurnEventBroadcaster, watch_turn_stop
from app.modules.agent.turns.service import resume_blocked_reason
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.runner import CancelClaim, ClaimCheck, Ready, RunnerContext, WaitingClaim
from app.modules.jobs.schemas import ProcessingJobStatus
from app.modules.settings.config import llm_provider_fingerprint, load_llm_provider
from app.shared.errors import CodedHTTPException

if TYPE_CHECKING:
    from app.modules.agent.turns.worker import _ClaimedTurn  # pyright: ignore[reportPrivateUsage]


class DelegationUncertain(Exception):
    """存在未得到可靠完成结果的请求，必须由用户明确选择。"""


async def owns_claim(session: AsyncSession, ctx: _ClaimedTurn) -> bool:
    await session.execute(
        update(ChatTurn).where(ChatTurn.id == ctx.turn_id).values(updated_at=ChatTurn.updated_at)
    )
    child = await session.get(AgentDelegation, ctx.delegation_id)
    return (
        child is not None
        and child.turn_id == ctx.turn_id
        and child.job_id == ctx.job_id
        and child.claim_token == ctx.claim_token
        and not child.cancel_requested
    )


async def validate_claim(
    session: AsyncSession, job: ProcessingJob, execution_id: str
) -> ClaimCheck[_ClaimedTurn]:
    from app.modules.agent.turns.worker import _ClaimedTurn  # pyright: ignore[reportPrivateUsage]

    child = await session.get(AgentDelegation, execution_id)
    root = await session.get(ChatTurn, child.turn_id) if child else None
    if (
        root is not None
        and not root.cancel_requested
        and root.status in ("QUEUED", "WAITING_USER", "INTERRUPTED")
    ):
        return WaitingClaim("delegation_parent_waiting")
    if (
        child is None
        or child.job_id != job.id
        or root is None
        or root.cancel_requested
        or root.status not in ("RUNNING", "WAITING_JOB")
    ):
        return CancelClaim("delegation_unavailable")
    if child.status == "RUNNING":
        return WaitingClaim("delegation_busy")
    if child.status != "QUEUED" or child.cancel_requested:
        return CancelClaim("delegation_not_queued")
    return Ready(
        _ClaimedTurn(
            job_id=job.id, record_id="", turn_id=root.id, claim_token="", delegation_id=child.id
        )
    )


async def claim(
    session: AsyncSession, job: ProcessingJob, ctx: _ClaimedTurn, now: datetime
) -> _ClaimedTurn:
    await session.execute(
        update(ChatTurn).where(ChatTurn.id == ctx.turn_id).values(updated_at=ChatTurn.updated_at)
    )
    child = await session.get(AgentDelegation, ctx.delegation_id)
    root = await session.get(ChatTurn, ctx.turn_id)
    if (
        child is None
        or root is None
        or root.cancel_requested
        or child.cancel_requested
        or child.status != "QUEUED"
        or root.status not in ("RUNNING", "WAITING_JOB")
    ):
        job.status, job.finished_at, job.updated_at = ProcessingJobStatus.CANCELLED, now, now
        return ctx
    child.status, child.claim_token = "RUNNING", str(uuid4())
    child.attempt += 1
    child.started_at, child.updated_at = child.started_at or now, now
    await emit_state(session, child)
    return replace(ctx, claim_token=child.claim_token)


async def failure(session: AsyncSession, ctx: _ClaimedTurn, code: str) -> None:
    await session.execute(
        update(ChatTurn).where(ChatTurn.id == ctx.turn_id).values(updated_at=ChatTurn.updated_at)
    )
    child = await session.get(AgentDelegation, ctx.delegation_id)
    root = await session.get(ChatTurn, ctx.turn_id)
    if (
        child is None
        or root is None
        or root.cancel_requested
        or child.claim_token != ctx.claim_token
        or child.status != "RUNNING"
    ):
        return
    if root.status in ("QUEUED", "WAITING_USER", "INTERRUPTED"):
        await defer_for_parent(session, ctx)
        return
    if root.status not in ("RUNNING", "WAITING_JOB"):
        return
    unknown = await unresolved_requests(session, child)
    unsafe = code in ("MODEL_CONTEXT_INCOMPATIBLE", "CHAT_TURN_RESUME_UNSAFE")
    status: Literal["INTERRUPTED", "FAILED"] = "INTERRUPTED" if unknown or unsafe else "FAILED"
    child.status = status
    child.error_code = code
    child.updated_at = utcnow()
    child.finished_at = None if status == "INTERRUPTED" else utcnow()
    child.result_json = KnowledgeResult(
        task_id=child.id, status=status, error_code=child.error_code, gaps=["知识任务未完成"]
    ).model_dump_json()
    await emit_state(session, child)


async def defer_for_parent(session: AsyncSession, ctx: _ClaimedTurn) -> None:
    if not await owns_claim(session, ctx):
        return
    root = await session.get(ChatTurn, ctx.turn_id)
    child = await session.get(AgentDelegation, ctx.delegation_id)
    if (
        root is None
        or child is None
        or child.status != "RUNNING"
        or root.cancel_requested
        or root.status not in ("QUEUED", "WAITING_USER", "INTERRUPTED")
    ):
        return
    job = await session.get(ProcessingJob, ctx.job_id)
    if job is None:
        return
    child.status, child.claim_token, child.updated_at = "QUEUED", None, utcnow()
    job.status, job.finished_at, job.next_run_at, job.updated_at = (
        ProcessingJobStatus.PENDING,
        None,
        None,
        utcnow(),
    )
    await emit_state(session, child)


async def execute(
    ctx: _ClaimedTurn,
    runner: RunnerContext,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
    checkpointer: BaseCheckpointSaver[str],
    broadcaster: TurnEventBroadcaster,
) -> bool:
    async with session_factory() as session:
        child = await session.get(AgentDelegation, ctx.delegation_id)
        root = await session.get(ChatTurn, ctx.turn_id)
        if (
            child is None
            or root is None
            or child.status != "RUNNING"
            or child.claim_token != ctx.claim_token
        ):
            return True
        frozen: dict[str, Any] = json.loads(child.input_json)
        attempt, execution_id = child.attempt, child.id
        retry_request, decision_id = child.retry_request_id, child.decision_id
    policy = ContextPolicy.model_validate_json(frozen["policy_json"])
    runtime = AgentRuntimeContext(
        session_factory,
        root.session_id,
        agent_id=AgentId.KNOWLEDGE,
        scope=ChatScope(frozen["scope"]),
        mode=ChatMode(frozen["mode"]),
        course_id=frozen["course_id"],
        record_id=frozen["record_id"],
        library_item_id=frozen["library_item_id"],
        turn_id=root.id,
        execution_id=execution_id,
        execution_attempt=attempt,
        execution_claim_token=ctx.claim_token,
        context_policy=policy,
        data_dir=data_dir,
        provider_fingerprint=frozen["execution"].get("provider_fingerprint"),
        outbound_consent_required=bool(frozen["execution"].get("outbound_consent_required")),
        retry_request_id=retry_request,
        decision_id=decision_id,
    )
    cancel = asyncio.Event()

    async def drive() -> None:
        provider = await asyncio.to_thread(load_llm_provider, data_dir)
        blocked = await resume_blocked_reason(data_dir, frozen["execution"], provider)
        if blocked is not None or provider is None:
            raise CodedHTTPException(
                code="MODEL_CONTEXT_INCOMPATIBLE"
                if blocked and blocked[0].value == "GRAPH_INCOMPATIBLE"
                else "CHAT_TURN_RESUME_CONDITION_UNMET",
                status_code=409,
                detail=blocked[1] if blocked else "供应商不可用",
            )
        if frozen["execution"].get("budget_policy_version") != POLICY_VERSION:
            raise CodedHTTPException(
                code="MODEL_CONTEXT_INCOMPATIBLE", status_code=409, detail="预算策略已变化"
            )
        runtime.llm_provider, runtime.provider_fingerprint = (
            provider,
            llm_provider_fingerprint(provider),
        )
        async with session_factory() as session:
            chat = await session.get(ChatSession, root.session_id)
            if chat is None:
                raise TurnCancelledError
            await validate_sendable_chat(session, chat)
        calls, chars = await restore(session_factory, root.id)
        runtime.budget = ToolCallBudget(calls_used=calls, chars_fed=chars)
        outcome = ChatStreamOutcome()

        async def consume(resume: bool) -> None:
            from app.modules.agent.turns.worker import ACLOSE_TIMEOUT_SECONDS

            stream = stream_chat_reply(
                checkpointer=checkpointer,
                provider=provider,
                context_messages=cast(list[AnyMessage], messages_from_dict(frozen["messages"])),
                runtime=runtime,
                outcome=outcome,
                thread_id=thread_id(execution_id),
                tool_namespace=thread_id(execution_id),
                cancel_check=cancel.is_set,
                resume=resume,
            )
            try:
                async for _event in stream:
                    pass
            finally:
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(stream.aclose(), ACLOSE_TIMEOUT_SECONDS)

        try:
            await consume(attempt > 1)
        except TurnCheckpointMissingError:
            async with session_factory() as session:
                unknown = await unresolved_requests(session, child)
                from app.modules.agent.context_budget.models import ChatModelRequest

                has_requests = await session.scalar(
                    select(ChatModelRequest.id)
                    .where(ChatModelRequest.execution_id == execution_id)
                    .limit(1)
                )
            if unknown or has_requests:
                raise CodedHTTPException(
                    code="CHAT_TURN_RESUME_UNSAFE",
                    status_code=409,
                    detail="子图状态缺失，不能可靠恢复，请停止后新任务",
                ) from None
            await consume(False)
        content = outcome.final_text or ""
        scope_id = (
            runtime.library_item_id
            if runtime.scope == ChatScope.LIBRARY_ITEM
            else runtime.record_id
            if runtime.scope == ChatScope.RECORD
            else runtime.course_id
        )
        records, items = await load_library_materials(session_factory, runtime.scope, scope_id)
        parsed = parse_library_citation_reply(content, records, items, allow_web=False)
        async with session_factory() as session:
            chat = await session.get(ChatSession, root.session_id)
            assert chat is not None
            await validate_sendable_chat(session, chat)
            await validate_evidence(
                session,
                chat,
                parsed.citations,
                rules=ContextRules.model_validate_json(frozen["rules_json"]),
            )
        result = KnowledgeResult(
            task_id=execution_id,
            status="COMPLETED" if content else "FAILED",
            summary=parsed.content,
            citations=[ChatCitationOut.model_validate(item) for item in parsed.citations],
            error_code=None if content else "EMPTY_REPLY",
        )
        if await commit_result(runtime, result):
            await checkpointer.adelete_thread(thread_id(execution_id))
            broadcaster.publish(root.id)

    watcher = asyncio.create_task(watch_turn_stop(session_factory, root.id, cancel, runner.stopped))
    work = asyncio.create_task(drive())
    stopped = asyncio.create_task(runner.stopped.wait())
    cancelled = asyncio.create_task(cancel.wait())
    try:
        done, _ = await asyncio.wait(
            {work, stopped, cancelled}, return_when=asyncio.FIRST_COMPLETED
        )
        if work not in done:
            from app.modules.agent.turns.worker import ACLOSE_TIMEOUT_SECONDS

            work.cancel()
            with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                await asyncio.wait_for(work, ACLOSE_TIMEOUT_SECONDS * 2)
        else:
            await work
    except (DelegationUncertain, openai.APIConnectionError, openai.APITimeoutError):
        async with session_factory() as session, session.begin():
            await failure(session, ctx, "CHAT_STREAM_FAILED")
    except TurnCancelledError:
        async with session_factory() as session, session.begin():
            await defer_for_parent(session, ctx)
    except Exception as exc:
        logger.warning(
            "agent_delegation_failed", execution_id=execution_id, error_type=type(exc).__name__
        )
        async with session_factory() as session, session.begin():
            await failure(
                session,
                ctx,
                exc.code if isinstance(exc, CodedHTTPException) else "CHAT_STREAM_FAILED",
            )
    finally:
        for task in (watcher, stopped, cancelled):
            task.cancel()
        for task in (watcher, stopped, cancelled):
            with contextlib.suppress(asyncio.CancelledError):
                await task
        async with session_factory() as session:
            saved = await session.get(AgentDelegation, execution_id)
            cleanup = saved is not None and saved.status in TERMINAL
        if cleanup:
            await checkpointer.adelete_thread(thread_id(execution_id))
    return True


async def cleanup_turn(
    factory: async_sessionmaker[AsyncSession],
    checkpointer: BaseCheckpointSaver[str],
    turn_id: str,
) -> None:
    async with factory() as session:
        ids = (
            await session.scalars(
                select(AgentDelegation.id).where(
                    AgentDelegation.turn_id == turn_id,
                    AgentDelegation.status.in_(TERMINAL),
                )
            )
        ).all()
    for execution_id in ids:
        await checkpointer.adelete_thread(thread_id(execution_id))


async def recover(session: AsyncSession) -> list[str]:
    children = (await session.scalars(select(AgentDelegation))).all()
    cleanup: list[str] = []
    for child in children:
        root = await session.get(ChatTurn, child.turn_id)
        if root is None:
            continue
        if child.status in TERMINAL:
            cleanup.append(child.id)
        elif root.cancel_requested or root.status in ("COMPLETED", "FAILED", "CANCELLED"):
            from app.modules.agent.delegations.service import cancel_children

            await cancel_children(session, root.id, "根任务已结束")
            cleanup.append(child.id)
        elif child.status in ("QUEUED", "RUNNING"):
            child.status, child.updated_at = "QUEUED", utcnow()
            job = await session.get(ProcessingJob, child.job_id)
            if job:
                job.status, job.next_run_at, job.finished_at = (
                    ProcessingJobStatus.PENDING,
                    None,
                    None,
                )
                job.updated_at = utcnow()
    return cleanup
