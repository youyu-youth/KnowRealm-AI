"""研究会话 V1（工单 01）：创建矩阵、研究 prompt 文本协议、propose_ingest
工具三分支与 done 载荷形状。端点契约走完整 app；prompt 与工具直调函数层；
流式经假模型先例（test_chat_streaming 同款 StubChatModel 收敛版）。
"""

import json
from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, cast
from uuid import uuid4

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessageChunk,
    UsageMetadata,
)
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import create_database
from app.db.migrations import run_migrations
from app.main import create_app
from app.modules.agent.context import (
    CHAT_RESEARCH_SECTION_TITLES,
    ContextRow,
    LibraryContext,
    LibraryRecordRow,
    build_context_messages,
)
from app.modules.agent.runtime import (
    AgentRuntimeContext,
    bind_agent_runtime_context,
    reset_agent_runtime_context,
)
from app.modules.agent.schemas import ChatMode, ChatRole
from app.modules.agent.tools.propose_ingest import (
    PROPOSE_INGEST_SOURCES_LIMIT,
    propose_ingest,
)
from app.modules.settings.config import save_llm_provider

TOKEN = "test-launch-token"
NOW = "2026-09-20T08:00:00.000000Z"
COURSE_A = "c0000000-0000-4000-8000-00000000000a"


# ---------------------------------------------------------------------------
# 夹具


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


async def seed_course(session_factory: async_sessionmaker[AsyncSession], course_id: str) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO courses (id, name, learning_context, depth, status,"
                " created_at, updated_at) VALUES (:id, '操作系统', 'INTEREST',"
                " 'INTERMEDIATE', 'ACTIVE', :now, :now)"
            ),
            {"id": course_id, "now": NOW},
        )


async def proposal_rows(data_dir: Path, session_id: str) -> list[tuple[str, str, str]]:
    async with aiosqlite.connect(data_dir / "knowrealm.db") as connection:
        return [
            (cast(str, row[0]), cast(str, row[1]), cast(str, row[2]))
            for row in await (
                await connection.execute(
                    "SELECT proposal_type, status, payload_json FROM agent_proposals"
                    " WHERE session_id = ?",
                    (session_id,),
                )
            ).fetchall()
        ]


# ---------------------------------------------------------------------------
# 创建矩阵（mode × scope）


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("payload", "expected_scope"),
    [
        ({"mode": "RESEARCH", "scope": "ALL"}, "ALL"),
        ({"mode": "RESEARCH"}, "FREE"),
        ({"mode": "RESEARCH", "scope": "FREE"}, "FREE"),
    ],
)
async def test_create_research_allows_all_course_free_scopes(
    tmp_path: Path, payload: dict[str, Any], expected_scope: str
) -> None:
    async with running_chat_app(tmp_path) as (_app, client):
        created = await client.post("/api/chat-sessions", json=payload)

    assert created.status_code == 201
    body = created.json()
    assert body["mode"] == "RESEARCH"
    assert body["scope"] == expected_scope


@pytest.mark.anyio
async def test_create_research_course_scope_ok(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        await seed_course(app.state.session_factory, COURSE_A)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            created = await client.post(
                "/api/chat-sessions",
                json={"mode": "RESEARCH", "scope": "COURSE", "course_id": COURSE_A},
            )

    assert created.status_code == 201
    body = created.json()
    assert body["mode"] == "RESEARCH"
    assert body["scope"] == "COURSE"
    assert body["course_id"] == COURSE_A


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {"mode": "RESEARCH", "scope": "RECORD", "record_id": str(uuid4())},
        {"mode": "RESEARCH", "record_id": str(uuid4())},
        {"mode": "RESEARCH", "scope": "LIBRARY_ITEM", "library_item_id": str(uuid4())},
    ],
)
async def test_create_research_rejects_record_and_library_item_scopes(
    tmp_path: Path, payload: dict[str, Any]
) -> None:
    """RESEARCH × RECORD / LIBRARY_ITEM 组合拒绝：422 + 登记错误码。"""
    async with running_chat_app(tmp_path) as (_app, client):
        created = await client.post("/api/chat-sessions", json=payload)

    assert created.status_code == 422
    body = created.json()
    assert body["code"] == "CHAT_RESEARCH_SCOPE_INVALID"


@pytest.mark.anyio
async def test_create_mode_literal_still_restricted(tmp_path: Path) -> None:
    """SOCRATIC_TUTOR 继续不放开（mode 字面量仍是 ASK | RESEARCH）。"""
    async with running_chat_app(tmp_path) as (_app, client):
        created = await client.post("/api/chat-sessions", json={"mode": "SOCRATIC_TUTOR"})

    assert created.status_code == 422
    assert created.json()["code"] == "REQUEST_VALIDATION_FAILED"


# ---------------------------------------------------------------------------
# 研究 prompt 文本协议（五节结构 + 证据纪律）


def _research_library() -> LibraryContext:
    return LibraryContext(
        scope_label="全部资料",
        records=(
            LibraryRecordRow(
                title="傅里叶分析第 2 讲", updated_date="2026-09-01", has_transcript=True
            ),
            LibraryRecordRow(
                title="速记：注意力机制", updated_date="2026-09-02", has_transcript=False
            ),
        ),
    )


def test_research_prompt_carries_five_section_protocol_and_discipline() -> None:
    messages = build_context_messages(
        [ContextRow(id="u1", role=ChatRole.USER, content="研究：注意力机制变体的取舍")],
        library=_research_library(),
        mode=ChatMode.RESEARCH,
    )
    system = str(messages[0].content)
    for title in CHAT_RESEARCH_SECTION_TITLES:
        assert f"## {title}" in system
    # 无证据拒答纪律与提案工具指引。
    assert "当前资料中未找到" in system
    assert "propose_ingest" in system
    # web 与本地 citation 类型不冒充。
    assert "不得互相冒充" in system
    assert "[n] 标题 — URL" in system


def test_research_prompt_free_scope_states_no_local_range() -> None:
    messages = build_context_messages(
        [ContextRow(id="u1", role=ChatRole.USER, content="研究：某时效性问题")],
        mode=ChatMode.RESEARCH,
    )
    system = str(messages[0].content)
    assert "无本地资料范围" in system
    for title in CHAT_RESEARCH_SECTION_TITLES:
        assert f"## {title}" in system


def test_ask_library_prompt_keeps_qa_protocol_without_research_sections() -> None:
    messages = build_context_messages(
        [ContextRow(id="u1", role=ChatRole.USER, content="问题")],
        library=_research_library(),
    )
    system = str(messages[0].content)
    assert "## 已有证据" not in system
    assert "propose_ingest" not in system


# ---------------------------------------------------------------------------
# propose_ingest 工具（未绑定 / 超限 / 成功建案）


async def _invoke_propose_ingest(sources: list[dict[str, str]]) -> dict[str, object]:
    raw = await propose_ingest.ainvoke({"sources": sources})
    return cast(dict[str, object], json.loads(raw))


@pytest.mark.anyio
async def test_propose_ingest_unbound_is_safe(tmp_path: Path) -> None:
    async with bare_db(tmp_path):
        payload = await _invoke_propose_ingest(
            [{"url": "https://example.com/a", "title": "来源 A"}]
        )
    assert payload["ok"] is False
    assert payload["error"] == "RESEARCH_INGEST_CONTEXT_UNBOUND"


@pytest.mark.anyio
async def test_propose_ingest_over_limit_rejects_without_rows(tmp_path: Path) -> None:
    """超限拒绝而非截断：零提案落库。"""
    async with bare_db(tmp_path) as session_factory:
        token = bind_agent_runtime_context(
            AgentRuntimeContext(session_factory=session_factory, session_id="sess-1")
        )
        try:
            sources = [
                {"url": f"https://example.com/{i}", "title": f"来源 {i}"}
                for i in range(PROPOSE_INGEST_SOURCES_LIMIT + 1)
            ]
            payload = await _invoke_propose_ingest(sources)
        finally:
            reset_agent_runtime_context(token)
        async with session_factory() as session:
            rows = (await session.execute(text("SELECT id FROM agent_proposals"))).all()
    assert payload["ok"] is False
    assert payload["error"] == "RESEARCH_SOURCES_TOO_LONG"
    assert rows == []


@pytest.mark.anyio
async def test_propose_ingest_creates_pending_proposals_with_course_id(
    tmp_path: Path,
) -> None:
    """COURSE 范围自动带课程 id；提案溯源带 session_id；创建不改事实。"""
    async with bare_db(tmp_path) as session_factory:
        token = bind_agent_runtime_context(
            AgentRuntimeContext(
                session_factory=session_factory,
                session_id="sess-1",
                course_id=COURSE_A,
            )
        )
        try:
            payload = await _invoke_propose_ingest(
                [
                    {"url": "https://example.com/a", "title": "来源 A"},
                    {"url": "https://example.com/b", "title": "来源 B"},
                ]
            )
        finally:
            reset_agent_runtime_context(token)
        assert payload["ok"] is True
        proposals = cast(list[dict[str, str]], payload["proposals"])
        assert [item["title"] for item in proposals] == ["来源 A", "来源 B"]
        async with session_factory() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT proposal_type, status, session_id, payload_json"
                        " FROM agent_proposals ORDER BY created_at, id"
                    )
                )
            ).all()
    assert len(rows) == 2
    for row, item in zip(rows, proposals, strict=True):
        assert row[0] == "RESEARCH_INGEST"
        assert row[1] == "PENDING"
        assert row[2] == "sess-1"
        body = json.loads(cast(str, row[3]))
        assert body == {"url": item["url"], "title": item["title"], "course_id": COURSE_A}


@pytest.mark.anyio
async def test_propose_ingest_all_scope_payload_course_id_none(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        token = bind_agent_runtime_context(
            AgentRuntimeContext(session_factory=session_factory, session_id="sess-2")
        )
        try:
            payload = await _invoke_propose_ingest(
                [{"url": "https://example.com/a", "title": "来源 A"}]
            )
        finally:
            reset_agent_runtime_context(token)
        async with session_factory() as session:
            row = (await session.execute(text("SELECT payload_json FROM agent_proposals"))).one()
    body = json.loads(cast(str, row[0]))
    assert body["course_id"] is None
    assert payload["ok"] is True


# ---------------------------------------------------------------------------
# 流式：挂载矩阵与 done 载荷（假模型先例）


@dataclass(frozen=True)
class _ToolCallReply:
    tool: str
    args: dict[str, Any]


_StubReply = list[str] | _ToolCallReply | None


class _StubChatModel(BaseChatModel):
    """测试缝隙：捕获 bind_tools 工具面，按队列逐 token 吐出预设回复。"""

    captured_bound: ClassVar[list[list[str]]] = []
    replies: ClassVar[list[_StubReply]] = []

    @property
    def _llm_type(self) -> str:
        return "stub-test"

    def _generate(
        self,
        messages: Any,
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise NotImplementedError

    def bind(self, **kwargs: Any) -> Any:  # pyright: ignore[reportIncompatibleMethodOverride]
        return self

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_StubChatModel":
        type(self).captured_bound.append([getattr(t, "name", "?") for t in tools])
        return self

    async def _astream(
        self,
        messages: Any,
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        reply = type(self).replies.pop(0)
        if isinstance(reply, _ToolCallReply):
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {
                            "name": reply.tool,
                            "args": json.dumps(reply.args, ensure_ascii=False),
                            "id": "call-1",
                            "index": 0,
                        }
                    ],
                    usage_metadata=UsageMetadata(input_tokens=3, output_tokens=4, total_tokens=7),
                )
            )
            return
        assert isinstance(reply, list)
        for index, part in enumerate(reply):
            usage = (
                UsageMetadata(input_tokens=3, output_tokens=4, total_tokens=7)
                if index == len(reply) - 1
                else None
            )
            yield ChatGenerationChunk(message=AIMessageChunk(content=part, usage_metadata=usage))


@asynccontextmanager
async def streaming_research_app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    replies: Sequence[_StubReply],
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient, list[list[str]]]]:
    queue: list[_StubReply] = list(replies)

    class _StubChatOpenAI(_StubChatModel):
        pass

    _StubChatOpenAI.captured_bound = []
    _StubChatOpenAI.replies = queue
    monkeypatch.setattr("app.modules.llm.service.ChatOpenAI", _StubChatOpenAI)

    save_llm_provider(
        tmp_path,
        base_url="https://stub.example.com/v1",
        api_key="sk-test",
        model="stub-chat-model",
        clear_api_key=False,
    )
    app = create_app(data_dir=tmp_path, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client, _StubChatOpenAI.captured_bound


async def read_sse(response: httpx.Response) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    event_name: str | None = None
    data_lines: list[str] = []
    async for line in response.aiter_lines():
        if line == "":
            if event_name is not None:
                payload = json.loads("\n".join(data_lines))
                events.append((event_name, cast(dict[str, Any], payload)))
            event_name, data_lines = None, []
        elif line.startswith("event:"):
            event_name = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").strip())
    return events


async def send_message(
    client: httpx.AsyncClient, session_id: str, content: str
) -> list[tuple[str, dict[str, Any]]]:
    async with client.stream(
        "POST",
        f"/api/chat-sessions/{session_id}/messages",
        json={"content": content, "web_search": False},
    ) as response:
        assert response.status_code == 200
        return await read_sse(response)


@pytest.mark.anyio
async def test_research_mounting_matrix_tool_visibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """propose_ingest 仅研究会话挂载；RESEARCH×ALL 再挂 search_library。"""
    async with streaming_research_app(tmp_path, monkeypatch, replies=[["回答"]] * 6) as (
        _app,
        client,
        captured_bound,
    ):
        free_research = (await client.post("/api/chat-sessions", json={"mode": "RESEARCH"})).json()[
            "id"
        ]
        all_research = (
            await client.post("/api/chat-sessions", json={"mode": "RESEARCH", "scope": "ALL"})
        ).json()["id"]
        free_ask = (await client.post("/api/chat-sessions", json={})).json()["id"]

        async def visible(session_id: str) -> list[str]:
            captured_bound.clear()
            events = await send_message(client, session_id, "研究问题")
            assert events[-1][0] == "done"
            return captured_bound[-1]

        free_tools = await visible(free_research)
        assert "propose_ingest" in free_tools
        assert "propose_memory" in free_tools
        assert "search_library" not in free_tools

        all_tools = await visible(all_research)
        assert "propose_ingest" in all_tools
        assert "search_library" in all_tools

        ask_tools = await visible(free_ask)
        assert "propose_ingest" not in ask_tools
        assert "search_library" not in ask_tools


@pytest.mark.anyio
async def test_research_stream_done_carries_research_proposals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """工具成功 → done 载荷 research_proposals 形状；提案落库 PENDING；
    llm_call_logs 记研究 prompt 版本。"""
    replies: list[_StubReply] = [
        _ToolCallReply(
            "propose_ingest",
            {"sources": [{"url": "https://example.com/a", "title": "来源 A"}]},
        ),
        ["## 已有证据\n当前资料中未找到。"],
    ]
    async with streaming_research_app(tmp_path, monkeypatch, replies=replies) as (
        _app,
        client,
        _captured_bound,
    ):
        created = await client.post("/api/chat-sessions", json={"mode": "RESEARCH", "scope": "ALL"})
        session_id = created.json()["id"]
        events = await send_message(client, session_id, "研究：注意力机制变体的取舍")

    tool_results = [payload for name, payload in events if name == "tool_result"]
    assert {"tool": "propose_ingest", "hits": 0, "ok": True} in tool_results
    done = events[-1][1]
    assert events[-1][0] == "done"
    proposals = done["research_proposals"]
    assert len(proposals) == 1
    assert proposals[0]["url"] == "https://example.com/a"
    assert proposals[0]["title"] == "来源 A"
    assert isinstance(proposals[0]["proposal_id"], str)
    assert done["memory_used"] == []

    rows = await proposal_rows(tmp_path, session_id)
    assert len(rows) == 1
    assert rows[0][0] == "RESEARCH_INGEST"
    assert rows[0][1] == "PENDING"
    body = json.loads(rows[0][2])
    assert body == {"url": "https://example.com/a", "title": "来源 A", "course_id": None}

    async with aiosqlite.connect(tmp_path / "knowrealm.db") as connection:
        log = await (
            await connection.execute(
                "SELECT prompt_version, error_code FROM llm_call_logs WHERE graph_name = 'chat'"
            )
        ).fetchone()
    assert log is not None
    assert log[0] == "chat-research-scope-v21"
    assert log[1] is None
