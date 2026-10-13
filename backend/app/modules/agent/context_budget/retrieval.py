"""页面与只读 Tool 共用的会话/段/来源读取边界。"""

import base64
import binascii
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import cast

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    ToolMessage,
    messages_from_dict,
    messages_to_dict,
)
from sqlalchemy import and_, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.agent.context_budget.models import (
    ChatContextInput,
    ChatContextOutput,
    ChatContextState,
    ChatModelRequest,
)
from app.modules.agent.context_budget.schemas import (
    ContextReadOut,
    ContextReadRequest,
    ContextSearchOut,
    ContextSearchRequest,
    ContextSourceOut,
)
from app.modules.agent.models import ChatMessage, ChatSession
from app.modules.agent.schemas import ChatRole, ChatScope
from app.modules.agent.session_service import ChatSessionService
from app.modules.agent.turns.models import ChatTurn
from app.modules.library.retrieval import LibraryRetrievalService, RetrievalScope
from app.modules.record.service import RecordService
from app.shared.errors import CodedHTTPException


@dataclass
class _ReadCache:
    # 仅在一次重验证内复用；共享关系/删除状态不一定改变正文版本。
    materials: dict[tuple[str, str], tuple[str, str, str] | CodedHTTPException] = field(
        default_factory=dict[tuple[str, str], tuple[str, str, str] | CodedHTTPException]
    )
    legacy: dict[str, tuple[ToolMessage, AIMessage, str]] = field(
        default_factory=dict[str, tuple[ToolMessage, AIMessage, str]]
    )
    evidence: set[tuple[str, str, str | None, str | None]] = field(
        default_factory=set[tuple[str, str, str | None, str | None]]
    )
    before: tuple[datetime, str] | None = None
    exhausted: bool = False


async def _read_material(
    session: AsyncSession, chat: ChatSession, kind: str, target: str, cache: _ReadCache | None
) -> tuple[str, str, str]:
    key = kind, target
    if cache is None:
        return await LibraryRetrievalService.read_source(
            session, _material_scope(chat), kind, target
        )
    if key not in cache.materials:
        try:
            cache.materials[key] = await LibraryRetrievalService.read_source(
                session, _material_scope(chat), kind, target
            )
        except CodedHTTPException as exc:
            cache.materials[key] = exc
    value = cache.materials[key]
    if isinstance(value, CodedHTTPException):
        raise value
    return value


def digest(content: str) -> str:
    return sha256(content.encode()).hexdigest()


def _cursor(binding: Sequence[object], offset: int) -> str:
    return base64.urlsafe_b64encode(
        json.dumps([digest(json.dumps([*binding, offset])), offset]).encode()
    ).decode()


def _offset(cursor: str | None, binding: Sequence[object], total: int) -> int:
    if cursor is None:
        return 0
    try:
        raw: object = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
        value = cast(list[object], raw) if isinstance(raw, list) else []
        if (
            len(value) == 2
            and type(value[1]) is int
            and 0 < value[1] < total
            and value[0] == digest(json.dumps([*binding, value[1]]))
        ):
            return value[1]
    except (ValueError, binascii.Error, UnicodeDecodeError):
        pass
    raise CodedHTTPException(
        code="CONTEXT_CURSOR_INVALID",
        status_code=409,
        detail="读取游标无效或来源已变化，请重新读取",
    )


async def _scope(session: AsyncSession, session_id: str) -> tuple[ChatSession, int, int]:
    chat = await ChatSessionService.get_out(session, session_id)
    if chat is None:
        raise CodedHTTPException(
            code="CHAT_SESSION_NOT_FOUND", status_code=404, detail="对话不存在或已删除"
        )
    if chat.record_deleted or chat.course_deleted or chat.library_item_deleted:
        raise CodedHTTPException(
            code="CONTEXT_SOURCE_UNAVAILABLE", status_code=409, detail="挂载来源已失效"
        )
    row = await session.get(ChatSession, session_id)
    assert row is not None
    from app.modules.agent.message_service import validate_sendable_chat

    await validate_sendable_chat(session, row)
    state = await session.get(ChatContextState, session_id)
    return row, state.segment if state else 1, state.version if state else 1


def _material_scope(chat: ChatSession) -> RetrievalScope:
    return RetrievalScope(chat.scope, chat.record_id, chat.library_item_id, chat.course_id)


async def _messages(
    session: AsyncSession, session_id: str, segment: int, target: str | None = None
) -> list[ChatMessage]:
    rows = (
        await session.execute(
            select(ChatMessage, ChatContextInput.segment, ChatTurn.id)
            .outerjoin(
                ChatTurn,
                or_(
                    ChatTurn.user_message_id == ChatMessage.id,
                    ChatTurn.final_message_id == ChatMessage.id,
                ),
            )
            .outerjoin(ChatContextInput, ChatContextInput.turn_id == ChatTurn.id)
            .where(ChatMessage.session_id == session_id, ChatMessage.role != ChatRole.SYSTEM)
            .where(ChatMessage.id == target if target is not None else true())
            .order_by(ChatMessage.created_at, ChatMessage.id)
        )
    ).all()
    # 升级前没有段快照的原消息只属于初始段，不自动纳入后续重置段。
    return [row for row, bound, _turn in rows if (bound if bound is not None else 1) == segment]


async def _outputs(
    session: AsyncSession, session_id: str, segment: int, target: str | None = None
) -> list[ChatContextOutput]:
    return list(
        (
            await session.scalars(
                select(ChatContextOutput)
                .join(ChatTurn, ChatTurn.id == ChatContextOutput.turn_id)
                .join(ChatContextInput, ChatContextInput.turn_id == ChatTurn.id)
                .where(ChatTurn.session_id == session_id, ChatContextInput.segment == segment)
                .where(ChatContextOutput.id == target if target is not None else true())
                .order_by(ChatContextOutput.created_at, ChatContextOutput.id)
            )
        ).all()
    )


async def _message_source(
    session: AsyncSession, row: ChatMessage, cache: _ReadCache | None = None
) -> ContextSourceOut:
    turn_id = await session.scalar(
        select(ChatTurn.id).where(
            or_(ChatTurn.user_message_id == row.id, ChatTurn.final_message_id == row.id)
        )
    )
    result = ContextSourceOut(
        source_id=f"message:{row.id}",
        kind="message",
        title=row.content[:120],
        version=digest(row.content),
        turn_id=turn_id,
        locator={"message_id": row.id, "role": row.role, "created_at": row.created_at.isoformat()},
    )
    if row.citations_json:
        chat = await session.get(ChatSession, row.session_id)
        assert chat is not None
        try:
            await validate_evidence(session, chat, json.loads(row.citations_json), cache)
            result.locator["citations_state"] = "VALID"
        except CodedHTTPException:
            result.locator["citations_state"] = "STALE"
    return result


async def validate_evidence(
    session: AsyncSession, chat: ChatSession, value: object, cache: _ReadCache | None = None
) -> None:
    """历史摘录不能绕过当前资料归属、版本和逐字证据校验。"""
    if not isinstance(value, list):
        return
    for raw in cast(list[object], value):
        if not isinstance(raw, dict):
            continue
        hit = cast(dict[str, object], raw)
        kind = "record" if hit.get("record_id") else "library"
        target = hit.get("record_id") or hit.get("library_item_id")
        if not isinstance(target, str):
            continue
        quote = hit.get("quote")
        expected = hit.get("source_version")
        key = (
            kind,
            target,
            str(expected) if expected is not None else None,
            (quote if isinstance(quote, str) else None),
        )
        if cache is not None and key in cache.evidence:
            continue
        _, content, version = await _read_material(session, chat, kind, target, cache)
        if (isinstance(quote, str) and quote not in content) or (
            expected is not None and str(expected) != version
        ):
            raise CodedHTTPException(
                code="CONTEXT_SOURCE_STALE", status_code=409, detail="原文证据或来源版本已变化"
            )
        if cache is not None:
            cache.evidence.add(key)


def _output_source(row: ChatContextOutput) -> ContextSourceOut:
    return ContextSourceOut(
        source_id=f"output:{row.id}",
        kind="output",
        title=row.tool_name,
        version=row.content_hash,
        turn_id=row.turn_id,
        locator={
            "tool": row.tool_name,
            "tool_call_id": row.logical_call_id,
            "created_at": row.created_at.isoformat(),
        },
    )


async def search_context(
    factory: async_sessionmaker[AsyncSession], session_id: str, body: ContextSearchRequest
) -> ContextSearchOut:
    async with factory() as session:
        chat, segment, version = await _scope(session, session_id)
        query = body.query.strip()
        sources = [
            await _message_source(session, row)
            for row in await _messages(session, session_id, segment)
            if not query or re.search(re.escape(query), row.content, re.IGNORECASE)
        ]
        sources.extend(
            _output_source(row)
            for row in await _outputs(session, session_id, segment)
            if not query or re.search(re.escape(query), row.content, re.IGNORECASE)
        )
        if query:
            content_by_id = {
                f"message:{row.id}": row.content
                for row in await _messages(session, session_id, segment)
            }
            content_by_id.update(
                {
                    f"output:{row.id}": row.content
                    for row in await _outputs(session, session_id, segment)
                }
            )
            for source in sources:
                content = content_by_id[source.source_id]
                match = re.search(re.escape(query), content, re.IGNORECASE)
                assert match is not None
                source.locator.update(
                    {
                        "start_offset": match.start(),
                        "quote": content[match.start() : match.start() + 80],
                    }
                )
        if query and chat.scope != ChatScope.FREE:
            found = await LibraryRetrievalService.search(session, _material_scope(chat), query)
            for hit in found.evidence_hits:
                kind = "record" if hit.record_id else "library"
                target = hit.record_id or hit.library_item_id
                if target is None:
                    continue
                source_id = f"{kind}:{target}"
                if any(source.source_id == source_id for source in sources):
                    continue
                title, material, source_version = await LibraryRetrievalService.read_source(
                    session, _material_scope(chat), kind, target
                )
                match_offset = await LibraryRetrievalService.source_offset(
                    session, kind, target, hit.segment_id, material, hit.quote[:80]
                )
                sources.append(
                    ContextSourceOut(
                        source_id=source_id,
                        kind=kind,
                        title=title[:120],
                        version=source_version,
                        locator={
                            "segment_id": hit.segment_id,
                            "quote": hit.quote[:80],
                            "start_offset": match_offset,
                        },
                    )
                )
        sources.sort(
            key=lambda source: (str(source.locator.get("created_at", "")), source.source_id)
        )
        cursor = body.cursor
        if cursor:
            try:
                raw: object = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
                saved = cast(list[object], raw) if isinstance(raw, list) else []
                if len(saved) != 2 or type(saved[0]) is not int or not isinstance(saved[1], str):
                    raise ValueError
                if not 0 < saved[0] <= len(sources):
                    raise ValueError
                sources, cursor = sources[: saved[0]], saved[1]
            except (ValueError, binascii.Error, UnicodeDecodeError):
                raise CodedHTTPException(
                    code="CONTEXT_CURSOR_INVALID",
                    status_code=409,
                    detail="查找游标无效，请重新查找",
                ) from None
        binding: list[object] = [
            session_id,
            segment,
            version,
            query,
            [(source.source_id, source.version) for source in sources],
        ]
        start = _offset(cursor, binding, len(sources))
        end = min(len(sources), start + body.limit)
        return ContextSearchOut(
            sources=sources[start:end],
            remaining=len(sources) - end,
            next_cursor=base64.urlsafe_b64encode(
                json.dumps([len(sources), _cursor(binding, end)]).encode()
            ).decode()
            if end < len(sources)
            else None,
        )


async def _legacy_message(
    session: AsyncSession, session_id: str, segment: int, target: str, cache: _ReadCache
) -> tuple[ToolMessage, AIMessage, str] | None:
    if target in cache.legacy or cache.exhausted:
        return cache.legacy.get(target)
    statement = (
        select(ChatModelRequest)
        .join(ChatTurn, ChatTurn.id == ChatModelRequest.turn_id)
        .join(ChatContextInput, ChatContextInput.turn_id == ChatTurn.id)
        .where(
            ChatTurn.session_id == session_id,
            ChatContextInput.segment == segment,
            ChatModelRequest.purpose == "ANSWER",
        )
        .order_by(ChatModelRequest.created_at.desc(), ChatModelRequest.id.desc())
    )
    if cache.before is not None:
        created_at, request_id = cache.before
        statement = statement.where(
            or_(
                ChatModelRequest.created_at < created_at,
                and_(ChatModelRequest.created_at == created_at, ChatModelRequest.id < request_id),
            )
        )
    requests = await session.stream_scalars(statement.execution_options(yield_per=1))
    try:
        async for request in requests:
            cache.before = request.created_at, request.id
            if not request.messages_json:
                continue
            messages = messages_from_dict(json.loads(request.messages_json))
            pairs: dict[str, AIMessage] = {}
            for message in messages:
                if isinstance(message, AIMessage):
                    for call in message.tool_calls:
                        if call["id"] is not None:
                            pairs.setdefault(call["id"], message)
            for message in messages:
                if isinstance(message, ToolMessage) and isinstance(message.content, str):
                    pair = pairs.get(message.tool_call_id)
                    if pair is not None:
                        identity = message.id or digest(
                            json.dumps(messages_to_dict([message]), ensure_ascii=False)
                        )
                        cache.legacy.setdefault(identity, (message, pair, request.turn_id))
            if target in cache.legacy:
                return cache.legacy[target]
        cache.exhausted = True
        return None
    finally:
        await requests.close()


async def read_context(
    factory: async_sessionmaker[AsyncSession],
    session_id: str,
    body: ContextReadRequest,
    *,
    _cache: _ReadCache | None = None,
) -> ContextReadOut:
    async with factory() as session:
        chat, segment, version = await _scope(session, session_id)
        kind, sep, target = body.source_id.partition(":")
        if not sep:
            kind, target = "message", body.source_id  # 摘要沿用已持久化的消息身份。
        source: ContextSourceOut | None = None
        content = ""
        if kind == "message":
            row = next(
                iter(await _messages(session, session_id, segment, target)),
                None,
            )
            if row:
                source, content = await _message_source(session, row, _cache), row.content
        elif kind == "output":
            row_output = next(
                iter(await _outputs(session, session_id, segment, target)),
                None,
            )
            if row_output:
                source, content = _output_source(row_output), row_output.content
        elif kind in ("record", "library"):
            title, content, source_version = await _read_material(
                session, chat, kind, target, _cache
            )
            source = ContextSourceOut(
                source_id=body.source_id,
                kind=kind,
                title=title[:120],
                version=source_version,
                locator={f"{kind}_id": target},
            )
        if source is None and kind == "message":
            # 压缩来源中的工具消息由已计量请求重建；不存在正文时绝不伪造。
            legacy = await _legacy_message(
                session, session_id, segment, target, _cache or _ReadCache()
            )
            if legacy is not None:
                message, pair, turn_id = legacy
                if message.name == "search_library":
                    await validate_evidence(
                        session, chat, json.loads(message.text).get("evidence_hits"), _cache
                    )
                source = ContextSourceOut(
                    source_id=body.source_id,
                    kind="message",
                    title=message.name or "tool",
                    version=digest(message.text),
                    turn_id=turn_id,
                    locator={
                        "tool_call_id": message.tool_call_id,
                        "paired_message_id": pair.id,
                        "tool": message.name,
                        "paired_tool_calls": json.dumps(pair.tool_calls, ensure_ascii=False),
                    },
                )
                content = message.text
        if source is None:
            raise CodedHTTPException(
                code="CONTEXT_SOURCE_UNAVAILABLE",
                status_code=404,
                detail="来源不属于当前会话或段，或旧记录未保存正文",
            )
        if body.version is not None and body.version != source.version:
            raise CodedHTTPException(
                code="CONTEXT_SOURCE_STALE",
                status_code=409,
                detail="来源版本已变化，请重新查找当前原文",
            )
        binding = [session_id, segment, version, source.source_id, source.version]
        start = _offset(body.cursor, binding, len(content))
        if body.cursor is None and body.quote:
            start = body.offset if body.offset is not None else content.find(body.quote)
            if start < 0 or content[start : start + len(body.quote)] != body.quote:
                raise CodedHTTPException(
                    code="CONTEXT_SOURCE_STALE",
                    status_code=409,
                    detail="命中摘录已不在当前原文中，请重新查找",
                )
            source.locator["quote"] = body.quote
        end = min(len(content), start + body.max_chars)
        source.locator.update({"start_offset": start, "end_offset": end})
        if kind == "record":
            segments = await RecordService.get_transcript_segments(session, target)
            # 时间/页码定位沿用现有分片，而非摘要自报的原文引用。
            by_id = {part.id: part for part in segments}
            for part_id, position, stop in LibraryRetrievalService.source_positions(
                content, [(part.id, part.content) for part in segments]
            ):
                if position <= start < stop:
                    part = by_id[part_id]
                    source.locator.update(
                        {"segment_id": part.id, "record_start_ms": part.record_start_ms}
                    )
                    break
            if "segment_id" not in source.locator:
                documents = await RecordService.get_document_segments(session, target)
                docs_by_id = {part.id: part for part in documents}
                for part_id, position, stop in LibraryRetrievalService.source_positions(
                    content, [(part.id, part.content) for part in documents]
                ):
                    if position <= start < stop:
                        document = docs_by_id[part_id]
                        source.locator.update(
                            {"segment_id": document.id, "page_no": document.page_no}
                        )
                        break
        return ContextReadOut(
            source=source,
            content=content[start:end],
            offset=start,
            remaining=len(content) - end,
            next_cursor=_cursor(binding, end) if end < len(content) else None,
        )


async def validate_read_results(
    factory: async_sessionmaker[AsyncSession], session_id: str, messages: list[AnyMessage]
) -> list[AnyMessage]:
    cache = _ReadCache()
    reads: dict[tuple[str, str | None], CodedHTTPException | None] = {}
    result: list[AnyMessage] = []
    for message in messages:
        if not isinstance(message, ToolMessage) or message.name not in (
            "read_context",
            "search_library",
        ):
            result.append(message)
            continue
        try:
            raw: object = json.loads(message.text)
        except ValueError:
            result.append(message)
            continue
        body = cast(dict[str, object], raw) if isinstance(raw, dict) else {}
        try:
            source = body.get("source")
            if message.name == "read_context" and isinstance(source, dict):
                source = cast(dict[str, object], source)
                request = ContextReadRequest.model_validate(
                    {
                        "source_id": source.get("source_id"),
                        "version": source.get("version"),
                        "max_chars": 1,
                    }
                )
                key = request.source_id, request.version
                if key not in reads:
                    try:
                        await read_context(factory, session_id, request, _cache=cache)
                        reads[key] = None
                    except CodedHTTPException as exc:
                        reads[key] = exc
                failure = reads[key]
                if failure is not None:
                    raise failure
            elif message.name == "search_library":
                async with factory() as session:
                    chat, _, _ = await _scope(session, session_id)
                    await validate_evidence(session, chat, body.get("evidence_hits"), cache)
        except CodedHTTPException as exc:
            # 只标记当前模型投影失效，不回写旧结果、回执或字符消费事实。
            message = message.model_copy(
                update={
                    "content": json.dumps(
                        {"ok": False, "error": exc.code, "message": "原文来源已失效，请重新查找。"},
                        ensure_ascii=False,
                    )
                }
            )
        result.append(message)
    return result
