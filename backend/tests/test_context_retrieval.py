"""工单 03：公开 API、真实 SQLite/Worker 与真实框架工具链（模型替身）。"""

import asyncio
import json
from datetime import timedelta
from math import ceil
from pathlib import Path
from typing import Any, cast

import pytest
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    BaseMessage,
    ToolMessage,
    messages_to_dict,
)
from langchain_core.tools import tool
from sqlalchemy import func, select, text

from app.modules.agent.budget.service import budgeted
from app.modules.agent.context_budget.models import (
    ChatContextOutput,
    ChatContextState,
    ChatModelRequest,
)
from app.modules.agent.graph import AgentConfig
from app.modules.agent.models import ChatMessage
from app.modules.agent.schemas import ChatRole
from tests.test_chat_turns import (
    GatedReply,
    ToolCallReply,
    create_session,
    submit,
    turns_app,
    wait_terminal,
)
from tests.test_chat_turns_recovery import recovery_app
from tests.test_conversation_compaction import configure, seed_history, summary_model


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_revalidation_reuses_material_and_rechecks_versions_and_visibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.agent.context_budget.retrieval import validate_read_results
    from app.modules.library.retrieval import LibraryRetrievalService
    from tests.test_shared_refs import (
        COURSE_AGENT,
        ITEM_ML_PAPER,
        REC_ML_PAPER,
        seed_full_corpus,
        seed_ref,
    )

    async with turns_app(tmp_path, monkeypatch) as (app, client, _captured):
        factory = app.state.session_factory
        await seed_full_corpus(factory)
        await seed_ref(factory, COURSE_AGENT, ITEM_ML_PAPER)
        sid = await create_session(client, scope="COURSE", course_id=COURSE_AGENT)
        original = (
            await client.post(
                f"/api/chat-sessions/{sid}/context/sources/read",
                json={"source_id": f"record:{REC_ML_PAPER}"},
            )
        ).json()
        hit = {
            "record_id": REC_ML_PAPER,
            "source_version": original["source"]["version"],
            "quote": original["content"][:20],
        }
        messages: list[AnyMessage] = [
            ToolMessage(
                content=json.dumps({"evidence_hits": [hit, hit]}),
                name="search_library",
                tool_call_id=f"search-{i}",
            )
            for i in range(12)
        ]
        messages.append(
            ToolMessage(content=json.dumps(original), name="read_context", tool_call_id="read")
        )
        messages.append(
            ToolMessage(
                content=json.dumps({"evidence_hits": [{**hit, "quote": "不存在的摘录"}]}),
                name="search_library",
                tool_call_id="bad-quote",
            )
        )
        calls = 0
        read_source = LibraryRetrievalService.read_source

        async def counted(*args: Any, **kwargs: Any) -> tuple[str, str, str]:
            nonlocal calls
            calls += 1
            return await read_source(*args, **kwargs)

        monkeypatch.setattr(LibraryRetrievalService, "read_source", counted)
        checked = await validate_read_results(factory, sid, messages)
        assert checked[:-1] == messages[:-1]
        assert json.loads(checked[-1].text)["error"] == "CONTEXT_SOURCE_STALE"
        assert calls == 1, f"same material loaded {calls} times in one validation pass"
        async with factory() as db, db.begin():
            await db.execute(
                text("UPDATE transcripts SET source_version=source_version+1 WHERE record_id=:id"),
                {"id": REC_ML_PAPER},
            )
        checked = await validate_read_results(factory, sid, messages)
        assert all(json.loads(m.text)["error"] == "CONTEXT_SOURCE_STALE" for m in checked)
        async with factory() as db, db.begin():
            await db.execute(
                text(
                    "DELETE FROM course_shared_refs WHERE course_id=:cid AND library_item_id=:iid"
                ),
                {"cid": COURSE_AGENT, "iid": ITEM_ML_PAPER},
            )
        checked = await validate_read_results(factory, sid, messages)
        assert all(json.loads(m.text)["error"] == "CONTEXT_SOURCE_UNAVAILABLE" for m in checked)
        assert "error" not in json.loads(messages[0].text)


@pytest.mark.anyio
async def test_revalidation_decodes_legacy_snapshots_once_and_reads_history_by_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy import event

    from app.modules.agent.context_budget import retrieval

    async with turns_app(tmp_path, monkeypatch) as (app, client, _captured):
        sid = await create_session(client)
        turn = (await submit(client, sid, "seed", request_id="validation-cache")).json()["id"]
        assert (await wait_terminal(client, turn))["status"] == "COMPLETED"
        ids = await seed_history(app, sid, 20, 1000)
        tools = [
            ToolMessage(content=f"legacy text {i}", id=f"legacy-{i}", tool_call_id=f"call-{i}")
            for i in range(2)
        ]
        older_tool = ToolMessage(
            content="older tool text", id="legacy-older", tool_call_id="call-old"
        )
        snapshot = json.dumps(
            messages_to_dict(
                [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {"name": "web_search", "args": {}, "id": m.tool_call_id} for m in tools
                        ],
                    ),
                    *tools,
                ]
            )
        )
        async with app.state.session_factory() as db, db.begin():
            row = await db.scalar(
                select(ChatModelRequest).where(
                    ChatModelRequest.turn_id == turn, ChatModelRequest.purpose == "ANSWER"
                )
            )
            assert row is not None
            row.messages_json = snapshot
            db.add(
                ChatModelRequest(
                    turn_id=turn,
                    status=row.status,
                    input_fingerprint=row.input_fingerprint,
                    estimate_json=row.estimate_json,
                    created_at=row.created_at - timedelta(seconds=1),
                    messages_json=json.dumps(
                        messages_to_dict(
                            [
                                AIMessage(
                                    content="old history" * 5000,
                                    tool_calls=[
                                        {"name": "web_search", "args": {}, "id": "call-old"}
                                    ],
                                ),
                                older_tool,
                            ]
                        )
                    ),
                )
            )
            db.add(
                ChatModelRequest(
                    turn_id=turn,
                    status=row.status,
                    input_fingerprint=row.input_fingerprint,
                    estimate_json=row.estimate_json,
                    created_at=row.created_at - timedelta(seconds=2),
                    messages_json="[]",
                )
            )
        sources = [
            (
                await client.post(
                    f"/api/chat-sessions/{sid}/context/sources/read", json={"source_id": source_id}
                )
            ).json()
            for source_id in [*ids[:2], *(f"message:{m.id}" for m in [*tools, older_tool])]
        ]
        assert all("source" in source for source in sources), sources
        decodes = 0
        loaded_messages = 0
        loaded_requests = 0
        decoder = retrieval.messages_from_dict

        def counted_decode(value: Any) -> list[BaseMessage]:
            nonlocal decodes
            decodes += 1
            return decoder(value)

        def loaded(_row: ChatMessage, _context: Any) -> None:
            nonlocal loaded_messages
            loaded_messages += 1

        def loaded_request(_row: ChatModelRequest, _context: Any) -> None:
            nonlocal loaded_requests
            loaded_requests += 1

        monkeypatch.setattr(retrieval, "messages_from_dict", counted_decode)
        event.listen(ChatMessage, "load", loaded)
        event.listen(ChatModelRequest, "load", loaded_request)
        try:
            messages: list[AnyMessage] = [
                ToolMessage(content=json.dumps(source), name="read_context", tool_call_id=str(i))
                for i, source in enumerate(sources)
            ]
            assert (
                await retrieval.validate_read_results(app.state.session_factory, sid, messages)
                == messages
            )
            assert decodes == 2, f"two request snapshots decoded {decodes} times"
            assert loaded_requests == 2, (
                f"loaded {loaded_requests} snapshots for two needed snapshots"
            )
            assert loaded_messages == 2, f"loaded {loaded_messages} messages for two source IDs"
            async with app.state.session_factory() as db, db.begin():
                row = await db.scalar(
                    select(ChatModelRequest)
                    .where(ChatModelRequest.turn_id == turn)
                    .order_by(ChatModelRequest.created_at.desc())
                )
                assert row is not None
                row.messages_json = "[]"
            checked = await retrieval.validate_read_results(
                app.state.session_factory, sid, messages
            )
            assert checked[:2] == messages[:2]
            assert all(
                json.loads(m.text)["error"] == "CONTEXT_SOURCE_UNAVAILABLE" for m in checked[2:4]
            )
            assert checked[4] == messages[4]
        finally:
            event.remove(ChatMessage, "load", loaded)
            event.remove(ChatModelRequest, "load", loaded_request)


@pytest.mark.anyio
async def test_history_scope_paging_versions_and_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with turns_app(tmp_path, monkeypatch) as (app, client, _captured):
        sid, other = await create_session(client), await create_session(client)
        ids = await seed_history(app, sid, 3, 4000)
        base = f"/api/chat-sessions/{sid}/context/sources"
        found = await client.post(f"{base}/search", json={"limit": 2})
        assert found.status_code == 200, found.text
        first = found.json()
        assert len(first["sources"]) == 2 and first["remaining"] == 4
        again = (
            await client.post(f"{base}/search", json={"limit": 2, "cursor": first["next_cursor"]})
        ).json()
        await seed_history(app, sid, 1, 10)
        stable = (
            await client.post(f"{base}/search", json={"limit": 2, "cursor": first["next_cursor"]})
        ).json()
        assert stable == again
        assert not {r["source_id"] for r in first["sources"]} & {
            r["source_id"] for r in again["sources"]
        }
        body = {"source_id": ids[0], "max_chars": 1000}
        page = (await client.post(f"{base}/read", json=body)).json()
        assert len(page["content"]) == 1000 and page["remaining"] > 0
        assert page["source"]["locator"]["message_id"] == ids[0]
        next_body = {**body, "cursor": page["next_cursor"]}
        second = (await client.post(f"{base}/read", json=next_body)).json()
        assert second["offset"] == 1000
        assert (
            await client.post(f"/api/chat-sessions/{other}/context/sources/read", json=next_body)
        ).status_code == 404
        assert (
            await client.post(f"{base}/read", json={**body, "cursor": "bad"})
        ).status_code == 409
        assert (
            await client.post(f"{base}/read", json={**body, "version": "old"})
        ).status_code == 409
        assert (
            await client.post(f"{base}/read", json={"source_id": "C:/secret.txt"})
        ).status_code == 404
        async with app.state.session_factory() as db, db.begin():
            db.add(ChatContextState(session_id=sid, segment=2, version=2))
        assert (await client.post(f"{base}/read", json=body)).status_code == 404
        assert (await client.post(f"{base}/search", json={})).json()["sources"] == []
        assert (await client.delete(f"/api/chat-sessions/{sid}")).status_code == 204
        assert (await client.post(f"{base}/read", json=body)).status_code == 404


@pytest.mark.anyio
async def test_reads_share_tool_count_character_budget_and_complete_input_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.llm import service

    async with turns_app(tmp_path, monkeypatch) as (app, client, captured):
        sid = await create_session(client)
        ids = await seed_history(app, sid, 1, 4000)
        cast(Any, service.ChatOpenAI).replies[:] = [
            *[
                ToolCallReply(
                    "read_context", {"source_id": ids[0], "max_chars": 2400}, call_id=f"read-{i}"
                )
                for i in range(7)
            ],
            ["按已有内容回答"],
        ]
        turn = (await submit(client, sid, "找回原文", request_id="retrieval-budgets")).json()["id"]
        assert (await wait_terminal(client, turn))["status"] == "COMPLETED"
        bodies = [json.loads(m.text) for m in captured[-1] if isinstance(m, ToolMessage)]
        assert any(body.get("error") == "CONTEXT_READ_BUDGET_EXHAUSTED" for body in bodies)
        assert bodies[-1]["error"] == "TOOL_CALL_LIMIT"
        # 页面读取完全独立，不消耗已耗尽的 Agent 额度。
        assert (
            await client.post(
                f"/api/chat-sessions/{sid}/context/sources/read", json={"source_id": ids[0]}
            )
        ).status_code == 200

    async with turns_app(tmp_path / "input", monkeypatch) as (app, client, captured):
        sid = await create_session(client)
        async with app.state.session_factory() as db, db.begin():
            message = ChatMessage(session_id=sid, role=ChatRole.ASSISTANT, content="x" * 4000)
            db.add(message)
            await db.flush()
            source_id = message.id
        preview = (
            await client.post(
                f"/api/chat-sessions/{sid}/context/estimates", json={"content": "读取"}
            )
        ).json()["next_estimate"]
        configured = await client.put(
            "/api/settings/providers/llm",
            json={
                "base_url": "https://stub.example.com/v1",
                "model": "stub-chat-model",
                "model_budget": {
                    "context_window": 128000,
                    "input_limit": ceil((preview["input_tokens"] + 800) / 0.8),
                },
            },
        )
        assert configured.status_code == 200
        cast(Any, service.ChatOpenAI).replies[:] = [
            ToolCallReply("read_context", {"source_id": source_id, "max_chars": 2400}),
            ["未发送"],
        ]
        turn = (await submit(client, sid, "读取", request_id="retrieval-input-full")).json()["id"]
        result = await wait_terminal(client, turn)
        assert (
            result["status"] == "FAILED" and result["error_code"] == "MODEL_INPUT_BUDGET_EXCEEDED"
        )
        assert len(captured) == 1
        view = (await client.get(f"/api/chat-sessions/{sid}/context")).json()
        assert view["actual"][-1]["status"] == "BLOCKED"


@pytest.mark.anyio
async def test_source_scope_shared_ref_version_archive_and_material_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_shared_refs import (
        COURSE_AGENT,
        COURSE_DB,
        ITEM_ML_PAPER,
        ITEM_ML_WEB,
        REC_ML_PAPER,
        seed_full_corpus,
        seed_ref,
    )

    async with turns_app(tmp_path, monkeypatch) as (app, client, _captured):
        await seed_full_corpus(app.state.session_factory)
        await seed_ref(app.state.session_factory, COURSE_AGENT, ITEM_ML_PAPER)
        await seed_ref(app.state.session_factory, COURSE_AGENT, ITEM_ML_WEB)
        sid = await create_session(client, scope="COURSE", course_id=COURSE_AGENT)
        other = await create_session(client, scope="COURSE", course_id=COURSE_DB)
        base = f"/api/chat-sessions/{sid}/context/sources/read"
        record = {"source_id": f"record:{REC_ML_PAPER}", "max_chars": 10}
        first = await client.post(base, json=record)
        assert first.status_code == 200, first.text
        assert (
            await client.post(f"/api/chat-sessions/{other}/context/sources/read", json=record)
        ).status_code == 404
        item = {"source_id": f"library:{ITEM_ML_WEB}"}
        web = await client.post(base, json=item)
        assert web.status_code == 200 and web.json()["content"]
        async with app.state.session_factory() as db, db.begin():
            await db.execute(
                text("UPDATE transcripts SET source_version=source_version+1 WHERE record_id=:id"),
                {"id": REC_ML_PAPER},
            )
        assert (
            await client.post(base, json={**record, "cursor": first.json()["next_cursor"]})
        ).status_code == 409
        assert (
            await client.post(base, json={**record, "version": first.json()["source"]["version"]})
        ).status_code == 409
        async with app.state.session_factory() as db, db.begin():
            await db.execute(
                text(
                    "DELETE FROM course_shared_refs WHERE course_id=:cid AND library_item_id=:iid"
                ),
                {"cid": COURSE_AGENT, "iid": ITEM_ML_PAPER},
            )
            await db.execute(
                text("UPDATE library_items SET status='ARCHIVED' WHERE id=:id"), {"id": ITEM_ML_WEB}
            )
        assert (await client.post(base, json=record)).status_code == 404
        assert (await client.post(base, json=item)).status_code == 404
        mounted = await create_session(client, scope="RECORD", record_id=REC_ML_PAPER)
        ids = await seed_history(app, mounted, 1, 20)
        async with app.state.session_factory() as db, db.begin():
            await db.execute(
                text("UPDATE transcripts SET content=content || :tail WHERE record_id=:id"),
                {"id": REC_ML_PAPER, "tail": "额外资料" * 5000 + "原文末尾定位"},
            )
        from app.modules.llm import service

        cast(Any, service.ChatOpenAI).replies[:] = [["相关片段回答"], ["全文回答"]]
        await configure(client, 60000)
        turn = (await submit(client, mounted, "梯度下降", request_id="material-snippets")).json()[
            "id"
        ]
        assert (await wait_terminal(client, turn))["status"] == "COMPLETED"
        assert set(ids) <= {m.id for m in _captured[-1]}
        assert "额外资料" * 5000 not in _captured[-1][0].text
        assert f"record:{REC_ML_PAPER}" in _captured[-1][0].text
        await configure(client, 128000)
        turn = (await submit(client, mounted, "继续", request_id="material-full")).json()["id"]
        assert (await wait_terminal(client, turn))["status"] == "COMPLETED"
        assert "额外资料" * 5000 in _captured[-1][0].text
        anchored = await client.post(
            f"/api/chat-sessions/{mounted}/context/sources/read",
            json={"source_id": f"record:{REC_ML_PAPER}", "quote": "原文末尾定位", "max_chars": 100},
        )
        assert anchored.status_code == 200 and anchored.json()["offset"] > 20000
        assert anchored.json()["content"].startswith("原文末尾定位")
        # 查找消息深处的关键词后，原文查看直接定位该命中。
        async with app.state.session_factory() as db, db.begin():
            deep = ChatMessage(
                session_id=mounted, role=ChatRole.ASSISTANT, content="x" * 8000 + "深处关键词"
            )
            db.add(deep)
        found = (
            await client.post(
                f"/api/chat-sessions/{mounted}/context/sources/search", json={"query": "深处关键词"}
            )
        ).json()["sources"][0]
        located = await client.post(
            f"/api/chat-sessions/{mounted}/context/sources/read",
            json={
                "source_id": found["source_id"],
                "version": found["version"],
                "quote": found["locator"]["quote"],
                "offset": found["locator"]["start_offset"],
            },
        )
        assert located.status_code == 200 and located.json()["offset"] == 8000
        assert located.json()["content"] == "深处关键词"
        item_session = await create_session(
            client, scope="LIBRARY_ITEM", library_item_id=ITEM_ML_PAPER
        )
        cast(Any, service.ChatOpenAI).replies.extend([["资料片段回答"]])
        await configure(client, 60000)
        turn = (
            await submit(client, item_session, "梯度下降", request_id="item-material-snippets")
        ).json()["id"]
        assert (await wait_terminal(client, turn))["status"] == "COMPLETED"
        assert "额外资料" * 5000 not in _captured[-1][0].text
        assert f"library:{ITEM_ML_PAPER}" in _captured[-1][0].text

        from app.modules.transcript.models import TranscriptSegment

        async with app.state.session_factory() as db, db.begin():
            transcript_id = await db.scalar(
                text("SELECT id FROM transcripts WHERE record_id=:id"), {"id": REC_ML_PAPER}
            )
            assert isinstance(transcript_id, str)
            await db.execute(
                text("DELETE FROM transcript_segments WHERE record_id=:id"), {"id": REC_ML_PAPER}
            )
            await db.execute(
                text("UPDATE transcripts SET content='重复正文\n重复正文' WHERE record_id=:id"),
                {"id": REC_ML_PAPER},
            )
            for seq in range(2):
                db.add(
                    TranscriptSegment(
                        id=f"duplicate-{seq}",
                        transcript_id=transcript_id,
                        record_id=REC_ML_PAPER,
                        file_id=f"file-{REC_ML_PAPER}",
                        sequence_no=seq,
                        content="重复正文",
                        content_hash=f"duplicate-{seq}",
                        record_start_ms=seq * 1000,
                    )
                )
        duplicate = await client.post(
            f"/api/chat-sessions/{mounted}/context/sources/read",
            json={"source_id": f"record:{REC_ML_PAPER}", "quote": "重复正文", "offset": 5},
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["source"]["locator"]["segment_id"] == "duplicate-1"
        assert duplicate.json()["source"]["locator"]["record_start_ms"] == 1000


@pytest.mark.anyio
async def test_output_and_cursor_survive_worker_restart_without_reexecution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executions: list[int] = []
    from app.modules.agent.graph import resolve_agent_config

    @tool
    @budgeted(lambda: "{}")
    async def durable_temporary() -> str:
        """Return a large temporary output, once per logical call."""
        executions.append(1)
        return json.dumps({"data": "x" * 50000})

    def config(**kwargs: Any) -> AgentConfig:
        base = resolve_agent_config(**kwargs)
        return AgentConfig(tools=(*base.tools, durable_temporary))

    monkeypatch.setattr("app.modules.agent.graph.resolve_agent_config", config)
    async with recovery_app(
        tmp_path,
        monkeypatch,
        replies=[ToolCallReply("durable_temporary", {}), GatedReply(("在途",), asyncio.Event())],
    ) as (app, client, captured):
        sid = await create_session(client)
        await configure(client, 60000)
        turn = (await submit(client, sid, "获取", request_id="output-restart")).json()["id"]
        async with asyncio.timeout(15):
            while len(captured) < 2:
                await asyncio.sleep(0.1)
        async with app.state.session_factory() as db:
            row = (await db.scalars(select(ChatContextOutput))).one()
            source_id = f"output:{row.id}"
        base = f"/api/chat-sessions/{sid}/context/sources/read"
        first = (await client.post(base, json={"source_id": source_id})).json()
    async with recovery_app(tmp_path, monkeypatch, replies=[["恢复完成"]]) as (
        app,
        client,
        _captured,
    ):
        assert (await wait_terminal(client, turn))["status"] == "COMPLETED"
        continued = await client.post(
            base, json={"source_id": source_id, "cursor": first["next_cursor"]}
        )
        assert continued.status_code == 200 and continued.json()["offset"] == 1600
        assert executions == [1]
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count()).select_from(ChatContextOutput)) == 1


@pytest.mark.anyio
async def test_compacted_source_is_read_through_real_framework_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Any] = []
    summary_model(monkeypatch, calls)
    async with turns_app(tmp_path, monkeypatch, replies=[["压缩完成"]]) as (app, client, captured):
        sid = await create_session(client)
        ids = await seed_history(app, sid, 16, 1000)
        await configure(client)
        turn = (await submit(client, sid, "继续", request_id="retrieval-compact")).json()["id"]
        assert (await wait_terminal(client, turn))["status"] == "COMPLETED"
        view = (await client.get(f"/api/chat-sessions/{sid}/context")).json()
        source_id = view["active_summary"]["covered_message_ids"][0]
        assert source_id in ids and calls
        from app.modules.llm import service

        cast(Any, service.ChatOpenAI).replies.extend(
            [
                ToolCallReply("read_context", {"source_id": source_id, "max_chars": 500}),
                ["细节已找回"],
            ]
        )
        turn = (
            await submit(client, sid, "找回被摘要省略的原话", request_id="retrieval-original")
        ).json()["id"]
        assert (await wait_terminal(client, turn))["status"] == "COMPLETED"
        payload = json.loads(
            next(
                m.text
                for m in reversed(captured[-1])
                if isinstance(m, ToolMessage) and m.name == "read_context"
            )
        )
        assert payload["source"]["locator"]["message_id"] == source_id
        assert len(payload["content"]) == 500 and payload["next_cursor"]


@pytest.mark.anyio
async def test_large_output_projection_preserves_snapshot_and_is_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = json.dumps({"ok": True, "data": "大结果🙂" * 10000}, ensure_ascii=False)

    @tool
    @budgeted(lambda: json.dumps({"ok": False, "error": "TOOL_CALL_LIMIT"}))
    async def temporary_output() -> str:
        """Return a non-rebuildable temporary result."""
        return original

    from app.modules.agent.graph import resolve_agent_config

    def config(**kwargs: Any) -> AgentConfig:
        base = resolve_agent_config(**kwargs)
        return AgentConfig(tools=(*base.tools, temporary_output))

    monkeypatch.setattr("app.modules.agent.graph.resolve_agent_config", config)
    async with turns_app(
        tmp_path, monkeypatch, replies=[ToolCallReply("temporary_output", {}), ["保存完成"]]
    ) as (app, client, captured):
        sid = await create_session(client)
        await configure(client, 60000)
        turn = (await submit(client, sid, "获取大结果", request_id="retrieval-output")).json()["id"]
        result = await wait_terminal(client, turn)
        assert result["status"] == "COMPLETED", result
        visible = json.loads(next(m.text for m in captured[-1] if isinstance(m, ToolMessage)))
        assert visible["source_id"].startswith("output:") and visible["truncated"]
        async with app.state.session_factory() as db:
            saved = (await db.scalars(select(ChatContextOutput))).one()
            assert saved.content == original and saved.turn_id == turn
        base = f"/api/chat-sessions/{sid}/context/sources"
        body = {"source_id": visible["source_id"], "version": visible["version"], "max_chars": 2400}
        page = (await client.post(f"{base}/read", json=body)).json()
        second = (
            await client.post(f"{base}/read", json={**body, "cursor": page["next_cursor"]})
        ).json()
        assert page["content"] + second["content"] == original[:4800]
        other = await create_session(client)
        assert (
            await client.post(f"/api/chat-sessions/{other}/context/sources/read", json=body)
        ).status_code == 404
        from app.modules.llm import service

        cast(Any, service.ChatOpenAI).replies.extend(
            [ToolCallReply("read_context", body, call_id="read-output"), ["取回完成"]]
        )
        read_turn = (
            await submit(client, sid, "继续读大结果", request_id="retrieval-output-next")
        ).json()["id"]
        assert (await wait_terminal(client, read_turn))["status"] == "COMPLETED"
        retrieved = json.loads(
            next(
                m.text
                for m in reversed(captured[-1])
                if isinstance(m, ToolMessage) and m.name == "read_context"
            )
        )
        assert retrieved["content"] == original[:2400]
        # 终态清理工具预算不能提前清理仍可取回的正文。
        async with app.state.session_factory() as db:
            assert await db.scalar(select(func.count()).select_from(ChatContextOutput)) == 1
        assert (await client.delete(f"/api/chat-sessions/{sid}")).status_code == 204
        assert (await client.post(f"{base}/read", json=body)).status_code == 404


@pytest.mark.anyio
async def test_real_web_tool_keeps_pre_truncation_text_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.search.integrations.tavily import TavilySearchClient
    from app.modules.search.web_search import WebSearchHit

    async def search(self: Any, query: str, *, max_results: int) -> list[WebSearchHit]:
        return [
            WebSearchHit(
                title="网页",
                url="https://example.com/source",
                content="网页正文" * 2000 + "尾部详情",
            )
        ]

    monkeypatch.setattr(TavilySearchClient, "search", search)
    async with turns_app(
        tmp_path,
        monkeypatch,
        replies=[ToolCallReply("web_search", {"query": "公开资料"}), ["结果可查"]],
    ) as (app, client, captured):
        sid = await create_session(client)
        configured = await client.put(
            "/api/settings/providers/web-search",
            json={"api_key": "tvly-test", "clear_api_key": False},
        )
        assert configured.status_code == 200
        turn = (
            await submit(client, sid, "查询", request_id="web-full-output", web_search=True)
        ).json()["id"]
        assert (await wait_terminal(client, turn))["status"] == "COMPLETED"
        payload = json.loads(next(m.text for m in captured[-1] if isinstance(m, ToolMessage)))
        assert len(payload["hits"][0]["content"]) == 400
        assert payload["source_id"].startswith("output:")
        full = await client.post(
            f"/api/chat-sessions/{sid}/context/sources/read",
            json={
                "source_id": payload["source_id"],
                "version": payload["version"],
                "quote": "尾部详情",
            },
        )
        assert full.status_code == 200 and full.json()["content"].startswith("尾部详情")
        async with app.state.session_factory() as db:
            row = (await db.scalars(select(ChatContextOutput))).one()
            assert "尾部详情" in row.content and row.inline_content == next(
                m.text for m in captured[-1] if isinstance(m, ToolMessage)
            )
