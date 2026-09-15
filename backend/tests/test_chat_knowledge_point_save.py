"""对话转知识点 V1（对话转学习资产）：保存端点、锚点/链接落库、事件零污染与回溯读。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast
from uuid import uuid4

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.db.base import utcnow
from app.main import create_app
from app.modules.agent.models import ChatMessage, ChatRole

TOKEN = "test-launch-token"

SAVE_BODY = {
    "name": "AOF 持久化",
    "detail": "AOF 以追加写方式记录每条写命令，数据丢失窗口较小。",
    "tags": ["Redis"],
    "importance": 4,
}


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


async def scalar(data_dir: Path, sql: str, *params: object) -> object:
    async with aiosqlite.connect(data_dir / "knowrealm.db") as connection:
        row = await (await connection.execute(sql, params)).fetchone()
    assert row is not None
    return cast(object, row[0])


async def make_coursed_record(client: httpx.AsyncClient) -> tuple[str, str]:
    """造一门课 + 一条已归类（含转写）的学习记录。"""
    course = await client.post(
        "/api/courses",
        json={"name": "Redis", "learning_context": "INTEREST", "depth": "BEGINNER"},
    )
    assert course.status_code == 201
    course_id = cast(str, course.json()["id"])
    capture = await client.post(
        "/api/text-captures",
        json={"capture_type": "PASTE", "content": "AOF 与 RDB 的取舍", "course_id": course_id},
    )
    assert capture.status_code == 201
    return course_id, cast(str, capture.json()["record_id"])


async def insert_message(app: FastAPI, session_id: str, role: ChatRole, content: str) -> str:
    message_id = str(uuid4())
    async with app.state.session_factory() as db, db.begin():
        db.add(
            ChatMessage(
                id=message_id,
                session_id=session_id,
                role=role,
                content=content,
                citations_json=None,
                model=None,
                token_usage_json=None,
                created_at=utcnow(),
            )
        )
    return message_id


async def save(
    client: httpx.AsyncClient, session_id: str, message_id: str, record_id: str
) -> httpx.Response:
    return await client.post(
        f"/api/chat-sessions/{session_id}/messages/{message_id}/knowledge-points",
        json={**SAVE_BODY, "target_record_id": record_id},
    )


@pytest.mark.anyio
async def test_save_assistant_message_creates_kp_anchor_link_without_events(
    tmp_path: Path,
) -> None:
    async with running_chat_app(tmp_path) as (app, client):
        course_id, record_id = await make_coursed_record(client)
        created = await client.post("/api/chat-sessions", json={"record_id": record_id})
        assert created.status_code == 201
        session_id = cast(str, created.json()["id"])
        message_id = await insert_message(app, session_id, ChatRole.ASSISTANT, "AOF 讲解……")

        saved = await save(client, session_id, message_id, record_id)

        assert saved.status_code == 201
        body = saved.json()
        kp_id = body["id"]
        assert body["record_id"] == record_id
        assert body["generation_status"] == "ACTIVE"
        assert body["batch_id"] is None

        # 同事务落锚点与链接：CHAT_MESSAGE 锚点指向原消息，PRIMARY 链接挂知识点。
        assert (
            await scalar(
                tmp_path,
                "SELECT count(*) FROM source_anchors"
                " WHERE source_type = 'CHAT_MESSAGE' AND source_id = ?"
                " AND record_id = ? AND course_id = ?",
                message_id,
                record_id,
                course_id,
            )
            == 1
        )
        assert (
            await scalar(
                tmp_path,
                "SELECT count(*) FROM source_anchor_links"
                " WHERE resource_type = 'KNOWLEDGE_POINT' AND resource_id = ?"
                " AND relation_type = 'PRIMARY'",
                kp_id,
            )
            == 1
        )
        # AI 辅助沉淀不是掌握证据：零学习事件；搜索索引同事务同步。
        assert await scalar(tmp_path, "SELECT count(*) FROM learning_events") == 0
        assert (
            await scalar(
                tmp_path,
                "SELECT count(*) FROM search_index WHERE entity_id = ?",
                kp_id,
            )
            == 1
        )


@pytest.mark.anyio
async def test_read_returns_chat_source_only_for_saved_knowledge_point(
    tmp_path: Path,
) -> None:
    async with running_chat_app(tmp_path) as (app, client):
        _course_id, record_id = await make_coursed_record(client)
        created = await client.post("/api/chat-sessions", json={"record_id": record_id})
        session_id = cast(str, created.json()["id"])
        message_id = await insert_message(app, session_id, ChatRole.ASSISTANT, "AOF 讲解……")
        assert (await save(client, session_id, message_id, record_id)).status_code == 201
        manual = await client.post(
            f"/api/records/{record_id}/knowledge-points",
            json={**SAVE_BODY, "name": "手工知识点"},
        )
        assert manual.status_code == 201

        read = await client.get(f"/api/records/{record_id}/knowledge-points")

        assert read.status_code == 200
        chat_sources = {item["name"]: item.get("chat_source") for item in read.json()["items"]}
        assert len(chat_sources) == 2
        assert chat_sources[SAVE_BODY["name"]] == {"chat_session_id": session_id}
        assert chat_sources["手工知识点"] is None


@pytest.mark.anyio
async def test_manual_knowledge_point_has_no_chat_source(
    tmp_path: Path,
) -> None:
    async with running_chat_app(tmp_path) as (_app, client):
        _course_id, record_id = await make_coursed_record(client)
        manual = await client.post(f"/api/records/{record_id}/knowledge-points", json=SAVE_BODY)
        assert manual.status_code == 201

        read = await client.get(f"/api/records/{record_id}/knowledge-points")

        items = read.json()["items"]
        assert len(items) == 1
        assert items[0]["chat_source"] is None


@pytest.mark.anyio
async def test_save_from_free_session_to_coursed_record(tmp_path: Path) -> None:
    async with running_chat_app(tmp_path) as (app, client):
        _course_id, record_id = await make_coursed_record(client)
        created = await client.post("/api/chat-sessions", json={})
        session_id = cast(str, created.json()["id"])
        message_id = await insert_message(app, session_id, ChatRole.ASSISTANT, "自由问答……")

        saved = await save(client, session_id, message_id, record_id)

        assert saved.status_code == 201
        assert saved.json()["record_id"] == record_id


@pytest.mark.anyio
async def test_save_rejects_missing_session_message_and_user_role(tmp_path: Path) -> None:
    async with running_chat_app(tmp_path) as (app, client):
        _course_id, record_id = await make_coursed_record(client)
        created = await client.post("/api/chat-sessions", json={"record_id": record_id})
        session_id = cast(str, created.json()["id"])
        other = await client.post("/api/chat-sessions", json={"record_id": record_id})
        other_session_id = cast(str, other.json()["id"])
        assistant_id = await insert_message(app, session_id, ChatRole.ASSISTANT, "回答")
        user_id = await insert_message(app, session_id, ChatRole.USER, "提问")
        missing = str(uuid4())

        absent_session = await client.post(
            f"/api/chat-sessions/{missing}/messages/{assistant_id}/knowledge-points",
            json={**SAVE_BODY, "target_record_id": record_id},
        )
        assert absent_session.status_code == 404
        assert absent_session.json()["code"] == "CHAT_SESSION_NOT_FOUND"

        absent_message = await client.post(
            f"/api/chat-sessions/{session_id}/messages/{missing}/knowledge-points",
            json={**SAVE_BODY, "target_record_id": record_id},
        )
        assert absent_message.status_code == 404
        assert absent_message.json()["code"] == "CHAT_MESSAGE_NOT_FOUND"

        foreign = await client.post(
            f"/api/chat-sessions/{other_session_id}/messages/{assistant_id}/knowledge-points",
            json={**SAVE_BODY, "target_record_id": record_id},
        )
        assert foreign.status_code == 404
        assert foreign.json()["code"] == "CHAT_MESSAGE_NOT_FOUND"

        user_role = await save(client, session_id, user_id, record_id)
        assert user_role.status_code == 409
        assert user_role.json()["code"] == "CHAT_MESSAGE_NOT_ASSISTANT"

        deleted = await client.delete(f"/api/chat-sessions/{session_id}")
        assert deleted.status_code == 204
        after_delete = await save(client, session_id, assistant_id, record_id)
        assert after_delete.status_code == 404
        assert after_delete.json()["code"] == "CHAT_SESSION_NOT_FOUND"


@pytest.mark.anyio
async def test_save_rejects_unfiled_target_record(tmp_path: Path) -> None:
    async with running_chat_app(tmp_path) as (app, client):
        capture = await client.post(
            "/api/text-captures",
            json={"capture_type": "QUICK_NOTE", "content": "未归类速记"},
        )
        inbox_record_id = cast(str, capture.json()["record_id"])
        created = await client.post("/api/chat-sessions", json={})
        session_id = cast(str, created.json()["id"])
        message_id = await insert_message(app, session_id, ChatRole.ASSISTANT, "回答")

        saved = await save(client, session_id, message_id, inbox_record_id)

        assert saved.status_code == 409
        assert saved.json()["code"] == "RECORD_COURSE_MISSING"
        assert await scalar(tmp_path, "SELECT count(*) FROM knowledge_points") == 0


@pytest.mark.anyio
async def test_save_same_message_twice_creates_two_independent_rows(tmp_path: Path) -> None:
    async with running_chat_app(tmp_path) as (app, client):
        _course_id, record_id = await make_coursed_record(client)
        created = await client.post("/api/chat-sessions", json={"record_id": record_id})
        session_id = cast(str, created.json()["id"])
        message_id = await insert_message(app, session_id, ChatRole.ASSISTANT, "回答")

        first = await save(client, session_id, message_id, record_id)
        second = await save(client, session_id, message_id, record_id)

        assert first.status_code == 201 and second.status_code == 201
        assert first.json()["id"] != second.json()["id"]
        assert await scalar(tmp_path, "SELECT count(*) FROM source_anchors") == 2
        assert await scalar(tmp_path, "SELECT count(*) FROM source_anchor_links") == 2


@pytest.mark.anyio
async def test_save_validates_write_request_boundaries(tmp_path: Path) -> None:
    async with running_chat_app(tmp_path) as (app, client):
        _course_id, record_id = await make_coursed_record(client)
        created = await client.post("/api/chat-sessions", json={"record_id": record_id})
        session_id = cast(str, created.json()["id"])
        message_id = await insert_message(app, session_id, ChatRole.ASSISTANT, "回答")

        invalid = await client.post(
            f"/api/chat-sessions/{session_id}/messages/{message_id}/knowledge-points",
            json={
                "name": "  ",
                "detail": "x",
                "tags": [],
                "importance": 3,
                "target_record_id": record_id,
            },
        )
        assert invalid.status_code == 422

        unknown_record = str(uuid4())
        missing_record = await client.post(
            f"/api/chat-sessions/{session_id}/messages/{message_id}/knowledge-points",
            json={**SAVE_BODY, "target_record_id": unknown_record},
        )
        assert missing_record.status_code == 404
        assert missing_record.json()["code"] == "RECORD_NOT_FOUND"


@pytest.mark.anyio
async def test_anchor_link_failure_rolls_back_knowledge_point(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with running_chat_app(tmp_path) as (app, client):
        _course_id, record_id = await make_coursed_record(client)
        created = await client.post("/api/chat-sessions", json={"record_id": record_id})
        session_id = cast(str, created.json()["id"])
        message_id = await insert_message(app, session_id, ChatRole.ASSISTANT, "回答")

        async def broken_link(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("link write failed")

        monkeypatch.setattr(
            "app.modules.knowledge_point.service.SourceAnchorService.link_resource",
            broken_link,
        )

        failed = await save(client, session_id, message_id, record_id)

        assert failed.status_code == 500
        # 同事务红线：链接失败时知识点与锚点一并回滚（记录索引行不受影响）。
        assert await scalar(tmp_path, "SELECT count(*) FROM knowledge_points") == 0
        assert await scalar(tmp_path, "SELECT count(*) FROM source_anchors") == 0
        assert (
            await scalar(
                tmp_path,
                "SELECT count(*) FROM search_index WHERE entity_type = 'knowledge_point'",
            )
            == 0
        )
