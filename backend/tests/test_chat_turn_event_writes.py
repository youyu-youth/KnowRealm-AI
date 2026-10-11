import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import create_database
from app.db.migrations import run_migrations
from app.modules.agent.models import ChatMessage, ChatSession
from app.modules.agent.turns.models import ChatTurn, ChatTurnEvent
from app.modules.agent.turns.service import ChatTurnService


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_concurrent_token_and_tool_flush_keep_unique_sequences(tmp_path: Path) -> None:
    """定时 token 刷新与工具事件刷新重叠时，两批事件都必须提交。"""
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    engine, factory = create_database(db_path)
    try:
        async with factory() as session, session.begin():
            session.add(ChatSession(id="chat", mode="ASK", scope="ALL"))
            await session.flush()
            session.add(ChatMessage(id="user", session_id="chat", role="USER", content="q"))
            await session.flush()
            session.add(
                ChatTurn(
                    id="turn",
                    session_id="chat",
                    user_message_id="user",
                    request_id="request",
                    request_fingerprint="fingerprint",
                    status="RUNNING",
                    claim_token="claim",
                )
            )

        both_read = asyncio.Event()
        readers = 0

        class OverlappingSession(AsyncSession):
            async def get(self, entity: Any, ident: Any, **kwargs: Any) -> Any:
                nonlocal readers
                row = await super().get(entity, ident, **kwargs)
                if entity is ChatTurn:
                    readers += 1
                    if readers == 2:
                        both_read.set()
                    await asyncio.wait_for(both_read.wait(), timeout=5)
                return row

        overlapping_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            engine, class_=OverlappingSession, expire_on_commit=False
        )
        batches = [
            [{"type": "token", "payload": {"text": "共 13 门课程"}}],
            [
                {
                    "type": "tool_call",
                    "tool_call_id": "call-goals",
                    "payload": {"tool": "list_goals", "tool_call_id": "call-goals"},
                }
            ],
        ]
        cursors = await asyncio.gather(
            *(
                ChatTurnService.append_events(
                    session_factory=overlapping_factory,
                    turn_id="turn",
                    claim_token="claim",
                    rows=batch,
                )
                for batch in batches
            )
        )
        assert None not in cursors
        assert sorted(cursor for cursor in cursors if cursor is not None) == [1, 2]
        async with factory() as session:
            turn = await session.get(ChatTurn, "turn")
            assert turn is not None and turn.status == "RUNNING" and turn.last_seq == 2
            events = list(
                (await session.scalars(select(ChatTurnEvent).order_by(ChatTurnEvent.seq))).all()
            )
            assert [event.seq for event in events] == [1, 2]
            assert {event.type for event in events} == {"token", "tool_call"}
            assert any(json.loads(event.payload_json).get("text") for event in events)
        # 迟到执行仍须拒绝，不能因序号分配改造绕过领取身份与终态保护。
        for claim in ("stale-claim", "claim"):
            if claim == "claim":
                async with factory() as session, session.begin():
                    turn = await session.get(ChatTurn, "turn")
                    assert turn is not None
                    turn.status = "COMPLETED"
            assert (
                await ChatTurnService.append_events(
                    session_factory=factory, turn_id="turn", claim_token=claim, rows=batches[0]
                )
                is None
            )
    finally:
        await engine.dispose()
