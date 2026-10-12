import asyncio
import json
from pathlib import Path
from typing import Literal, cast

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    SystemMessage,
    messages_from_dict,
    messages_to_dict,
)
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.agent.context import ChatContextTooLargeError
from app.modules.agent.context_budget.models import (
    ChatCompaction,
    ChatContextInput,
    ChatContextState,
    ChatModelRequest,
)
from app.modules.agent.context_budget.policy import estimate_input, policy_for
from app.modules.agent.context_budget.schemas import (
    ContextPolicy,
    ContextPreviewRequest,
    ContextViewOut,
    ModelRequestOut,
)
from app.modules.agent.models import ChatSession
from app.modules.agent.turns.models import ChatTurn
from app.modules.settings.config import (
    llm_consent,
    load_llm_provider,
    load_web_search_config,
    memory_outbound_enabled,
    resolve_user_timezone,
)
from app.shared.errors import CodedHTTPException


async def initialize_context(session: AsyncSession, session_id: str) -> ChatContextState:
    await session.execute(
        insert(ChatContextState).values(session_id=session_id).on_conflict_do_nothing()
    )
    state = await session.get(ChatContextState, session_id)
    assert state is not None
    return state


async def bind_context(
    session: AsyncSession, turn_id: str, session_id: str, policy: ContextPolicy
) -> None:
    state = await initialize_context(session, session_id)
    session.add(
        ChatContextInput(
            turn_id=turn_id,
            context_version=state.version,
            policy_json=policy.model_dump_json(),
            segment=state.segment,
            summary_id=state.summary_id,
        )
    )


async def context_input(
    session_factory: async_sessionmaker[AsyncSession], turn_id: str
) -> ChatContextInput | None:
    async with session_factory() as session:
        return await session.get(ChatContextInput, turn_id)


def restore_messages(snapshot: ChatContextInput) -> list[AnyMessage] | None:
    return (
        cast(list[AnyMessage], messages_from_dict(json.loads(snapshot.messages_json)))
        if snapshot.messages_json
        else None
    )


async def save_messages(
    session: AsyncSession, turn_id: str, messages: list[AnyMessage]
) -> list[AnyMessage]:
    snapshot = await session.get(ChatContextInput, turn_id)
    if snapshot is None:
        raise CodedHTTPException(
            code="MODEL_CONTEXT_INCOMPATIBLE",
            status_code=409,
            detail="原轮次缺少输入快照，请停止后重新提问",
        )
    original = restore_messages(snapshot)
    if original is not None:
        return original
    messages = await apply_history(session, messages, snapshot.summary_id)
    snapshot.messages_json = json.dumps(messages_to_dict(messages), ensure_ascii=False)
    return messages


async def apply_history(
    session: AsyncSession, messages: list[AnyMessage], summary_id: str | None
) -> list[AnyMessage]:
    from app.modules.agent.context_budget.compaction import summary_message

    result: list[AnyMessage] = []
    for message in messages:
        if isinstance(message, AIMessage) and message.id:
            turn = await session.scalar(
                select(ChatTurn).where(ChatTurn.final_message_id == message.id)
            )
            if turn:
                request = await session.scalar(
                    select(ChatModelRequest)
                    .where(
                        ChatModelRequest.turn_id == turn.id,
                        ChatModelRequest.purpose == "ANSWER",
                        ChatModelRequest.status == "COMPLETED",
                        ChatModelRequest.messages_json.is_not(None),
                    )
                    .order_by(ChatModelRequest.created_at.desc(), ChatModelRequest.id.desc())
                    .limit(1)
                )
                if request and request.messages_json:
                    saved = cast(
                        list[AnyMessage], messages_from_dict(json.loads(request.messages_json))
                    )
                    start = next(
                        (
                            index
                            for index, item in enumerate(saved)
                            if item.id == turn.user_message_id
                        ),
                        None,
                    )
                    if start is not None:
                        result.extend(saved[start + 1 :])
        result.append(message)
    summary = await session.get(ChatCompaction, summary_id) if summary_id else None
    if summary and summary.status == "COMPLETED":
        covered = set(json.loads(summary.covered_json))
        result = [message for message in result if message.id not in covered]
        index = 1 if result and isinstance(result[0], SystemMessage) else 0
        result.insert(index, summary_message(summary))
    return result


async def view_context(
    session_factory: async_sessionmaker[AsyncSession],
    data_dir: Path,
    session_id: str,
    preview: ContextPreviewRequest,
) -> ContextViewOut:
    async with session_factory() as session, session.begin():
        chat = await session.get(ChatSession, session_id)
        if chat is None:
            raise CodedHTTPException(
                code="CHAT_SESSION_NOT_FOUND", status_code=404, detail="对话不存在或已删除"
            )
        state = await initialize_context(session, session_id)
        turn_id = await session.scalar(
            select(ChatTurn.id)
            .where(ChatTurn.session_id == session_id)
            .order_by(ChatTurn.created_at.desc(), ChatTurn.id.desc())
            .limit(1)
        )
        requests = (
            list(
                (
                    await session.scalars(
                        select(ChatModelRequest)
                        .where(ChatModelRequest.turn_id == turn_id)
                        .order_by(ChatModelRequest.created_at, ChatModelRequest.id)
                    )
                ).all()
            )
            if turn_id
            else []
        )
        bound = await session.get(ChatContextInput, turn_id) if turn_id else None
        result = ContextViewOut(
            session_id=session_id,
            version=state.version,
            segment=state.segment,
            actual_turn_id=turn_id,
            actual=[
                ModelRequestOut(
                    id=row.id,
                    turn_id=row.turn_id,
                    status=row.status,
                    context_version=bound.context_version if bound else None,
                    estimate=json.loads(row.estimate_json),
                    usage=json.loads(row.usage_json) if row.usage_json else None,
                    error_code=row.error_code,
                    created_at=row.created_at,
                    purpose=cast(Literal["ANSWER", "SUMMARY"], row.purpose),
                )
                for row in requests
            ],
            next_estimate=None,
            next_error_code=None,
        )
        from app.modules.agent.context_budget.compaction import compaction_out

        compactions = (
            list(
                (
                    await session.scalars(
                        select(ChatCompaction)
                        .where(ChatCompaction.turn_id == turn_id)
                        .order_by(ChatCompaction.created_at, ChatCompaction.id)
                    )
                ).all()
            )
            if turn_id
            else []
        )
        result.compactions = [
            compaction_out(row, bound.summary_allowance if bound else 4) for row in compactions
        ]
        latest_turn = await session.get(ChatTurn, turn_id) if turn_id else None
        if latest_turn and latest_turn.status == "CANCELLED":
            for item in result.compactions:
                if item.status != "COMPLETED":
                    item.status = "CANCELLED"
        active = await session.get(ChatCompaction, state.summary_id) if state.summary_id else None
        if active:
            result.active_summary = compaction_out(active, bound.summary_allowance if bound else 4)
    provider = await asyncio.to_thread(load_llm_provider, data_dir)
    if provider is None or not provider.api_key:
        result.next_error_code = "LLM_PROVIDER_UNCONFIGURED"
        return result
    # 局部引用打断 service ↔ graph 装配依赖；所有选材仍由既有上下文服务负责。
    from app.modules.agent.graph import resolve_agent_config
    from app.modules.agent.message_service import session_context

    try:
        policy = policy_for(provider)
        _, consent = await asyncio.to_thread(llm_consent, data_dir)
        allowed = consent and await asyncio.to_thread(memory_outbound_enabled, data_dir)
        web_search = (
            preview.web_search
            and await asyncio.to_thread(load_web_search_config, data_dir) is not None
        )
        context = await session_context(
            session_factory,
            session_id,
            web_search=web_search,
            memory_allowed=allowed,
            preview_content=preview.content,
            page=preview.page,
            user_timezone=await asyncio.to_thread(resolve_user_timezone, data_dir),
        )
        config = resolve_agent_config(
            retrieval=context.scope != "FREE",
            web_search_enabled=web_search,
            research=context.mode == "RESEARCH",
        )
        async with session_factory() as session:
            preview_messages = await apply_history(session, context.messages, state.summary_id)
        result.next_estimate = estimate_input(policy, preview_messages, config.tools)
        result.next_error_code = result.next_estimate.error_code
    except CodedHTTPException as exc:
        result.next_error_code = exc.code
    except ChatContextTooLargeError:
        result.next_error_code = "CHAT_CONTEXT_TOO_LARGE"
    return result
