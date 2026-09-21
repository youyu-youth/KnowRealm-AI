"""资料库 V1 工单 06 测试：Learner Memory 端点契约、MEMORY 提案闭环与硬门禁。

零容忍硬门禁（spec/ADR-0025）各至少一个失败即红的用例：未经确认零写入、
关闭外发后零注入（零发送）、删除后零再次注入、Course 状态零越界注入、
观察偏好零覆盖显式偏好。端点契约走完整 app；聚合与工具直调 service 层。
"""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import create_database
from app.db.migrations import run_migrations
from app.main import create_app
from app.modules.agent.message_service import ChatMessageService, ChatStreamRegistry
from app.modules.agent.runtime import (
    AgentRuntimeContext,
    bind_agent_runtime_context,
    reset_agent_runtime_context,
)
from app.modules.agent.tools.propose_memory import propose_memory
from app.modules.learner.service import build_learner_context
from app.modules.library.proposals import ProposalService
from app.modules.library.schemas import ChatScope
from app.modules.settings.config import save_llm_provider

TOKEN = "test-launch-token"
NOW = "2026-09-20T08:00:00.000000Z"
COURSE_A = "c0000000-0000-4000-8000-00000000000a"
COURSE_B = "c0000000-0000-4000-8000-00000000000b"
CONCEPT_A_WEAK = "c0000000-0000-4000-8000-00000000001a"
CONCEPT_A_OK = "c0000000-0000-4000-8000-00000000001b"
CONCEPT_B_ONLY = "c0000000-0000-4000-8000-00000000002a"


@asynccontextmanager
async def bare_db(tmp_path: Path) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    _engine, session_factory = create_database(db_path)
    try:
        yield session_factory
    finally:
        await _engine.dispose()


@asynccontextmanager
async def running_app(
    tmp_path: Path,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient, async_sessionmaker[AsyncSession], Path]]:
    data_dir = tmp_path / "KnowRealm"
    app = create_app(data_dir=data_dir, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client, app.state.session_factory, data_dir


async def insert(
    sql: str, params: dict[str, object], session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(text(sql), params)


async def seed_course(session_factory: async_sessionmaker[AsyncSession], course_id: str) -> None:
    await insert(
        "INSERT INTO courses (id, name, learning_context, depth, status, created_at, "
        "updated_at) VALUES (:id, :name, 'INTEREST', 'INTERMEDIATE', 'ACTIVE', :now, :now)",
        {"id": course_id, "name": f"课程{course_id[-1]}", "now": NOW},
        session_factory,
    )


async def seed_mastery(
    session_factory: async_sessionmaker[AsyncSession],
    course_id: str,
    concept_id: str,
    name: str,
    *,
    score: float | None,
) -> None:
    await insert(
        "INSERT INTO concepts (id, course_id, canonical_name, normalized_name, status, "
        "created_at, updated_at) VALUES (:id, :course_id, :name, :norm, 'CONFIRMED', :now, :now)",
        {"id": concept_id, "course_id": course_id, "name": name, "norm": name.lower(), "now": NOW},
        session_factory,
    )
    if score is not None:
        await insert(
            "INSERT INTO user_concept_mastery (id, course_id, concept_id, mastery_score, "
            "mastery_confidence, algorithm_version, updated_at) VALUES (:id, :course_id, "
            ":concept_id, :score, 0.8, 'test', :now)",
            {
                "id": concept_id + "-m",
                "course_id": course_id,
                "concept_id": concept_id,
                "score": score,
                "now": NOW,
            },
            session_factory,
        )


async def create_memory_proposal(
    client: httpx.AsyncClient, payload: dict[str, object]
) -> dict[str, object]:
    response = await client.post(
        "/api/proposals",
        json={"proposal_type": "MEMORY", "payload": payload},
    )
    assert response.status_code == 201, response.text
    return cast_dict(response.json())


def cast_dict(value: object) -> dict[str, object]:
    return cast("dict[str, object]", value)


@pytest.mark.anyio
async def test_get_preferences_default_empty(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (_app, client, _sf, _data_dir):
        response = await client.get("/api/learner/preferences")
        assert response.status_code == 200
        body = cast_dict(response.json())
        assert body["explicit_items"] == []
        assert body["observed_entries"] == {}
        assert body["observed_confidence"] is None
        assert body["evidence_count"] == 0
        outbound = cast_dict(body["memory_outbound"])
        # 默认开启外发；但测试目录无供应商配置，同意恒为未授予/失效。
        assert outbound["enabled"] is True
        assert outbound["consent_granted_at"] is None
        assert outbound["consent_current"] is False


@pytest.mark.anyio
async def test_put_preferences_replaces_and_dedupes(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (_app, client, _sf, _data_dir):
        response = await client.put(
            "/api/learner/preferences",
            json={"items": [" 先看例题 ", "先看例题", "多给反例"]},
        )
        assert response.status_code == 200
        body = cast_dict(response.json())
        assert body["explicit_items"] == ["先看例题", "多给反例"]
        # PUT 只动显式偏好：第二次替换后旧条目不残留。
        response = await client.put("/api/learner/preferences", json={"items": ["放慢语速"]})
        assert cast_dict(response.json())["explicit_items"] == ["放慢语速"]


@pytest.mark.anyio
async def test_put_preferences_validation(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (_app, client, _sf, _data_dir):
        # 纯空白条目被 strip 校验拒绝（min_length=1 作用于 strip 后值）。
        response = await client.put("/api/learner/preferences", json={"items": ["  "]})
        assert response.status_code == 422
        # 正常单条放行。
        response = await client.put("/api/learner/preferences", json={"items": ["偏好一"]})
        assert response.status_code == 200


@pytest.mark.anyio
async def test_memory_outbound_toggle_persists(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (_app, client, _sf, data_dir):
        response = await client.put("/api/learner/memory-outbound", json={"enabled": False})
        assert response.status_code == 200
        body = cast_dict(response.json())
        assert body["enabled"] is False
        # 关闭落 settings.json 偏离项键。
        settings = json.loads((data_dir / "config" / "settings.json").read_text("utf-8"))
        assert settings["learner_memory_outbound_enabled"] is False
        # 再开启：回到默认值，键被删除（settings.json 只存偏离项）。
        response = await client.put("/api/learner/memory-outbound", json={"enabled": True})
        assert cast_dict(response.json())["enabled"] is True
        settings = json.loads((data_dir / "config" / "settings.json").read_text("utf-8"))
        assert "learner_memory_outbound_enabled" not in settings


@pytest.mark.anyio
async def test_memory_proposal_unconfirmed_writes_nothing(tmp_path: Path) -> None:
    """硬门禁：未经确认零写入——提案创建后 learner_preferences 零行零变化。"""
    async with running_app(tmp_path) as (_app, client, session_factory, _data_dir):
        proposal = await create_memory_proposal(client, {"kind": "EXPLICIT", "items": ["先看例题"]})
        assert proposal["status"] == "PENDING"
        async with session_factory() as session:
            rows = (
                await session.execute(text("SELECT id FROM learner_preferences WHERE id = 'me'"))
            ).all()
        # 创建提案不改事实：单例行都不惰性创建。
        assert rows == []
        # 确认后才写入。
        response = await client.post(f"/api/proposals/{proposal['id']}/confirm")
        assert response.status_code == 200
        assert cast_dict(response.json())["status"] == "APPLIED"
        read = await client.get("/api/learner/preferences")
        assert cast_dict(read.json())["explicit_items"] == ["先看例题"]


@pytest.mark.anyio
async def test_memory_proposal_reject_changes_nothing(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (_app, client, _sf, _data_dir):
        proposal = await create_memory_proposal(client, {"kind": "EXPLICIT", "items": ["先看例题"]})
        response = await client.post(f"/api/proposals/{proposal['id']}/reject")
        assert response.status_code == 200
        read = await client.get("/api/learner/preferences")
        body = cast_dict(read.json())
        assert body["explicit_items"] == []
        assert body["observed_entries"] == {}


@pytest.mark.anyio
async def test_observed_proposal_never_overwrites_explicit(tmp_path: Path) -> None:
    """硬门禁：观察偏好零覆盖显式——OBSERVED 确认后显式列逐字节不变。"""
    async with running_app(tmp_path) as (_app, client, session_factory, _data_dir):
        await client.put("/api/learner/preferences", json={"items": ["先看例题"]})
        async with session_factory() as session:
            explicit_before = (
                await session.execute(
                    text("SELECT user_selected_preference FROM learner_preferences")
                )
            ).scalar_one()
        proposal = await create_memory_proposal(
            client,
            {
                "kind": "OBSERVED",
                "entries": {"解释风格": "偏好例子先行"},
                "confidence": 0.82,
                "evidence_count": 12,
            },
        )
        response = await client.post(f"/api/proposals/{proposal['id']}/confirm")
        assert response.status_code == 200
        async with session_factory() as session:
            explicit_after = (
                await session.execute(
                    text("SELECT user_selected_preference FROM learner_preferences")
                )
            ).scalar_one()
        assert explicit_after == explicit_before
        body = cast_dict((await client.get("/api/learner/preferences")).json())
        assert body["explicit_items"] == ["先看例题"]
        assert body["observed_entries"] == {"解释风格": "偏好例子先行"}
        assert body["observed_confidence"] == 0.82
        assert body["evidence_count"] == 12
        assert body["last_observed_at"] is not None


@pytest.mark.anyio
async def test_delete_observed_removes_entry_only(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (_app, client, session_factory, _data_dir):
        proposal = await create_memory_proposal(
            client,
            {
                "kind": "OBSERVED",
                "entries": {"复习时段": "晚上", "笔记习惯": "结构化"},
                "confidence": 0.6,
                "evidence_count": 3,
            },
        )
        confirm = await client.post(f"/api/proposals/{proposal['id']}/confirm")
        assert confirm.status_code == 200
        response = await client.delete("/api/learner/preferences/observed/复习时段")
        assert response.status_code == 204
        body = cast_dict((await client.get("/api/learner/preferences")).json())
        assert body["observed_entries"] == {"笔记习惯": "结构化"}
        # 未知键 404（稳定错误码）。
        response = await client.delete("/api/learner/preferences/observed/不存在")
        assert response.status_code == 404
        assert cast_dict(response.json())["code"] == "LEARNER_OBSERVED_KEY_NOT_FOUND"
        # 删除观察条目不影响显式列（本用例从未写显式偏好，保持默认空）。
        async with session_factory() as session:
            explicit = (
                await session.execute(
                    text("SELECT user_selected_preference FROM learner_preferences")
                )
            ).scalar_one()
        assert json.loads(explicit).get("items", []) == []


@pytest.mark.anyio
async def test_memory_payload_validation(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (_app, client, _sf, _data_dir):
        # EXPLICIT 无条目、OBSERVED 缺置信度 → 判别校验拒绝。
        response = await client.post(
            "/api/proposals", json={"proposal_type": "MEMORY", "payload": {"kind": "EXPLICIT"}}
        )
        assert response.status_code == 422
        response = await client.post(
            "/api/proposals",
            json={
                "proposal_type": "MEMORY",
                "payload": {"kind": "OBSERVED", "entries": {"a": "b"}},
            },
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# build_learner_context：注入范围与硬门禁（服务级直调）


@pytest.mark.anyio
async def test_context_requires_injection_allowed(tmp_path: Path) -> None:
    """硬门禁：关闭外发后零注入（零发送）——开关关闭即零记忆，含课程状态。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory, COURSE_A)
        await seed_mastery(session_factory, COURSE_A, CONCEPT_A_WEAK, "傅里叶级数", score=0.1)
        async with session_factory() as session:
            context = await build_learner_context(
                session, scope=ChatScope.COURSE, course_id=COURSE_A, injection_allowed=False
            )
        assert context.text == ""
        assert context.memories == ()


@pytest.mark.anyio
async def test_context_injects_global_preferences_across_scopes(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        async with session_factory() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO learner_preferences (id, user_selected_preference, "
                    "observed_learning_preference, observed_confidence, evidence_count, "
                    "updated_at) VALUES ('me', :explicit, :observed, 0.5, 4, :now)"
                ),
                {
                    "explicit": json.dumps({"items": ["先看例题", "多给反例"]}, ensure_ascii=False),
                    "observed": json.dumps({"entries": {"笔记习惯": "结构化"}}, ensure_ascii=False),
                    "now": NOW,
                },
            )
        for scope in ChatScope:
            async with session_factory() as session:
                context = await build_learner_context(
                    session, scope=scope, course_id=None, injection_allowed=True
                )
            assert "先看例题" in context.text, scope
            assert "笔记习惯：结构化" in context.text, scope
            assert "当前课程学习状态" not in context.text, scope
            assert context.memories[:2] == ("先看例题", "多给反例")


@pytest.mark.anyio
async def test_context_course_state_scoped_and_isolated(tmp_path: Path) -> None:
    """硬门禁：Course 状态零越界——课程 B 的概念只进课程 B 的会话；ALL 不注入。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory, COURSE_A)
        await seed_course(session_factory, COURSE_B)
        await seed_mastery(session_factory, COURSE_A, CONCEPT_A_WEAK, "傅里叶级数", score=0.1)
        await seed_mastery(session_factory, COURSE_A, CONCEPT_A_OK, "矩阵求逆", score=0.95)
        await seed_mastery(session_factory, COURSE_B, CONCEPT_B_ONLY, "拉普拉斯变换", score=0.2)
        async with session_factory() as session:
            context_a = await build_learner_context(
                session, scope=ChatScope.COURSE, course_id=COURSE_A, injection_allowed=True
            )
            context_all = await build_learner_context(
                session, scope=ChatScope.ALL, course_id=None, injection_allowed=True
            )
            context_free = await build_learner_context(
                session, scope=ChatScope.FREE, course_id=None, injection_allowed=True
            )
        assert "傅里叶级数" in context_a.text
        assert "当前课程学习状态" in context_a.text
        # 越界：课程 B 概念不得出现在课程 A 上下文。
        assert "拉普拉斯变换" not in context_a.text
        assert "拉普拉斯变换" not in context_all.text
        assert "当前课程学习状态" not in context_all.text
        assert "当前课程学习状态" not in context_free.text


@pytest.mark.anyio
async def test_deleted_memory_is_not_reinjected(tmp_path: Path) -> None:
    """硬门禁：删除后零再次注入。"""
    async with bare_db(tmp_path) as session_factory:
        async with session_factory() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO learner_preferences (id, user_selected_preference, "
                    "observed_learning_preference, observed_confidence, evidence_count, "
                    "updated_at) VALUES ('me', :explicit, NULL, NULL, 0, :now)"
                ),
                {
                    "explicit": json.dumps({"items": ["先看例题"]}, ensure_ascii=False),
                    "now": NOW,
                },
            )
        async with session_factory() as session:
            context = await build_learner_context(
                session, scope=ChatScope.FREE, course_id=None, injection_allowed=True
            )
        assert "先看例题" in context.text
        async with session_factory() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE learner_preferences SET user_selected_preference = '{}', "
                    "updated_at = :now WHERE id = 'me'"
                ),
                {"now": NOW},
            )
        async with session_factory() as session:
            context = await build_learner_context(
                session, scope=ChatScope.FREE, course_id=None, injection_allowed=True
            )
        assert "先看例题" not in context.text
        assert context.text == ""
        assert context.memories == ()


# ---------------------------------------------------------------------------
# propose_memory 工具：模型受控写路径


@pytest.mark.anyio
async def test_propose_memory_tool_creates_pending_proposal(tmp_path: Path) -> None:
    """工具创建提案不改事实；确认后才写入（经应用器）。"""
    async with bare_db(tmp_path) as session_factory:
        token = bind_agent_runtime_context(
            AgentRuntimeContext(session_factory=session_factory, session_id="sess-1")
        )
        try:
            raw = await propose_memory.ainvoke({"items": ["先看例题", " "]})
        finally:
            reset_agent_runtime_context(token)
        payload = json.loads(raw)
        assert payload["ok"] is True
        assert payload["items"] == ["先看例题"]
        assert payload["status"] == "PENDING"
        # 创建后事实不变（零行）。
        async with session_factory() as session:
            rows = (await session.execute(text("SELECT id FROM learner_preferences"))).all()
        assert rows == []
        # 确认经已注册应用器写入。
        async with session_factory() as session:
            proposal = await ProposalService.confirm(session, str(payload["proposal_id"]))
        assert proposal.status == "APPLIED"
        async with session_factory() as session:
            row = (
                await session.execute(
                    text("SELECT user_selected_preference FROM learner_preferences WHERE id='me'")
                )
            ).scalar_one()
        assert json.loads(row)["items"] == ["先看例题"]


@pytest.mark.anyio
async def test_propose_memory_tool_unbound_is_safe(tmp_path: Path) -> None:
    async with bare_db(tmp_path):
        raw = await propose_memory.ainvoke({"items": ["先看例题"]})
        payload = json.loads(raw)
        assert payload["ok"] is False
        raw = await propose_memory.ainvoke({"items": ["  "]})
        assert json.loads(raw)["ok"] is False


@pytest.mark.anyio
async def test_proposal_list_filters_memory(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (_app, client, _sf, _data_dir):
        created = await create_memory_proposal(client, {"kind": "EXPLICIT", "items": ["a"]})
        response = await client.get("/api/proposals", params={"proposal_type": "MEMORY"})
        assert response.status_code == 200
        items = response.json()
        assert [item["id"] for item in items] == [created["id"]]


@pytest.mark.anyio
async def test_accept_derives_memory_injection_flag(tmp_path: Path) -> None:
    """硬门禁「关闭外发后零发送」的真实链路：accept 派生注入标志
    = 外发开关开启 AND 外发同意对当前供应商有效（fingerprint 匹配）。"""
    async with running_app(tmp_path) as (_app, client, session_factory, data_dir):
        created = await client.post("/api/chat-sessions", json={})
        assert created.status_code == 201
        session_id = created.json()["id"]

        async def accept() -> object:
            return await ChatMessageService.accept(
                session_factory=session_factory,
                data_dir=data_dir,
                registry=ChatStreamRegistry(),
                session_id=session_id,
                content="问题",
            )

        # 供应商已配置但外发同意未授予 → 不注入。
        save_llm_provider(
            data_dir,
            base_url="https://stub.example.com/v1",
            api_key="sk-test",
            model="stub-chat-model",
            clear_api_key=False,
        )
        assert (await accept()).memory_injection_allowed is False  # type: ignore[attr-defined]
        # 授予同意（绑定当前供应商指纹）→ 注入。
        granted = await client.post("/api/settings/external-processing-consents/llm")
        assert granted.status_code == 200
        assert (await accept()).memory_injection_allowed is True  # type: ignore[attr-defined]
        # 关闭外发开关 → 不注入（记忆保留本地）。
        toggled = await client.put("/api/learner/memory-outbound", json={"enabled": False})
        assert toggled.status_code == 200
        assert (await accept()).memory_injection_allowed is False  # type: ignore[attr-defined]
