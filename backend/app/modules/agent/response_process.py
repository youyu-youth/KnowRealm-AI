"""回答过程的展示事实；不调度任务、不重放业务操作。"""

import json

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.modules.agent.models import ChatResponseProcess
from app.modules.agent.schemas import (
    ChatProcessStatus,
    ChatProcessTool,
    ChatResponseProcessOut,
)


def process_out(row: ChatResponseProcess) -> ChatResponseProcessOut:
    return ChatResponseProcessOut.model_validate(
        {
            "id": row.id,
            "session_id": row.session_id,
            "user_message_id": row.user_message_id,
            "assistant_message_id": row.assistant_message_id,
            "status": row.status,
            "started_at": row.started_at,
            "updated_at": row.updated_at,
            "ended_at": row.ended_at,
            "elapsed_ms": row.elapsed_ms,
            "entries": json.loads(row.entries_json),
        }
    )


def finish_process(process: ChatResponseProcessOut, status: ChatProcessStatus) -> None:
    process.status = status
    process.ended_at = utcnow()
    for entry in process.entries:
        if isinstance(entry, ChatProcessTool) and entry.status == "RUNNING":
            entry.status = "INTERRUPTED"


async def save_process(session: AsyncSession, process: ChatResponseProcessOut) -> None:
    row = await session.get(ChatResponseProcess, process.id)
    if row is None:
        raise ValueError("chat response process missing")
    process.updated_at = process.ended_at or utcnow()
    process.elapsed_ms = max(
        0, round((process.updated_at - process.started_at).total_seconds() * 1000)
    )
    row.status = process.status
    row.assistant_message_id = process.assistant_message_id
    row.updated_at = process.updated_at
    row.ended_at = process.ended_at
    row.elapsed_ms = process.elapsed_ms
    row.entries_json = json.dumps(
        [entry.model_dump(mode="json") for entry in process.entries],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    await session.flush()


async def persist_process(
    session_factory: async_sessionmaker[AsyncSession], process: ChatResponseProcessOut
) -> None:
    try:
        async with session_factory() as session, session.begin():
            await save_process(session, process)
        process.history_saved = True
    except Exception:
        process.history_saved = False
        logger.error(
            "chat_process_save_failed", process_id=process.id, error_code="CHAT_PROCESS_SAVE_FAILED"
        )


async def recover_processes(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session, session.begin():
        rows = await session.scalars(
            select(ChatResponseProcess).where(ChatResponseProcess.status == "RUNNING")
        )
        for row in rows:
            process = process_out(row)
            process.status = "INTERRUPTED"
            process.ended_at = row.updated_at
            for entry in process.entries:
                if isinstance(entry, ChatProcessTool) and entry.status == "RUNNING":
                    entry.status = "INTERRUPTED"
            await save_process(session, process)
