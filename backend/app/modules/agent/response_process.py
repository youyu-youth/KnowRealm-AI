"""回答过程的展示事实；不调度任务、不重放业务操作。

旧执行路径的运行期持久化已随 ChatTurn 迁移移除（票 01）；本模块保留旧行
只读投影与启动恢复（历史过程仍可查），新轮次过程由 turns.projection 投影。
"""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.modules.agent.models import ChatResponseProcess
from app.modules.agent.schemas import (
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
