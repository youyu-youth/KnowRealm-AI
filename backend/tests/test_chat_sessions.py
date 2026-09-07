import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import update

from app.db.base import utcnow
from app.main import create_app
from app.modules.chat.session_service import NEUTRAL_PROFILE_SNAPSHOT
from app.modules.settings.config import save_llm_provider
from app.modules.transcript.models import Transcript

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

        assert version == (18,)

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
async def test_create_mounted_chat_keeps_record_course_without_profile_snapshot(
    tmp_path: Path,
) -> None:
    async with running_chat_app(tmp_path) as (_app, client):
        course = await client.post(
            "/api/courses",
            json={"name": "数学", "learning_context": "INTEREST", "depth": "BEGINNER"},
        )
        assert course.status_code == 201
        for course_id in (None, course.json()["id"]):
            capture = await client.post(
                "/api/text-captures",
                json={"capture_type": "PASTE", "content": "公式 x+y", "course_id": course_id},
            )
            assert capture.status_code == 201
            record_id = capture.json()["record_id"]
            created = await client.post("/api/chat-sessions", json={"record_id": record_id})
            assert created.status_code == 201
            assert created.json()["record_id"] == record_id
            assert created.json()["course_id"] == course_id
            assert await message_rows(tmp_path, created.json()["id"]) == []

        invalid = await client.post("/api/chat-sessions", json={"record_id": "invalid"})
        assert invalid.status_code == 422
        missing = await client.post(
            "/api/chat-sessions", json={"record_id": "00000000-0000-4000-8000-000000000000"}
        )
        assert missing.status_code == 404


@pytest.mark.anyio
async def test_mount_options_include_inbox_disable_missing_transcript_and_hide_deleted(
    tmp_path: Path,
) -> None:
    async with running_chat_app(tmp_path) as (app, client):
        record_ids: list[str] = []
        for title in ("收件箱速记", "还没有转写", "已删除记录"):
            response = await client.post(
                "/api/text-captures", json={"capture_type": "QUICK_NOTE", "content": title}
            )
            record_ids.append(response.json()["record_id"])
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                update(Transcript)
                .where(Transcript.record_id == record_ids[1])
                .values(deleted_at=utcnow())
            )
        await client.delete(f"/api/records/{record_ids[2]}")

        options = await client.get("/api/chat-sessions/record-options")
        assert options.status_code == 200
        by_id = {item["id"]: item for item in options.json()}
        assert set(by_id) == set(record_ids[:2])
        assert by_id[record_ids[0]]["has_transcript"] is True
        assert by_id[record_ids[0]]["course_id"] is None
        assert by_id[record_ids[1]]["has_transcript"] is False
        rejected = await client.post("/api/chat-sessions", json={"record_id": record_ids[1]})
        assert rejected.status_code == 409 and "TRANSCRIPT_NOT_READY" in rejected.json()["detail"]
        deleted = await client.post("/api/chat-sessions", json={"record_id": record_ids[2]})
        assert deleted.status_code == 404

        created = await client.post("/api/chat-sessions", json={"record_id": record_ids[0]})
        session_id = created.json()["id"]
        changed = await client.patch(
            f"/api/chat-sessions/{session_id}", json={"title": "新标题", "record_id": None}
        )
        assert changed.status_code == 422
        assert (await client.get(f"/api/chat-sessions/{session_id}")).json()[
            "record_id"
        ] == record_ids[0]


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
async def test_list_orders_by_updated_at_desc_and_rename_keeps_position(
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

        # 重命名只改标题，不推进 updated_at：列表"最近更新"仍是会话活跃度。
        after_rename = await client.get("/api/chat-sessions")
        assert [item["id"] for item in after_rename.json()] == [second["id"], first["id"]]
        assert after_rename.json()[1]["title"] == "操作系统答疑"


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


@pytest.mark.anyio
async def test_deleted_mount_record_marks_session_invalid_and_rejects_send(
    tmp_path: Path,
) -> None:
    # accept 先校验供应商，需已配置才能走到失效态校验。
    save_llm_provider(
        tmp_path,
        base_url="https://stub.example.com/v1",
        api_key="sk-test",
        model="stub-chat-model",
        clear_api_key=False,
    )
    async with running_chat_app(tmp_path) as (_app, client):
        capture = await client.post(
            "/api/text-captures", json={"capture_type": "QUICK_NOTE", "content": "原始内容"}
        )
        record_id = capture.json()["record_id"]
        free = await client.post("/api/chat-sessions", json={})
        assert free.json()["record_deleted"] is False
        created = await client.post("/api/chat-sessions", json={"record_id": record_id})
        session_id = created.json()["id"]
        assert created.json()["record_deleted"] is False

        deleted = await client.delete(f"/api/records/{record_id}")
        assert deleted.status_code == 204

        # 列表与详情标记失效；自由聊天不受影响；会话保留可读。
        listed = await client.get("/api/chat-sessions")
        by_id = {item["id"]: item for item in listed.json()}
        assert by_id[session_id]["record_deleted"] is True
        assert by_id[free.json()["id"]]["record_deleted"] is False
        detail = await client.get(f"/api/chat-sessions/{session_id}")
        assert detail.status_code == 200
        assert detail.json()["record_deleted"] is True
        history = await client.get(f"/api/chat-sessions/{session_id}/messages")
        assert history.status_code == 200

        # 失效会话发送返回语义化冲突错误，不落 user 行。
        rejected = await client.post(
            f"/api/chat-sessions/{session_id}/messages", json={"content": "还能问吗"}
        )
        assert rejected.status_code == 409
        assert "CHAT_RECORD_UNAVAILABLE" in rejected.json()["detail"]
        assert await message_rows(tmp_path, session_id) == []
