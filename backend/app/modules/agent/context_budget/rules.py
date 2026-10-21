"""单会话过滤规则；执行读取使用原轮快照，页面读取使用当前设置。"""

import json
from typing import Any, cast

from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.agent.context_budget.models import (
    ChatContextInput,
    ChatContextOutput,
    ChatContextState,
)
from app.modules.agent.context_budget.schemas import (
    ContextHistoryOut,
    ContextHistoryTurnOut,
    ContextRuleChange,
    ContextRules,
    ContextRulesOut,
)
from app.modules.agent.models import ChatMessage
from app.modules.agent.runtime import current_agent_runtime
from app.modules.agent.schemas import ChatRole
from app.modules.agent.session_service import ChatSessionService
from app.modules.agent.turns.models import ChatTurn
from app.modules.agent.turns.schemas import ChatTurnStatus
from app.modules.library.retrieval import (
    SEARCH_LIBRARY_LIMIT,
    LibraryRetrievalService,
    RetrievalResult,
    RetrievalScope,
)
from app.shared.errors import CodedHTTPException


async def context_rules(
    session: AsyncSession, session_id: str, *, turn_id: str | None = None, current: bool = False
) -> tuple[int, ContextRules]:
    runtime = current_agent_runtime()
    if not current and runtime and runtime.execution_id and runtime.session_id == session_id:
        from app.modules.agent.delegations.models import AgentDelegation

        child = await session.get(AgentDelegation, runtime.execution_id)
        if child is not None:
            frozen = json.loads(child.input_json)
            return frozen["segment"], ContextRules.model_validate_json(frozen["rules_json"])
    if not current and turn_id is None and runtime and runtime.session_id == session_id:
        turn_id = runtime.turn_id
    bound = await session.get(ChatContextInput, turn_id) if turn_id else None
    state = bound or await session.get(ChatContextState, session_id)
    return (
        (state.segment, ContextRules.model_validate_json(state.rules_json))
        if state
        else (1, ContextRules())
    )


def turn_allowed(rules: ContextRules, segment: int, turn_id: str | None, turn_segment: int) -> bool:
    return turn_id not in rules.excluded_turn_ids and (
        turn_segment == segment or turn_id in rules.included_turn_ids
    )


async def history_identities(
    session: AsyncSession, session_id: str, messages: list[ChatMessage] | None = None
) -> dict[str, tuple[str, int, str]]:
    turns = (
        await session.execute(
            select(ChatTurn, ChatContextInput.segment)
            .outerjoin(ChatContextInput, ChatContextInput.turn_id == ChatTurn.id)
            .where(ChatTurn.session_id == session_id)
        )
    ).all()
    identities = {
        identity: (turn.id, segment or 1, turn.status)
        for turn, segment in turns
        for identity in (turn.user_message_id, turn.final_message_id)
        if identity
    }
    if messages is None:
        rows = (
            await session.execute(
                select(ChatMessage.id, ChatMessage.role)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at, ChatMessage.id)
            )
        ).all()
        roles = [(identity, role) for identity, role in rows]
    else:
        roles = [(message.id, message.role) for message in messages]
    previous: str | None = None
    for identity, role in roles:
        if identity in identities or role == ChatRole.SYSTEM:
            previous = None
            continue
        if role == ChatRole.USER:
            previous = identity
            identities[identity] = (f"legacy:{identity}", 1, "INCOMPLETE")
        elif previous:
            pair = (f"legacy:{previous}", 1, "COMPLETED")
            identities[identity] = pair
            identities[previous] = pair
    return identities


async def source_excluded(
    session: AsyncSession, session_id: str, source_id: str, rules: ContextRules
) -> bool:
    if source_id in rules.excluded_source_ids:
        return True
    kind, sep, target = source_id.partition(":")
    if not sep:
        kind, target = "message", source_id
    if kind == "message":
        identity = (await history_identities(session, session_id)).get(target)
        turn_id = identity[0] if identity else None
    elif kind == "output":
        turn_id = await session.scalar(
            select(ChatContextOutput.turn_id)
            .join(ChatTurn, ChatTurn.id == ChatContextOutput.turn_id)
            .where(ChatTurn.session_id == session_id, ChatContextOutput.id == target)
        )
    else:
        return False
    return turn_id in rules.excluded_turn_ids


async def require_source_allowed(
    session: AsyncSession, session_id: str, source_id: str, rules: ContextRules | None = None
) -> None:
    if rules is None:
        _, rules = await context_rules(session, session_id)
    if await source_excluded(session, session_id, source_id, rules):
        raise CodedHTTPException(
            code="CONTEXT_SOURCE_EXCLUDED",
            status_code=409,
            detail="来源已被排除，可在下一轮设置中恢复",
        )


def evidence_excluded(evidence: object, rules: ContextRules) -> bool:
    if not isinstance(evidence, list):
        return False
    for item in cast(list[object], evidence):
        if isinstance(item, dict):
            fields = cast(dict[str, object], item)
            if any(
                f"{kind}:{fields.get(key)}" in rules.excluded_source_ids
                for kind, key in (("record", "record_id"), ("library", "library_item_id"))
            ):
                return True
    return False


async def search_material(
    session: AsyncSession,
    session_id: str,
    scope: RetrievalScope,
    query: str,
    limit: int = SEARCH_LIBRARY_LIMIT,
) -> RetrievalResult:
    _, rules = await context_rules(session, session_id)
    excluded = rules.excluded_source_ids
    if f"record:{scope.record_id}" in excluded or f"library:{scope.library_item_id}" in excluded:
        return RetrievalResult()
    found = await LibraryRetrievalService.search(session, scope, query, limit)
    return RetrievalResult(
        evidence_hits=[
            hit
            for hit in found.evidence_hits
            if f"record:{hit.record_id}" not in excluded
            and f"library:{hit.library_item_id}" not in excluded
        ],
        asset_matches=[
            hit
            for hit in found.asset_matches
            if f"{'record' if hit.type == 'RECORD' else 'library'}:{hit.id}" not in excluded
        ],
        concept_hints=found.concept_hints,
    )


class RuleStateSnapshot(BaseModel):
    version: int
    segment: int
    rules: ContextRules
    source_version: str | None = None


async def capture_rule_state(
    session: AsyncSession, session_id: str, change: ContextRuleChange
) -> RuleStateSnapshot:
    from app.modules.agent.context_budget.service import initialize_context
    from app.modules.library.retrieval import LibraryRetrievalService

    chat = await ChatSessionService.get(session, session_id)
    if chat is None:
        raise CodedHTTPException(
            code="CHAT_SESSION_NOT_FOUND", status_code=404, detail="对话不存在或已删除"
        )
    state = await initialize_context(session, session_id)
    if state.version != change.expected_version:
        raise CodedHTTPException(
            code="CONTEXT_VERSION_CONFLICT", status_code=409, detail="设置已变化，请刷新后重试"
        )
    rules = ContextRules.model_validate_json(state.rules_json)
    for identity in change.turn_ids:
        if identity.startswith("legacy:"):
            entry = (await history_identities(session, session_id)).get(
                identity.removeprefix("legacy:")
            )
            if (
                entry is None
                or entry[0] != identity
                or (
                    change.action == "INCLUDE_HISTORY"
                    and (entry[2] != "COMPLETED" or state.segment <= 1)
                )
            ):
                raise CodedHTTPException(
                    code="CONTEXT_HISTORY_RANGE_INVALID",
                    status_code=409,
                    detail="旧历史范围不属于当前会话或尚未完成",
                )
            continue
        turn = await session.get(ChatTurn, identity)
        bound = await session.get(ChatContextInput, identity)
        if (
            turn is None
            or turn.session_id != session_id
            or (
                change.action == "INCLUDE_HISTORY"
                and (turn.status != "COMPLETED" or (bound.segment if bound else 1) >= state.segment)
            )
        ):
            raise CodedHTTPException(
                code="CONTEXT_HISTORY_RANGE_INVALID",
                status_code=409,
                detail="请选择本会话已完成的旧段轮次",
            )
    version = None
    if change.source_id:
        if change.action == "RESTORE_SOURCE":
            if change.source_id not in rules.excluded_source_ids:
                raise CodedHTTPException(
                    code="CONTEXT_HISTORY_RANGE_INVALID",
                    status_code=409,
                    detail="来源未被排除，请刷新设置",
                )
        else:
            kind, _, target = change.source_id.partition(":")
            _, _, version = await LibraryRetrievalService.read_source(
                session,
                RetrievalScope(chat.scope, chat.record_id, chat.library_item_id, chat.course_id),
                kind,
                target,
            )
            if version != change.source_version:
                raise CodedHTTPException(
                    code="CONTEXT_SOURCE_STALE", status_code=409, detail="来源已变化，请重新选择"
                )
    return RuleStateSnapshot(
        version=state.version, segment=state.segment, rules=rules, source_version=version
    )


async def change_rules_core(
    session: AsyncSession, session_id: str, change: ContextRuleChange
) -> ContextRulesOut:
    locked = cast(
        CursorResult[Any],
        await session.execute(
            update(ChatContextState)
            .where(
                ChatContextState.session_id == session_id,
                ChatContextState.version == change.expected_version,
            )
            .values(version=ChatContextState.version)
        ),
    )
    if locked.rowcount != 1:
        await capture_rule_state(session, session_id, change)
    snapshot = await capture_rule_state(session, session_id, change)
    state = await session.get(ChatContextState, session_id)
    assert state is not None
    rules = snapshot.rules
    if change.action == "RESET":
        state.segment += 1
        rules.included_turn_ids = []
    elif change.action == "INCLUDE_HISTORY":
        rules.included_turn_ids = sorted(set(rules.included_turn_ids) | set(change.turn_ids))
    elif change.action.endswith("TURN"):
        selected = set(rules.excluded_turn_ids)
        if change.action == "EXCLUDE_TURN":
            selected.update(change.turn_ids)
        else:
            selected.difference_update(change.turn_ids)
        rules.excluded_turn_ids = sorted(selected)
    else:
        assert change.source_id is not None
        selected = set(rules.excluded_source_ids)
        if change.action == "EXCLUDE_SOURCE":
            selected.add(change.source_id)
        else:
            selected.discard(change.source_id)
        rules.excluded_source_ids = sorted(selected)
    state.version += 1
    state.summary_id = None
    state.rules_json = rules.model_dump_json()
    await session.flush()
    return ContextRulesOut(
        session_id=session_id, version=state.version, segment=state.segment, rules=rules
    )


async def change_rules(
    factory: async_sessionmaker[AsyncSession], session_id: str, change: ContextRuleChange
) -> ContextRulesOut:
    from app.modules.agent.runs.schemas import OperationAuthorization
    from app.modules.agent.runs.service import record_direct_execution

    async with factory() as session, session.begin():
        result = await change_rules_core(session, session_id, change)
        await record_direct_execution(
            session,
            action="change_context_rules",
            level="L1",
            target=("chat_session", session_id),
            payload_json=change.model_dump_json(),
            authorization=OperationAuthorization(trigger="USER_MANUAL", session_id=session_id),
            result_dict=result.model_dump(mode="json"),
        )
    return result


async def history_turns(
    factory: async_sessionmaker[AsyncSession],
    session_id: str,
    offset: int,
    expected_version: int | None,
) -> ContextHistoryOut:
    async with factory() as session, session.begin():
        if await ChatSessionService.get(session, session_id) is None:
            raise CodedHTTPException(
                code="CHAT_SESSION_NOT_FOUND", status_code=404, detail="对话不存在或已删除"
            )
        from app.modules.agent.context_budget.service import initialize_context

        state = await initialize_context(session, session_id)
        if offset and expected_version != state.version:
            raise CodedHTTPException(
                code="CONTEXT_VERSION_CONFLICT", status_code=409, detail="设置已变化，请重新读取"
            )
        rules = ContextRules.model_validate_json(state.rules_json)
        messages = list(
            (
                await session.scalars(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session_id)
                    .order_by(ChatMessage.created_at, ChatMessage.id)
                )
            ).all()
        )
        identities = await history_identities(session, session_id, messages)
        rows = [
            message
            for message in reversed(messages)
            if message.role == ChatRole.USER and message.id in identities
        ]
        page = rows[offset : offset + 20]
        return ContextHistoryOut(
            version=state.version,
            turns=[
                ContextHistoryTurnOut(
                    turn_id=identities[message.id][0],
                    segment=identities[message.id][1],
                    status="INCOMPLETE"
                    if identities[message.id][2] == "INCOMPLETE"
                    else ChatTurnStatus(identities[message.id][2]),
                    title=message.content[:160],
                    excluded=identities[message.id][0] in rules.excluded_turn_ids,
                    included=turn_allowed(
                        rules, state.segment, identities[message.id][0], identities[message.id][1]
                    ),
                )
                for message in page
            ],
            next_offset=offset + 20 if len(rows) > offset + 20 else None,
        )
