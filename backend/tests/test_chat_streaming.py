import json
from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, ClassVar, cast

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    UsageMetadata,
)
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from sqlalchemy import update

from app.agents.chat import (
    CHAT_CONTEXT_CHAR_BUDGET,
    ChatContextTooLargeError,
    ContextRow,
    RecordContext,
    build_context_messages,
)
from app.main import create_app
from app.models.chat import ChatMessage
from app.models.document import AiSummary, KnowledgePoint
from app.schemas.chat import ChatRole
from app.services.chat_message_service import ChatMessageService
from app.services.local_config import save_llm_provider

TOKEN = "test-launch-token"

STUB_REPLY = ["回答", "完成", "了"]


def row(row_id: str, role: ChatRole, content: str) -> ContextRow:
    return ContextRow(id=row_id, role=role, content=content)


def chat_rows(count: int, *, prefix: str = "") -> list[ContextRow]:
    """构造 count 个完整 user→assistant 往返轮。"""
    return [
        item
        for index in range(1, count + 1)
        for item in (
            row(f"{prefix}u{index}", ChatRole.USER, f"{prefix}问题{index}"),
            row(f"{prefix}a{index}", ChatRole.ASSISTANT, f"{prefix}回答{index}"),
        )
    ]


class TestBuildContextMessages:
    def test_oversize_assets_are_not_silently_truncated_or_sent_over_budget(self) -> None:
        with pytest.raises(ChatContextTooLargeError):
            build_context_messages(
                [row("current", ChatRole.USER, "追问")],
                record=RecordContext(transcript="长" * 30001, knowledge_points="知" * 60000),
            )

    def test_mounted_transcript_stays_when_oldest_turn_is_trimmed(self) -> None:
        rows = [*chat_rows(2), row("current", ChatRole.USER, "追问")]
        mounted = RecordContext(transcript="原文🧠" * 7500)
        messages = build_context_messages(rows, record=mounted)
        assert mounted.transcript in str(messages[0].content)
        # 上限恰好容纳一轮和当前提问，下一字符才触发裁剪。
        required = len(str(messages[0].content)) + 8
        trimmed = build_context_messages(rows, record=mounted, budget=required)
        assert [message.content for message in trimmed[1:]] == ["问题2", "回答2", "追问"]
        assert trimmed[0].content == messages[0].content
        under = build_context_messages(rows, record=mounted, budget=required - 1)
        assert [message.content for message in under[1:]] == ["追问"]

    def test_long_transcript_uses_assets_and_only_last_three_completed_turns_excerpts(self) -> None:
        rows = [
            item
            for index in range(1, 5)
            for item in (
                row(f"u{index}", ChatRole.USER, f"问题{index}"),
                ContextRow(
                    id=f"a{index}",
                    role=ChatRole.ASSISTANT,
                    content=f"回答{index}",
                    cited_excerpts=(f"摘录{index}",),
                ),
            )
        ]
        rows.append(row("pending", ChatRole.USER, "尚未回复"))
        transcript = "长" * 30001 + "摘录1 摘录2 摘录3 摘录4"
        messages = build_context_messages(
            rows,
            record=RecordContext(
                transcript=transcript, summary="已确认摘要", knowledge_points="知识点全文"
            ),
        )
        source = str(messages[0].content)
        assert transcript not in source
        assert "已确认摘要" in source and "知识点全文" in source
        assert "摘录1" not in source
        assert all(f"摘录{index}" in source for index in (2, 3, 4))
        assert messages[-1].content == "尚未回复"

    def test_keeps_system_snapshot_first_with_stable_row_id(self) -> None:
        messages = build_context_messages(
            [
                row("sys", ChatRole.SYSTEM, "你是学习助手"),
                row("u1", ChatRole.USER, "问题"),
                row("a1", ChatRole.ASSISTANT, "回答"),
            ]
        )

        assert len(messages) == 3
        assert isinstance(messages[0], SystemMessage)
        assert messages[0].content == "你是学习助手"
        assert messages[0].id == "sys"
        assert isinstance(messages[1], HumanMessage)
        assert isinstance(messages[2], AIMessage)
        assert [message.id for message in messages] == ["sys", "u1", "a1"]

    def test_window_keeps_last_ten_turns_and_drops_oldest(self) -> None:
        messages = build_context_messages([row("sys", ChatRole.SYSTEM, "S"), *chat_rows(11)])

        contents = [message.content for message in messages]
        assert "问题1" not in contents
        assert "回答1" not in contents
        assert "问题2" in contents
        assert "问题11" in contents and "回答11" in contents
        # SYSTEM + 10 轮 × 2 条 = 21 条
        assert len(messages) == 21

    def test_trailing_unanswered_user_counts_as_current_turn(self) -> None:
        # 10 个完成轮全部在窗口内，末尾未回复 user 作为当前提问额外附加、不占窗口。
        messages = build_context_messages(
            [row("sys", ChatRole.SYSTEM, "S"), *chat_rows(10), row("u11", ChatRole.USER, "追问")]
        )

        contents = [message.content for message in messages]
        assert "问题1" in contents
        assert "追问" in contents
        assert len(messages) == 1 + 10 * 2 + 1

    def test_interrupted_turn_excluded_from_completed_turn_count(self) -> None:
        # 中断轮（孤立 user）不计入 10 轮窗口：9 完整轮 + 孤立 user 时最旧完整轮保留。
        messages = build_context_messages(
            [
                row("sys", ChatRole.SYSTEM, "S"),
                *chat_rows(9),
                row("u10", ChatRole.USER, "中断的问题"),
            ]
        )

        contents = [message.content for message in messages]
        assert "问题1" in contents  # 只有 9 个完整轮 + 当前孤立 user = 10 轮内
        assert "中断的问题" in contents

    def test_budget_drops_oldest_turns_until_within_budget(self) -> None:
        # 每轮 6 字符（"问题N"+"回答N"），SYSTEM 1 字符：budget=19 恰容 3 轮。
        messages = build_context_messages(
            [row("sys", ChatRole.SYSTEM, "S"), *chat_rows(5)],
            budget=19,
        )

        contents = [message.content for message in messages]
        assert "问题1" not in contents and "问题2" not in contents
        assert "问题3" in contents and "回答5" in contents

    def test_budget_never_drops_current_question(self) -> None:
        messages = build_context_messages(
            [
                row("sys", ChatRole.SYSTEM, "S"),
                *chat_rows(3),
                row("u4", ChatRole.USER, "这是一个相当长的当前提问" * 20),
            ],
            budget=50,
        )

        contents = [message.content for message in messages]
        assert "这是一个相当长的当前提问" * 20 in contents
        assert "问题3" not in contents

    def test_skips_tool_rows(self) -> None:
        messages = build_context_messages(
            [
                row("sys", ChatRole.SYSTEM, "S"),
                row("u1", ChatRole.USER, "问题"),
                row("t1", ChatRole.TOOL, "工具输出"),
                row("a1", ChatRole.ASSISTANT, "回答"),
            ]
        )

        assert [message.content for message in messages] == ["S", "问题", "回答"]

    def test_default_budget_constant(self) -> None:
        assert CHAT_CONTEXT_CHAR_BUDGET == 60000


class StubChatModel(BaseChatModel):
    """测试缝隙：捕获喂入的消息列表，按队列逐 token 吐出预设回复。

    replies 队列元素为分片列表；None 表示该次调用抛错（注入供应商故障）。
    captured / replies 用类级共享（ClassVar），跨每请求新建的实例累积。
    """

    captured: ClassVar[list[list[AnyMessage]]] = []
    replies: ClassVar[list[list[str] | None]] = []

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

    async def _astream(
        self,
        messages: Any,
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        type(self).captured.append(list(messages))
        reply = type(self).replies.pop(0)
        if reply is None:
            raise RuntimeError("stub provider down")
        for index, part in enumerate(reply):
            usage = (
                UsageMetadata(input_tokens=3, output_tokens=4, total_tokens=7)
                if index == len(reply) - 1
                else None
            )
            yield ChatGenerationChunk(message=AIMessageChunk(content=part, usage_metadata=usage))

    def bind(self, **kwargs: Any) -> Any:  # pyright: ignore[reportIncompatibleMethodOverride]
        return self

    def bind_tools(self, tools: Any, **kwargs: Any) -> "StubChatModel":
        return self


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@asynccontextmanager
async def streaming_chat_app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    replies: Sequence[list[str] | None] | None = None,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient, list[list[AnyMessage]]]]:
    captured: list[list[AnyMessage]] = []
    queue: list[list[str] | None] = list(replies) if replies is not None else [list(STUB_REPLY)]

    class _StubChatOpenAI(StubChatModel):
        pass

    _StubChatOpenAI.captured = captured
    _StubChatOpenAI.replies = queue
    monkeypatch.setattr("app.agents.llm.ChatOpenAI", _StubChatOpenAI)

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
            yield app, client, captured


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
        json={"content": content},
    ) as response:
        assert response.status_code == 200
        return await read_sse(response)


async def message_rows(data_dir: Path, session_id: str) -> list[tuple[str, str]]:
    async with aiosqlite.connect(data_dir / "knowrealm.db") as connection:
        return [
            (cast(str, item[0]), cast(str, item[1]))
            for item in await (
                await connection.execute(
                    "SELECT role, content FROM chat_messages"
                    " WHERE session_id = ? ORDER BY created_at, id",
                    (session_id,),
                )
            ).fetchall()
        ]


async def chat_log_rows(data_dir: Path) -> list[Sequence[Any]]:
    async with aiosqlite.connect(data_dir / "knowrealm.db") as connection:
        return list(
            await (
                await connection.execute(
                    "SELECT graph_name, graph_node, model, prompt_version,"
                    " token_usage_json, error_code FROM llm_call_logs"
                    " WHERE graph_name = 'chat'"
                )
            ).fetchall()
        )


async def create_session(client: httpx.AsyncClient) -> str:
    created = await client.post("/api/chat-sessions", json={})
    assert created.status_code == 201
    return cast(str, created.json()["id"])


@pytest.mark.anyio
async def test_mounted_stream_reads_current_transcript_without_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with streaming_chat_app(tmp_path, monkeypatch, replies=[list(STUB_REPLY)] * 2) as (
        _app,
        client,
        captured,
    ):
        await client.put(
            "/api/profile", json={"primary_role": "DEVELOPER", "about_me": "角色专用文本"}
        )
        capture = await client.post(
            "/api/text-captures", json={"capture_type": "QUICK_NOTE", "content": "原始公式 x+y"}
        )
        assert capture.status_code == 201
        record_id = capture.json()["record_id"]
        created = await client.post("/api/chat-sessions", json={"record_id": record_id})
        assert created.status_code == 201
        session_id = created.json()["id"]
        assert (await send_message(client, session_id, "后面那个公式？"))[-1][0] == "done"
        prompt = str(captured[0][0].content)
        assert "原始公式 x+y" in prompt
        assert "角色专用文本" not in prompt and "程序员" not in prompt

        edited = await client.patch(
            f"/api/records/{record_id}/transcript",
            json={"content": "修订公式 x-y", "expected_source_version": 1},
        )
        assert edited.status_code == 200
        assert (await send_message(client, session_id, "现在的公式？"))[-1][0] == "done"
        assert "修订公式 x-y" in str(captured[1][0].content)
        assert "原始公式 x+y" not in str(captured[1][0].content)
        assert "后面那个公式？" in [message.content for message in captured[1]]


@pytest.mark.anyio
async def test_long_mounted_stream_reads_confirmed_assets_and_valid_citations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with streaming_chat_app(tmp_path, monkeypatch, replies=[list(STUB_REPLY)] * 2) as (
        app,
        client,
        captured,
    ):
        transcript = "长" * 30001 + "可核实摘录"
        capture = await client.post(
            "/api/text-captures", json={"capture_type": "QUICK_NOTE", "content": transcript}
        )
        record_id = capture.json()["record_id"]
        created = await client.post("/api/chat-sessions", json={"record_id": record_id})
        session_id = created.json()["id"]
        await send_message(client, session_id, "先提问")
        async with app.state.session_factory() as session, session.begin():
            for index, status in enumerate(("CONFIRMED", "GENERATED", "SUPERSEDED"), 1):
                session.add(
                    AiSummary(
                        record_id=record_id,
                        version_no=index,
                        transcript_source_version=1,
                        topic=f"主题{status}",
                        abstract=f"摘要{status}",
                        summary_json=json.dumps(
                            {"sections": [{"heading": "细节", "points": [f"要点{status}"]}]}
                        ),
                        status=status,
                        model="stub",
                        prompt_version="stub",
                        token_usage_json="{}",
                        latency_ms=0,
                    )
                )
            for status in ("ACTIVE", "DRAFT", "SUPERSEDED"):
                session.add(
                    KnowledgePoint(
                        record_id=record_id,
                        name=f"知识点{status}",
                        detail=f"完整详情{status}",
                        tags="[]",
                        importance=3,
                        generation_status=status,
                    )
                )
            await session.execute(
                update(ChatMessage)
                .where(
                    ChatMessage.session_id == session_id,
                    ChatMessage.role == ChatRole.ASSISTANT,
                )
                .values(
                    citations_json=json.dumps(
                        [
                            {"record_id": record_id, "quote": "可核实摘录"},
                            {"record_id": record_id, "quote": "不存在的摘录"},
                            {"record_id": "other-record", "quote": "长"},
                        ]
                    )
                )
            )
        assert (await send_message(client, session_id, "再问细节"))[-1][0] == "done"
        prompt = str(captured[1][0].content)
        assert transcript not in prompt
        assert "摘要CONFIRMED" in prompt and "要点CONFIRMED" in prompt
        assert "知识点ACTIVE" in prompt and "完整详情ACTIVE" in prompt
        assert "可核实摘录" in prompt and "不存在的摘录" not in prompt
        assert "GENERATED" not in prompt and "SUPERSEDED" not in prompt and "DRAFT" not in prompt
        async with app.state.session_factory() as session, session.begin():
            session.add_all(
                [
                    KnowledgePoint(
                        record_id=record_id,
                        name=f"补充知识点{index}",
                        detail="长" * 2000,
                        tags="[]",
                        importance=3,
                        generation_status="ACTIVE",
                    )
                    for index in range(31)
                ]
            )
        oversized = await send_message(client, session_id, "材料过长时不发送给模型")
        assert [event for event, _ in oversized] == ["status", "error"]
        assert oversized[-1][1]["code"] == "CHAT_CONTEXT_TOO_LARGE"
        assert len(captured) == 2


@pytest.mark.anyio
async def test_send_message_streams_status_tokens_then_done_and_persists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with streaming_chat_app(tmp_path, monkeypatch) as (_app, client, _captured):
        saved = await client.put(
            "/api/profile",
            json={"primary_role": "DEVELOPER", "about_me": "三年后端"},
        )
        assert saved.status_code == 200
        session_id = await create_session(client)

        events = await send_message(client, session_id, "什么是 MVCC")

        names = [name for name, _payload in events]
        assert names[0] == "status"
        assert names[1:-1] == ["token"] * (len(names) - 2)
        assert names[-1] == "done"
        assert events[0][1] == {"phase": "generating"}
        tokens = [payload["text"] for name, payload in events if name == "token"]
        assert tokens == STUB_REPLY
        assert events[-1][1]["content"] == "回答完成了"

        # 用户与助手消息都落库；SYSTEM 快照仍在最前（角色在建档后创建的会话生效）。
        rows = await message_rows(tmp_path, session_id)
        assert rows[0][0] == "SYSTEM"
        assert "程序员" in rows[0][1]
        assert ("USER", "什么是 MVCC") in rows
        assert ("ASSISTANT", "回答完成了") in rows

        # 重开会话：历史接口完整返回，assistant 行带模型名。
        history = await client.get(f"/api/chat-sessions/{session_id}/messages")
        assert history.status_code == 200
        body = history.json()
        assert [item["role"] for item in body] == ["SYSTEM", "USER", "ASSISTANT"]
        assert body[2]["model"] == "stub-chat-model"
        assert body[2]["content"] == "回答完成了"

        # 会话标题默认取首条用户消息。
        detail = await client.get(f"/api/chat-sessions/{session_id}")
        assert detail.json()["title"] == "什么是 MVCC"


@pytest.mark.anyio
async def test_context_contains_system_snapshot_and_last_ten_turns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with streaming_chat_app(tmp_path, monkeypatch, replies=[list(STUB_REPLY)] * 12) as (
        _app,
        client,
        captured,
    ):
        session_id = await create_session(client)

        for index in range(1, 12):
            events = await send_message(client, session_id, f"问题{index}")
            assert events[-1][0] == "done"

        # 第 11 次发送时历史恰有 10 个完成轮：SYSTEM 快照 + 10 轮 + 当前提问。
        eleventh = captured[10]
        assert eleventh[0].type == "system"
        assert "学习助手" in str(eleventh[0].content)
        contents = [str(message.content) for message in eleventh]
        assert "问题1" in contents and "问题10" in contents and "问题11" in contents
        assert contents.count("回答完成了") == 10
        assert len(eleventh) == 1 + 10 * 2 + 1

        # 存在 11 个完成轮后再发送：最旧轮不进上下文。
        await send_message(client, session_id, "问题12")
        contents = [str(message.content) for message in captured[11]]
        assert "问题1" not in contents
        assert "问题2" in contents and "问题12" in contents
        assert contents.count("回答完成了") == 10


@pytest.mark.anyio
async def test_interrupted_stream_keeps_user_row_and_skips_assistant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with streaming_chat_app(tmp_path, monkeypatch, replies=[list(STUB_REPLY)] * 2) as (
        app,
        client,
        _captured,
    ):
        session_id = await create_session(client)
        accepted = await ChatMessageService.accept(
            session_factory=app.state.session_factory,
            data_dir=app.state.data_dir,
            registry=app.state.chat_stream_registry,
            session_id=session_id,
            content="会被中断的问题",
        )
        stream = ChatMessageService.stream_events(
            session_factory=app.state.session_factory,
            checkpointer=app.state.chat_checkpointer,
            registry=app.state.chat_stream_registry,
            accepted=accepted,
        )
        assert (await anext(stream)).event == "status"
        assert (await anext(stream)).event == "token"
        # 模拟客户端断开：真实 uvicorn 下客户端断连时 starlette 会 aclose 响应流
        # 生成器（经探针验证，ASGITransport 提前退出不会传导断开，故直接在生成器边界验证）。
        await stream.aclose()

        rows = await message_rows(tmp_path, session_id)
        assert ("USER", "会被中断的问题") in rows
        assert all(role != "ASSISTANT" for role, _content in rows)

        # 中断释放了在途锁：同一会话可再次发送；补答复用原 user 行，无重复提问。
        events = await send_message(client, session_id, "会被中断的问题")
        assert events[-1][0] == "done"
        rows = await message_rows(tmp_path, session_id)
        assert [content for role, content in rows if role == "USER"].count("会被中断的问题") == 1
        assert ("ASSISTANT", "回答完成了") in rows


@pytest.mark.anyio
async def test_second_send_while_streaming_returns_409(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with streaming_chat_app(tmp_path, monkeypatch) as (app, client, _captured):
        session_id = await create_session(client)
        assert app.state.chat_stream_registry.acquire(session_id)

        conflict = await client.post(
            f"/api/chat-sessions/{session_id}/messages", json={"content": "第二条"}
        )
        assert conflict.status_code == 409
        assert "CHAT_STREAM_IN_PROGRESS" in conflict.json()["detail"]

        app.state.chat_stream_registry.release(session_id)


@pytest.mark.anyio
async def test_provider_failure_emits_error_and_chat_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with streaming_chat_app(tmp_path, monkeypatch, replies=[None, list(STUB_REPLY)]) as (
        _app,
        client,
        _captured,
    ):
        session_id = await create_session(client)

        events = await send_message(client, session_id, "第一次提问")
        assert events[0][0] == "status"
        assert events[-1][0] == "error"
        assert events[-1][1]["code"] == "CHAT_STREAM_FAILED"
        assert not any(name == "done" for name, _payload in events)

        # 失败不落 assistant 行；error 后可继续发问并成功。
        rows = await message_rows(tmp_path, session_id)
        assert all(role != "ASSISTANT" for role, _content in rows)
        retry = await send_message(client, session_id, "第一次提问")
        assert retry[-1][0] == "done"
        rows = await message_rows(tmp_path, session_id)
        assert ("ASSISTANT", "回答完成了") in rows


@pytest.mark.anyio
async def test_llm_call_logs_records_metadata_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with streaming_chat_app(tmp_path, monkeypatch) as (_app, client, _captured):
        session_id = await create_session(client)
        await send_message(client, session_id, "记录埋点")

        rows = await chat_log_rows(tmp_path)
        assert len(rows) == 1
        graph_name, graph_node, model, prompt_version, token_usage_json, error_code = rows[0]
        assert (graph_name, graph_node, model) == (
            "chat",
            "generate",
            "stub-chat-model",
        )
        assert prompt_version
        assert "total_tokens" in cast(str, token_usage_json)
        assert error_code is None

        # 表结构不含对话正文的落点；日志记录只有元数据列（迁移 0008 定义的列集）。
        async with aiosqlite.connect(tmp_path / "knowrealm.db") as connection:
            columns = {
                cast(str, item[1])
                for item in await (
                    await connection.execute("PRAGMA table_info(llm_call_logs)")
                ).fetchall()
            }
        assert columns == {
            "id",
            "request_id",
            "graph_name",
            "graph_node",
            "model",
            "prompt_version",
            "embedding_model",
            "token_usage_json",
            "latency_ms",
            "retrieval_count",
            "evidence_count",
            "interrupt_count",
            "error_code",
            "created_at",
        }


@pytest.mark.anyio
async def test_send_without_provider_returns_semantic_409(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.agents.llm.ChatOpenAI", StubChatModel)
    app = create_app(data_dir=tmp_path, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            session_id = await create_session(client)
            response = await client.post(
                f"/api/chat-sessions/{session_id}/messages",
                json={"content": "没配置供应商"},
            )
            assert response.status_code == 409
            assert "LLM_PROVIDER_UNCONFIGURED" in response.json()["detail"]
            rows = await message_rows(tmp_path, session_id)
            assert all(role != "USER" for role, _content in rows)


@pytest.mark.anyio
async def test_send_validates_payload_and_missing_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with streaming_chat_app(tmp_path, monkeypatch) as (_app, client, _captured):
        blank = await client.post(
            "/api/chat-sessions/00000000-0000-4000-8000-000000000001/messages",
            json={"content": "   "},
        )
        assert blank.status_code == 422

        missing = await client.post(
            "/api/chat-sessions/00000000-0000-4000-8000-000000000002/messages",
            json={"content": "不存在的会话"},
        )
        assert missing.status_code == 404

        history_missing = await client.get(
            "/api/chat-sessions/00000000-0000-4000-8000-000000000002/messages"
        )
        assert history_missing.status_code == 404
