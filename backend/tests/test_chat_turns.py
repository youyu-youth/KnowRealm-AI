"""ChatTurn 切换会话与持久控制（票 01）验收：T01～T04、T06、T05 普通提案、
T11 当前轮次取消、T19 活动删除、T21 迁移持久化与启动对账。

公开 API + 真实 JobRunner（双 CHAT_TURN 槽）+ 迁移后临时 SQLite；模型用可控
替身（GatedReply 挂起＝「生成在途」的确定性窗口），数据库写入 / 领取 / 业务
回执不以 mock 替代。
"""

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, cast

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, AnyMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult

from app.db.migrations import run_migrations, supported_user_version
from app.main import create_app
from app.modules.settings.config import save_llm_provider

TOKEN = "test-launch-token"
STUB_REPLY = ["回答", "完成", "了"]


@dataclass(frozen=True)
class ToolCallReply:
    tool: str
    args: dict[str, Any]
    call_id: str = "call-1"


@dataclass(frozen=True)
class GatedReply:
    """挂起回复：先吐 prefix 分片再等 release（「生成在途」确定性窗口）。"""

    prefix: tuple[str, ...]
    release: asyncio.Event
    rest: tuple[str, ...] = ("收尾",)


StubReply = list[str] | ToolCallReply | GatedReply | None


class StubChatModel(BaseChatModel):
    captured: ClassVar[list[list[AnyMessage]]] = []
    replies: ClassVar[list[StubReply]] = []

    @property
    def _llm_type(self) -> str:
        return "stub-test"

    def _generate(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
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
        if isinstance(reply, GatedReply):
            for part in reply.prefix:
                yield ChatGenerationChunk(message=AIMessageChunk(content=part))
            await reply.release.wait()
            for part in reply.rest:
                yield ChatGenerationChunk(message=AIMessageChunk(content=part))
            return
        if isinstance(reply, ToolCallReply):
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {
                            "name": reply.tool,
                            "args": json.dumps(reply.args, ensure_ascii=False),
                            "id": reply.call_id,
                            "index": 0,
                        }
                    ],
                )
            )
            return
        if reply is None:
            raise RuntimeError("stub provider down")
        for part in reply:
            yield ChatGenerationChunk(message=AIMessageChunk(content=part))

    def bind(self, **kwargs: Any) -> Any:
        return self

    def bind_tools(self, tools: Any, **kwargs: Any) -> "StubChatModel":
        return self


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@asynccontextmanager
async def turns_app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    replies: list[StubReply] | None = None,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient, list[list[AnyMessage]]], None]:
    captured: list[list[AnyMessage]] = []
    queue: list[StubReply] = list(replies) if replies is not None else [list(STUB_REPLY)]

    class _StubChatOpenAI(StubChatModel):
        pass

    _StubChatOpenAI.captured = captured
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
            yield app, client, captured


async def create_session(client: httpx.AsyncClient, **body: Any) -> str:
    created = await client.post("/api/chat-sessions", json=body or {})
    assert created.status_code == 201
    return cast(str, created.json()["id"])


async def submit(
    client: httpx.AsyncClient,
    session_id: str,
    content: str,
    *,
    request_id: str,
    web_search: bool = False,
    auth_mode: str | None = None,
    page: dict[str, Any] | None = None,
) -> httpx.Response:
    body: dict[str, Any] = {
        "content": content,
        "web_search": web_search,
        "request_id": request_id,
    }
    if auth_mode is not None:
        body["auth_mode"] = auth_mode
    if page is not None:
        body["page"] = page
    return await client.post(f"/api/chat-sessions/{session_id}/turns", json=body)


async def snapshot(client: httpx.AsyncClient, turn_id: str) -> dict[str, Any]:
    return cast(dict[str, Any], (await client.get(f"/api/chat-turns/{turn_id}")).json())


async def wait_terminal(
    client: httpx.AsyncClient, turn_id: str, timeout_seconds: float = 15.0
) -> dict[str, Any]:
    for _ in range(int(timeout_seconds / 0.1)):
        body = await snapshot(client, turn_id)
        if body["status"] in ("COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"):
            return body
        await asyncio.sleep(0.1)
    pytest.fail(f"轮次未达终态: {turn_id}")


async def wait_running_progress(client: httpx.AsyncClient, turn_id: str, min_seq: int) -> None:
    for _ in range(150):
        body = await snapshot(client, turn_id)
        if body["status"] == "RUNNING" and body["last_seq"] >= min_seq:
            return
        if body["status"] in ("COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"):
            pytest.fail(f"轮次提前终态: {body['status']}")
        await asyncio.sleep(0.1)
    pytest.fail("轮次未推进")


async def read_sse(response: httpx.Response) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    event_name: str | None = None
    data_lines: list[str] = []
    async for line in response.aiter_lines():
        if line == "":
            if event_name is not None:
                events.append((event_name, json.loads("\n".join(data_lines))))
            event_name, data_lines = None, []
        elif line.startswith("event:"):
            event_name = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").strip())
    return events


async def drain_events(
    client: httpx.AsyncClient, turn_id: str, after_seq: int = 0
) -> list[tuple[str, dict[str, Any]]]:
    async with client.stream(
        "GET", f"/api/chat-turns/{turn_id}/events?after_seq={after_seq}"
    ) as response:
        assert response.status_code == 200
        return await read_sse(response)


async def db_rows(data_dir: Path, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    async with aiosqlite.connect(data_dir / "knowrealm.db") as connection:
        return [
            cast(tuple[Any, ...], row)
            for row in await (await connection.execute(sql, params)).fetchall()
        ]


# ---------------------------------------------------------------------------
# T01：会话 A 生成时切到 B 再返回——A 不中断、不重执行，B 独立推进。


@pytest.mark.anyio
async def test_t01_switch_to_b_keeps_a_running_and_b_progresses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate_a = asyncio.Event()
    replies: list[StubReply] = [
        GatedReply(prefix=("A-", "部分"), release=gate_a),
        list(STUB_REPLY),
    ]
    async with turns_app(tmp_path, monkeypatch, replies=replies) as (_app, client, captured):
        session_a = await create_session(client)
        session_b = await create_session(client)

        # A 提交后离开（不订阅事件，仅持轮次身份）。
        submitted_a = await submit(client, session_a, "问题 A", request_id="req-t01-a-0001")
        assert submitted_a.status_code == 202
        turn_a = cast(str, submitted_a.json()["id"])
        await wait_running_progress(client, turn_a, min_seq=1)

        # 切到 B：B 独立领取另一执行槽并完成（A 仍挂起占用其槽）。
        events_b = await drain_events_after_submit(client, session_b, "req-t01-b-0001")
        assert events_b[-1][0] == "done"

        # 返回 A：未取消、未重执行（模型仍只有 A 的首轮调用），部分输出可见。
        state_a = await snapshot(client, turn_a)
        assert state_a["status"] == "RUNNING"
        assert state_a["cancel_requested"] is False
        assert state_a["output_text"] == "A-部分"
        assert len([call for call in captured]) == 2  # A 首轮 + B 首轮，各恰一次

        # 释放 A：完成并落最终消息（离开期间无第二次执行）。
        gate_a.set()
        events_a = await drain_events(client, turn_a)
        assert events_a[-1][0] == "done"
        history = cast(
            list[dict[str, Any]],
            (await client.get(f"/api/chat-sessions/{session_a}/messages")).json(),
        )
        visible_roles = [item["role"] for item in history if item["role"] != "SYSTEM"]
        assert visible_roles == ["USER", "ASSISTANT"]


async def drain_events_after_submit(
    client: httpx.AsyncClient, session_id: str, request_id: str
) -> list[tuple[str, dict[str, Any]]]:
    submitted = await submit(
        client, session_id, request_id.removeprefix("req-"), request_id=request_id
    )
    assert submitted.status_code == 202, submitted.text
    turn_id = cast(str, submitted.json()["id"])
    return await drain_events(client, turn_id)


# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_active_turn_list_carries_partial_output_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """返回会话（active_only 列表）能看到部分输出与过程投影（spec §15）。"""
    gate = asyncio.Event()
    replies: list[StubReply] = [GatedReply(prefix=("部分", "输出"), release=gate)]
    async with turns_app(tmp_path, monkeypatch, replies=replies) as (_app, client, _c):
        session_id = await create_session(client)
        submitted = await submit(client, session_id, "离开中", request_id="req-active-01")
        turn_id = cast(str, submitted.json()["id"])
        await wait_running_progress(client, turn_id, min_seq=1)

        listed = await client.get(f"/api/chat-sessions/{session_id}/turns?active_only=true&limit=1")
        assert listed.status_code == 200
        body = listed.json()
        assert len(body["turns"]) == 1
        active = body["turns"][0]
        assert active["id"] == turn_id
        assert active["output_text"] == "部分输出"
        assert active["process"] is not None
        assert active["process"]["status"] == "RUNNING"

        cancelled = await client.post(f"/api/chat-turns/{turn_id}/cancel")
        assert cancelled.status_code == 200
        await wait_terminal(client, turn_id)
        gate.set()


@pytest.mark.anyio
async def test_turn_cancel_guard_middleware_blocks_model_and_tool() -> None:
    """取消标记已置位时：模型前与工具前中止（副作用前最后一道闸，spec §2/§14）。"""
    from langchain_core.messages import ToolMessage

    from app.modules.agent.middleware.cancel_guard import (
        TurnCancelGuardMiddleware,
        TurnCancelledError,
    )

    cancelled = asyncio.Event()
    guard = TurnCancelGuardMiddleware(cancelled.is_set)

    async def handler(_request: object) -> ToolMessage:
        raise AssertionError("取消后不应执行工具")

    cancelled.set()
    with pytest.raises(TurnCancelledError):
        await guard.abefore_model(None, None)
    with pytest.raises(TurnCancelledError):
        await guard.awrap_tool_call(cast(Any, object()), cast(Any, handler))

    cancelled.clear()
    tool_message = ToolMessage(content="ok", tool_call_id="t1")

    async def pass_through(_request: object) -> ToolMessage:
        return tool_message

    result = await guard.awrap_tool_call(cast(Any, object()), cast(Any, pass_through))
    assert result is tool_message


# ---------------------------------------------------------------------------
# T02：离开期间完成——返回直接看到最终消息与真实回执。


@pytest.mark.anyio
async def test_t02_completion_while_away_shows_final_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with turns_app(tmp_path, monkeypatch) as (_app, client, _captured):
        session_id = await create_session(client)
        submitted = await submit(
            client, session_id, "离开期间完成的问题", request_id="req-t02-0001"
        )
        turn_id = cast(str, submitted.json()["id"])
        # 不订阅（模拟离开），轮询快照直到完成。
        final = await wait_terminal(client, turn_id)
        assert final["status"] == "COMPLETED"
        assert final["final_message_id"] is not None
        # 返回会话：历史已含最终消息，订阅端点仍可补发完整 done 事件。
        history = cast(
            list[dict[str, Any]],
            (await client.get(f"/api/chat-sessions/{session_id}/messages")).json(),
        )
        visible = [item for item in history if item["role"] != "SYSTEM"]
        assert [item["role"] for item in visible] == ["USER", "ASSISTANT"]
        assert visible[1]["content"] == "回答完成了"
        events = await drain_events(client, turn_id)
        assert events[0][0] == "status"
        assert events[-1][0] == "done"
        assert events[-1][1]["content"] == "回答完成了"
        # done 事件 payload 与最终消息一致（权威正文，不重复拼接 token）。
        tokens = "".join(payload["text"] for name, payload in events if name == "token")
        assert tokens == events[-1][1]["content"]


# ---------------------------------------------------------------------------
# T03：刷新 / 重复订阅 / 事件缺口——游标补发不丢不重。


@pytest.mark.anyio
async def test_t03_resubscribe_with_cursor_no_loss_or_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with turns_app(tmp_path, monkeypatch) as (_app, client, _captured):
        session_id = await create_session(client)
        submitted = await submit(client, session_id, "游标补发", request_id="req-t03-0001")
        turn_id = cast(str, submitted.json()["id"])
        full = await drain_events(client, turn_id)
        assert full[-1][0] == "done"
        last_seq = (await snapshot(client, turn_id))["last_seq"]

        # 刷新重连：从快照 last_seq 续订——终态轮只有首导 status（无重复事件）。
        resumed = await drain_events(client, turn_id, after_seq=last_seq)
        assert [name for name, _payload in resumed] == ["status"]

        # 缺口补拉：从中间游标重放，后缀与前缀拼起来等于全量（重复 seq 忽略由
        # 客户端按 seq 去重；服务端只按游标返回未提交过的缺口）。
        prefix = await drain_events(client, turn_id, after_seq=1)
        names_full = [name for name, _payload in full]
        names_prefix = [name for name, _payload in prefix]
        # after_seq=1 的重放含首导 status（连接级事件），其后为 seq>1 的缺口
        # （对应全量去掉首个事件），拼起来无丢失、无重复。
        assert names_prefix[1:] == names_full[2:]


# ---------------------------------------------------------------------------
# T04：request_id 幂等 / 指纹冲突 / 配置漂移 / 并发提交。


@pytest.mark.anyio
async def test_t04_request_id_idempotency_and_conflicts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replies = cast("list[StubReply]", [list(STUB_REPLY)] * 3)
    async with turns_app(tmp_path, monkeypatch, replies=replies) as (
        _app,
        client,
        _captured,
    ):
        session_id = await create_session(client)

        # 相同 request_id + 相同内容 → 原轮次（网络重试语义）。
        first = await submit(client, session_id, "幂等问题", request_id="req-t04-0001")
        assert first.status_code == 202
        turn_id = cast(str, first.json()["id"])
        retry = await submit(client, session_id, "幂等问题", request_id="req-t04-0001")
        assert retry.status_code == 202
        assert retry.json()["id"] == turn_id
        await wait_terminal(client, turn_id)
        # 终态后同身份重试仍返回原轮次（不复用身份创建新轮次）。
        after_terminal = await submit(client, session_id, "幂等问题", request_id="req-t04-0001")
        assert after_terminal.status_code == 202
        assert after_terminal.json()["id"] == turn_id
        rows = await db_rows(
            tmp_path,
            "SELECT count(*) FROM chat_messages WHERE session_id = ? AND role = 'USER'",
            (session_id,),
        )
        assert rows[0][0] == 1  # 只有一组 user 消息（幂等不重复落库）

        # 同身份不同内容 → 明确冲突。
        conflict = await submit(client, session_id, "不同内容", request_id="req-t04-0001")
        assert conflict.status_code == 409
        assert "CHAT_TURN_REQUEST_CONFLICT" in conflict.json()["detail"]

        # 全局配置变化不改变原请求指纹：换模型后同身份同内容重试仍是原轮次。
        save_llm_provider(
            tmp_path,
            base_url="https://stub.example.com/v1",
            api_key="sk-test",
            model="another-model",
            clear_api_key=False,
        )
        drifted = await submit(client, session_id, "幂等问题", request_id="req-t04-0001")
        assert drifted.status_code == 202
        assert drifted.json()["id"] == turn_id

        # 并发相同提交（gather）：只有一组 user 消息 / 轮次 / job。
        concurrent_session = await create_session(client)
        results = await asyncio.gather(
            submit(client, concurrent_session, "并发问题", request_id="req-t04-0002"),
            submit(client, concurrent_session, "并发问题", request_id="req-t04-0002"),
        )
        assert all(result.status_code == 202 for result in results)
        assert len({result.json()["id"] for result in results}) == 1
        counts = await db_rows(
            tmp_path,
            "SELECT (SELECT count(*) FROM chat_turns WHERE session_id = ?),"
            " (SELECT count(*) FROM chat_turn_events WHERE turn_id = ?)",
            (concurrent_session, results[0].json()["id"]),
        )
        assert counts[0][0] == 1


# ---------------------------------------------------------------------------
# T05（普通提案）：提案不阻塞轮次完成与下一轮提问。


@pytest.mark.anyio
async def test_t05_normal_proposal_does_not_block_turn_or_next_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replies: list[StubReply] = [
        ToolCallReply(
            "create_course",
            {"name": "提案课", "learning_context": "INTEREST", "depth": "BEGINNER"},
        ),
        ["提案已创建。"],
        list(STUB_REPLY),
    ]
    async with turns_app(tmp_path, monkeypatch, replies=replies) as (_app, client, _captured):
        session_id = await create_session(client)
        first = await drain_events_after_submit(client, session_id, "req-t05-0001")
        done = first[-1]
        assert done[0] == "done"
        assert done[1]["content"] == "提案已创建。"
        assert any(name == "tool_result" for name, _payload in first)
        # 提案保留待确认（独立入口处理），轮次正常完成。
        proposal_rows = await db_rows(
            tmp_path,
            "SELECT proposal_type, status FROM agent_proposals WHERE session_id = ?",
            (session_id,),
        )
        assert proposal_rows == [("COURSE_CREATE", "PENDING")]
        # 下一轮提问创建新轮次并完成。
        second = await drain_events_after_submit(client, session_id, "req-t05-0002")
        assert second[-1][0] == "done"


# ---------------------------------------------------------------------------
# T06：单槽故障只收口对应轮次，另一槽继续（针对性收口，不全局重置）。


@pytest.mark.anyio
async def test_t06_slot_failure_is_targeted_and_other_slot_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.agent.turns.worker as turns_worker

    original_writeback = turns_worker.writeback
    failing_job_ids: set[str] = set()

    async def flaky_writeback(ctx: Any, result: Any, *, session_factory: Any) -> bool:
        if ctx.job_id in failing_job_ids:
            raise RuntimeError("writeback storage unavailable")
        return await original_writeback(ctx, result, session_factory=session_factory)

    monkeypatch.setattr(turns_worker, "writeback", flaky_writeback)
    gate = asyncio.Event()
    replies: list[StubReply] = [
        GatedReply(prefix=("故障轮",), release=gate),  # A 轮：writeback 被注入失败
        list(STUB_REPLY),  # B 轮：另一槽正常完成
        list(STUB_REPLY),  # A 会话后续新问（槽已恢复）
    ]
    async with turns_app(tmp_path, monkeypatch, replies=replies) as (_app, client, _captured):
        session_a = await create_session(client)
        session_b = await create_session(client)
        submitted_a = await submit(client, session_a, "故障轮问题", request_id="req-t06-0001")
        turn_a = cast(str, submitted_a.json()["id"])
        await wait_running_progress(client, turn_a, min_seq=1)

        # B 轮在另一槽正常完成（A 故障不影响兄弟槽）。
        events_b = await drain_events_after_submit(client, session_b, "req-t06-0002")
        assert events_b[-1][0] == "done"

        # 标记 A 的 job 为写回失败目标：释放 gate → 执行完成 → writeback 抛错 →
        # 循环错误走针对性收口（on_loop_failure：job FAILED + 轮次 FAILED）。
        job_rows = await db_rows(
            tmp_path,
            "SELECT id FROM processing_jobs WHERE job_type = 'CHAT_TURN' AND input_json = ?",
            (json.dumps({"turn_id": turn_a}, separators=(",", ":")),),
        )
        assert len(job_rows) == 1
        failing_job_ids.add(cast(str, job_rows[0][0]))
        gate.set()
        final_a = await wait_terminal(client, turn_a)
        # 轮次在执行内已完成（finalize 先于 writeback）；写回异常只收口 job。
        assert final_a["status"] == "COMPLETED"
        job_state: str | None = None
        for _ in range(100):
            rows_now = await db_rows(
                tmp_path,
                "SELECT status FROM processing_jobs WHERE id = ?",
                (job_rows[0][0],),
            )
            job_state = str(rows_now[0][0]) if rows_now else None
            if job_state in ("FAILED", "CANCELLED", "SUCCEEDED"):
                break
            await asyncio.sleep(0.1)
        assert job_state in ("FAILED", "CANCELLED")
        # 会话未被永久占用：新问照常受理并完成（另一槽仍健康）。
        events_retry = await drain_events_after_submit(client, session_a, "req-t06-0003")
        assert events_retry[-1][0] == "done"
        monkeypatch.setattr(turns_worker, "writeback", original_writeback)


# ---------------------------------------------------------------------------
# T11：完成 / 取消竞态只有一个有效终态；取消后无新副作用。


@pytest.mark.anyio
async def test_t11_cancel_and_completion_race_has_single_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = asyncio.Event()
    replies: list[StubReply] = [
        GatedReply(prefix=("竞态",), release=gate),
        list(STUB_REPLY),
    ]
    async with turns_app(tmp_path, monkeypatch, replies=replies) as (_app, client, _captured):
        session_id = await create_session(client)
        submitted = await submit(client, session_id, "竞态问题", request_id="req-t11-0001")
        turn_id = cast(str, submitted.json()["id"])
        await wait_running_progress(client, turn_id, min_seq=1)

        cancelled = await client.post(f"/api/chat-turns/{turn_id}/cancel")
        assert cancelled.status_code == 200
        body = cancelled.json()["turn"]
        assert body["cancel_requested"] is True
        assert body["status"] in ("RUNNING", "CANCELLED")  # 在途＝正在停止
        final = await wait_terminal(client, turn_id)
        assert final["status"] == "CANCELLED"
        gate.set()

        # 取消后无新副作用：无 assistant 行；重复取消幂等；迟到完成不复活。
        again = await client.post(f"/api/chat-turns/{turn_id}/cancel")
        assert again.status_code == 200
        assert again.json()["turn"]["status"] == "CANCELLED"
        rows = await db_rows(
            tmp_path,
            "SELECT role FROM chat_messages WHERE session_id = ?",
            (session_id,),
        )
        assert all(role != "ASSISTANT" for (role,) in rows)
        # 会话已释放：新问创建新轮次。
        events = await drain_events_after_submit(client, session_id, "req-t11-0002")
        assert events[-1][0] == "done"


@pytest.mark.anyio
async def test_t11_completion_wins_when_finalized_before_cancel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with turns_app(tmp_path, monkeypatch) as (_app, client, _captured):
        session_id = await create_session(client)
        submitted = await submit(client, session_id, "先完成", request_id="req-t11b-0001")
        turn_id = cast(str, submitted.json()["id"])
        final = await wait_terminal(client, turn_id)
        assert final["status"] == "COMPLETED"

        # 完成先提交：取消是幂等只读（终态不可复活，也无第二个终态）。
        cancelled = await client.post(f"/api/chat-turns/{turn_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["turn"]["status"] == "COMPLETED"
        assert (await snapshot(client, turn_id))["status"] == "COMPLETED"


@pytest.mark.anyio
async def test_t11_cancel_committed_before_stream_end_rejects_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """取消先落库、流随后结束：完成提交必须被拒绝（规格 §14；验收「取消先提交
    后无新副作用」「迟到输出不得转回完成」）。

    窗口真实性：流结束（consume 返回）后执行侧已停用取消观察器与等待器
    （worker.run 在 asyncio.wait 返回时取消 watcher/flusher，进入 _finalize 前
    取消 cancel_waiter），此后唯一兜底是完成提交事务内的条件检查；窗口宽度上界
    ＝观察器 0.4s 轮询间隔——取消在最后一次轮询之后、流结束之前落库即命中。
    本用例把观察器间隔钉到最坏观察延迟，使兜底路径成为唯一收口路径（断言与
    轮询相位无关；取消的原子性不得依赖观察器及时性，规格 §14「取消不依赖下
    一条 token」）。修复前同一时序落 COMPLETED＋最终消息＋done 事件。
    """
    import app.modules.agent.turns.worker as turns_worker

    monkeypatch.setattr(turns_worker, "CANCEL_POLL_INTERVAL_SECONDS", 30.0)
    gate = asyncio.Event()
    replies: list[StubReply] = [GatedReply(prefix=("半截",), release=gate)]
    async with turns_app(tmp_path, monkeypatch, replies=replies) as (_app, client, _captured):
        session_id = await create_session(client)
        submitted = await submit(client, session_id, "取消先提交", request_id="req-t11-0003")
        turn_id = cast(str, submitted.json()["id"])
        await wait_running_progress(client, turn_id, min_seq=1)

        # 取消先落库：执行在途（观察器尚未置位），状态保持 RUNNING＝「正在停止」。
        cancelled = await client.post(f"/api/chat-turns/{turn_id}/cancel")
        assert cancelled.status_code == 200
        body = cancelled.json()["turn"]
        assert body["cancel_requested"] is True
        assert body["status"] == "RUNNING"

        # 流照常结束：完整生成已持久，完成提交必须被取消裁决拒绝。
        gate.set()

        final = await wait_terminal(client, turn_id)
        assert final["status"] == "CANCELLED"
        assert final["cancel_requested"] is True
        assert final["final_message_id"] is None
        assert final["last_seq"] == 2  # 部分（此处完整）输出保留
        assert final["output_text"] == "半截收尾"
        rows = await db_rows(
            tmp_path,
            "SELECT role FROM chat_messages WHERE session_id = ?",
            (session_id,),
        )
        assert all(role != "ASSISTANT" for (role,) in rows)
        event_types = [
            event_type
            for (event_type,) in await db_rows(
                tmp_path,
                "SELECT type FROM chat_turn_events WHERE turn_id = ?",
                (turn_id,),
            )
        ]
        assert "done" not in event_types


# ---------------------------------------------------------------------------
# T19：有非终态轮次的会话删除返回冲突；停止后可删。


@pytest.mark.anyio
async def test_t19_delete_active_session_conflicts_until_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = asyncio.Event()
    replies: list[StubReply] = [GatedReply(prefix=("删除",), release=gate)]
    async with turns_app(tmp_path, monkeypatch, replies=replies) as (_app, client, _captured):
        session_id = await create_session(client)
        submitted = await submit(client, session_id, "删除冲突问题", request_id="req-t19-0001")
        turn_id = cast(str, submitted.json()["id"])
        await wait_running_progress(client, turn_id, min_seq=1)

        conflict = await client.delete(f"/api/chat-sessions/{session_id}")
        assert conflict.status_code == 409
        assert "CHAT_SESSION_HAS_ACTIVE_TURN" in conflict.json()["detail"]

        cancelled = await client.post(f"/api/chat-turns/{turn_id}/cancel")
        assert cancelled.status_code == 200
        await wait_terminal(client, turn_id)
        gate.set()
        deleted = await client.delete(f"/api/chat-sessions/{session_id}")
        assert deleted.status_code == 204


# ---------------------------------------------------------------------------
# T21：迁移持久化——全量迁移库的 CHECK / 部分唯一索引 / 公开契约。


@pytest.mark.anyio
async def test_t21_migration_constraints_in_real_database(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    async with aiosqlite.connect(db_path) as connection:
        version_row = await (await connection.execute("PRAGMA user_version")).fetchone()
        assert version_row is not None and version_row[0] == supported_user_version()
        session_id = "sess-t21-0001"
        await connection.execute(
            "INSERT INTO chat_sessions (id, mode, scope, created_at, updated_at)"
            " VALUES (?, 'ASK', 'FREE', '2026-10-06T00:00:00Z', '2026-10-06T00:00:00Z')",
            (session_id,),
        )
        await connection.execute(
            "INSERT INTO chat_messages (id, session_id, role, content, created_at)"
            " VALUES ('msg-1', ?, 'USER', '迁移校验', '2026-10-06T00:00:00Z')",
            (session_id,),
        )
        base = (
            session_id,
            "msg-1",
            "req-t21-{}",
            "fp",
            "QUEUED",
            "{}",
            "2026-10-06T00:00:00Z",
            "2026-10-06T00:00:00Z",
        )

        async def insert_turn(request_id: str, status: str) -> None:
            await connection.execute(
                "INSERT INTO chat_turns (id, session_id, user_message_id, request_id,"
                " request_fingerprint, status, execution_json, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("turn-" + request_id, *base[:2], request_id, base[3], status, *base[5:]),
            )

        # 同会话第二个非终态轮次被部分唯一索引拒绝；终态后允许新轮次。
        await insert_turn("active", "QUEUED")
        await insert_turn("terminal", "COMPLETED")
        with pytest.raises(aiosqlite.IntegrityError):
            await insert_turn("second-active", "RUNNING")

        # request_id 唯一；状态 CHECK 值域（含后续票 WAITING_*）成立。
        with pytest.raises(aiosqlite.IntegrityError):
            await insert_turn("active", "QUEUED")
        with pytest.raises(aiosqlite.IntegrityError):
            await insert_turn("bad-status", "WEIRD")

        # 事件 seq 唯一且单调受 CHECK 保护。
        await connection.execute(
            "INSERT INTO chat_turn_events (turn_id, seq, attempt, output_revision, type,"
            " payload_json, created_at)"
            " VALUES ('turn-active', 1, 1, 1, 'token', '{}', '2026-10-06T00:00:00Z')"
        )
        with pytest.raises(aiosqlite.IntegrityError):
            await connection.execute(
                "INSERT INTO chat_turn_events (turn_id, seq, attempt, output_revision, type,"
                " payload_json, created_at)"
                " VALUES ('turn-active', 1, 1, 1, 'token', '{}', '2026-10-06T00:00:01Z')"
            )
        with pytest.raises(aiosqlite.IntegrityError):
            await connection.execute(
                "INSERT INTO chat_turn_events (turn_id, seq, attempt, output_revision, type,"
                " payload_json, created_at)"
                " VALUES ('turn-active', 0, 1, 1, 'token', '{}', '2026-10-06T00:00:02Z')"
            )
        # processing_jobs 的 CHAT_TURN job_type 已放开。
        await connection.execute(
            "INSERT INTO processing_jobs (id, job_type, status, progress, attempts,"
            " max_attempts, input_json, created_at, updated_at)"
            " VALUES ('job-t21', 'CHAT_TURN', 'PENDING', 0, 0, 1, '{}',"
            " '2026-10-06T00:00:00Z', '2026-10-06T00:00:00Z')"
        )
        await connection.commit()


# ---------------------------------------------------------------------------
# 启动对账：崩溃残留 RUNNING → INTERRUPTED，保留内容并可取消释放。


@pytest.mark.anyio
async def test_startup_recovery_marks_running_turn_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = asyncio.Event()
    replies: list[StubReply] = [GatedReply(prefix=("崩溃前", "输出"), release=gate)]
    async with turns_app(tmp_path, monkeypatch, replies=replies) as (_app, client, _captured):
        session_id = await create_session(client)
        submitted = await submit(client, session_id, "崩溃问题", request_id="req-recover-01")
        turn_id = cast(str, submitted.json()["id"])
        await wait_running_progress(client, turn_id, min_seq=1)
        # 模拟进程强杀：不释放 gate 直接退出（teardown 软停机取消生成、不写终态，
        # 轮次残留 RUNNING＝崩溃现场；部分输出已持久）。

    # 重启（同一数据目录新实例）：启动对账把 RUNNING 翻 INTERRUPTED，保留内容。
    async with turns_app(tmp_path, monkeypatch) as (_app2, client2, _captured2):
        state = await snapshot(client2, turn_id)
        assert state["status"] == "INTERRUPTED"
        assert state["output_text"] == "崩溃前输出"
        # INTERRUPTED 可显式取消释放会话（无继续按钮：安全续跑属后续票）。
        cancelled = await client2.post(f"/api/chat-turns/{turn_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["turn"]["status"] == "CANCELLED"
        # 释放后可新问，不改写旧轮次。
        events = await drain_events_after_submit(client2, session_id, "req-recover-02")
        assert events[-1][0] == "done"
        rows = await db_rows(
            tmp_path,
            "SELECT status FROM chat_turns WHERE id = ?",
            (turn_id,),
        )
        assert rows[0][0] == "CANCELLED"
