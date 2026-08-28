import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.main import create_app
from app.services.chat_session_service import NEUTRAL_PROFILE_SNAPSHOT

TOKEN = "test-launch-token"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@asynccontextmanager
async def running_chat_app(
    data_dir: Path,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(data_dir=data_dir, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client


async def table_names(data_dir: Path) -> set[str]:
    async with aiosqlite.connect(data_dir / "knowrealm.db") as connection:
        return {
            cast(str, row[0])
            for row in await (
                await connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            ).fetchall()
        }


async def table_columns(data_dir: Path, table: str) -> set[str]:
    async with aiosqlite.connect(data_dir / "knowrealm.db") as connection:
        return {
            cast(str, row[1])
            for row in await (await connection.execute(f"PRAGMA table_info({table})")).fetchall()
        }


async def message_rows(data_dir: Path, session_id: str) -> list[tuple[str, str]]:
    async with aiosqlite.connect(data_dir / "knowrealm.db") as connection:
        return [
            (cast(str, row[0]), cast(str, row[1]))
            for row in await (
                await connection.execute(
                    "SELECT role, content FROM chat_messages"
                    " WHERE session_id = ? ORDER BY created_at, id",
                    (session_id,),
                )
            ).fetchall()
        ]


async def session_row(data_dir: Path, session_id: str) -> tuple[str | None, str | None]:
    async with aiosqlite.connect(data_dir / "knowrealm.db") as connection:
        row = await (
            await connection.execute(
                "SELECT title, deleted_at FROM chat_sessions WHERE id = ?", (session_id,)
            )
        ).fetchone()
    assert row is not None
    return cast("tuple[str | None, str | None]", row)


@pytest.mark.anyio
async def test_migration_0014_creates_chat_tables_and_advances_user_version(
    tmp_path: Path,
) -> None:
    async with running_chat_app(tmp_path) as (_app, _client):
        async with aiosqlite.connect(tmp_path / "knowrealm.db") as connection:
            version = await (await connection.execute("PRAGMA user_version")).fetchone()

        assert version == (14,)

        tables = await table_names(tmp_path)
        assert {"profile", "chat_sessions", "chat_messages"} <= tables
        assert await table_columns(tmp_path, "chat_sessions") >= {
            "course_id",
            "record_id",
            "concept_id",
            "mode",
            "title",
            "created_at",
            "updated_at",
            "deleted_at",
        }
        # chat_messages 是追加型事实表：没有软删列。
        assert "deleted_at" not in await table_columns(tmp_path, "chat_messages")


@pytest.mark.anyio
async def test_create_free_chat_without_profile_snapshots_neutral_system_message(
    tmp_path: Path,
) -> None:
    async with running_chat_app(tmp_path) as (_app, client):
        created = await client.post("/api/chat-sessions", json={})

        assert created.status_code == 201
        body = created.json()
        assert body["mode"] == "ASK"
        assert body["title"] is None
        assert body["record_id"] is None
        assert body["course_id"] is None

        rows = await message_rows(tmp_path, body["id"])
        assert rows == [("SYSTEM", NEUTRAL_PROFILE_SNAPSHOT)]


@pytest.mark.anyio
async def test_create_free_chat_after_profile_snapshots_role_and_about_me(
    tmp_path: Path,
) -> None:
    async with running_chat_app(tmp_path) as (_app, client):
        saved = await client.put(
            "/api/profile",
            json={"primary_role": "DEVELOPER", "about_me": "三年后端，正在补操作系统基础"},
        )
        assert saved.status_code == 200

        created = await client.post("/api/chat-sessions", json={})
        assert created.status_code == 201

        rows = await message_rows(tmp_path, created.json()["id"])
        assert len(rows) == 1
        role, content = rows[0]
        assert role == "SYSTEM"
        assert "程序员" in content
        assert "三年后端，正在补操作系统基础" in content


@pytest.mark.anyio
async def test_list_orders_by_updated_at_desc_and_rename_moves_session_to_top(
    tmp_path: Path,
) -> None:
    async with running_chat_app(tmp_path) as (_app, client):
        first = (await client.post("/api/chat-sessions", json={})).json()
        await asyncio.sleep(0.01)
        second = (await client.post("/api/chat-sessions", json={})).json()

        initial = await client.get("/api/chat-sessions")
        assert [item["id"] for item in initial.json()] == [second["id"], first["id"]]

        renamed = await client.patch(
            f"/api/chat-sessions/{first['id']}", json={"title": "操作系统答疑"}
        )
        assert renamed.status_code == 200
        assert renamed.json()["title"] == "操作系统答疑"

        after_rename = await client.get("/api/chat-sessions")
        assert [item["id"] for item in after_rename.json()] == [first["id"], second["id"]]
        assert after_rename.json()[0]["title"] == "操作系统答疑"


@pytest.mark.anyio
async def test_delete_soft_deletes_session_but_keeps_rows(tmp_path: Path) -> None:
    async with running_chat_app(tmp_path) as (_app, client):
        created = await client.post("/api/chat-sessions", json={})
        session_id = created.json()["id"]

        deleted = await client.delete(f"/api/chat-sessions/{session_id}")
        assert deleted.status_code == 204

        listed = await client.get("/api/chat-sessions")
        assert listed.json() == []

        detail = await client.get(f"/api/chat-sessions/{session_id}")
        assert detail.status_code == 404

        # 软删：会话行仍在（deleted_at 已置），SYSTEM 快照消息不动。
        title, deleted_at = await session_row(tmp_path, session_id)
        assert title is None
        assert deleted_at is not None
        assert await message_rows(tmp_path, session_id) != []


@pytest.mark.anyio
async def test_create_rejects_unsupported_mode_and_rename_validates_title(
    tmp_path: Path,
) -> None:
    async with running_chat_app(tmp_path) as (_app, client):
        unsupported = await client.post("/api/chat-sessions", json={"mode": "COURSE_QA"})
        assert unsupported.status_code == 422

        blank = await client.patch(
            "/api/chat-sessions/00000000-0000-4000-8000-000000000000",
            json={"title": "   "},
        )
        assert blank.status_code == 422

        missing = await client.patch(
            "/api/chat-sessions/00000000-0000-4000-8000-000000000000",
            json={"title": "不存在的会话"},
        )
        assert missing.status_code == 404
