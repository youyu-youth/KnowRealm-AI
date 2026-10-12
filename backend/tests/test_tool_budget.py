"""真实迁移库、框架工具与公开轮次/Worker 的预算故障窗口。"""

import asyncio
import json
from pathlib import Path
from typing import Any

import aiosqlite
import httpx
import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.db.migrations import supported_user_version
from app.modules.agent.budget.models import BudgetCall, BudgetOutput
from app.modules.agent.budget.policy import POLICY_VERSION
from app.modules.agent.budget.service import BudgetRejected, admit, restore
from app.modules.agent.runtime import bind_agent_runtime_context, reset_agent_runtime_context
from app.modules.agent.tools.get_current_time import get_current_time
from app.modules.agent.turns.effects import (
    ToolCallIdentity,
    bind_tool_call_identity,
    reset_tool_call_identity,
)
from app.modules.agent.turns.models import ChatTurn
from app.shared.errors import CodedHTTPException
from tests.test_agent_undo_retry import bare_db
from tests.test_chat_turns import (
    GatedReply,
    StubReply,
    ToolCallReply,
    create_session,
    db_rows,
    snapshot,
    submit,
    wait_running_progress,
    wait_terminal,
)
from tests.test_chat_turns_recovery import (
    _runtime_for,  # pyright: ignore[reportPrivateUsage]
    _seed_turn,  # pyright: ignore[reportPrivateUsage]
    recovery_app,
    wait_stable_status,
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


async def modern_turn(factory: Any) -> Any:
    seed = await _seed_turn(factory)
    async with factory() as session, session.begin():
        turn = await session.get(ChatTurn, seed.turn_id)
        assert turn is not None
        turn.execution_json = json.dumps({"budget_policy_version": POLICY_VERSION})
    return seed


@pytest.mark.anyio
async def test_atomic_admission_replay_and_claim_guard(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as factory:
        seed = await modern_turn(factory)

        async def consume(call: str, tool: str = "get_current_time", args: object = None) -> str:
            token = bind_tool_call_identity(ToolCallIdentity("namespace", call))
            try:
                try:
                    result = await admit(_runtime_for(factory, seed), tool, args)
                    assert result is not None
                    return result
                except BudgetRejected as exc:
                    return exc.code
            finally:
                reset_tool_call_identity(token)

        for i in range(5):
            await consume(str(i))
        same = await asyncio.gather(consume("last"), consume("last"))
        assert same[0] == same[1] and same[0] != "TOOL_CALL_LIMIT"
        assert await consume("new") == "TOOL_CALL_LIMIT"
        assert await consume("last", args={"timezone": "UTC"}) == "TOOL_CALL_IDENTITY_CONFLICT"
        assert await consume("last", tool="get_plan") == "TOOL_CALL_IDENTITY_CONFLICT"
        assert await restore(factory, seed.turn_id) == (6, 0)
        # 最后一个名额由不同身份争抢，不可超卖。
        async with factory() as session, session.begin():
            await session.execute(delete(BudgetCall).where(BudgetCall.id == same[0]))
        competing = await asyncio.gather(consume("a"), consume("b"))
        assert competing.count("TOOL_CALL_LIMIT") == 1
        async with factory() as session, session.begin():
            turn = await session.get(ChatTurn, seed.turn_id)
            assert turn is not None
            turn.claim_token = "new-worker"
        assert await consume("0") == "CHAT_TURN_CANCELLED"
        assert await restore(factory, seed.turn_id) == (6, 0)


@pytest.mark.anyio
async def test_output_new_production_and_recovery_are_separate(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as factory:
        seed = await modern_turn(factory)
        runtime = _runtime_for(factory, seed)
        rt = bind_agent_runtime_context(runtime)
        it = bind_tool_call_identity(ToolCallIdentity("ns", "time"))
        try:
            first = await get_current_time.ainvoke({})
            assert await restore(factory, seed.turn_id) == (1, len(first))
            # 输出已落库但 checkpoint 尚未提交，模拟上下文重建不会再计量。
            recovered = await restore(factory, seed.turn_id)
            assert recovered == await restore(factory, seed.turn_id)
            runtime.budget.chars_fed = 0
            second = await get_current_time.ainvoke({})
            assert await restore(factory, seed.turn_id) == (1, len(first) + len(second))
            async with factory() as session:
                assert await session.scalar(select(func.count()).select_from(BudgetOutput)) == 2
            # 旧 worker 已失效，不得把迟到输出交模型或记账。
            async with factory() as session, session.begin():
                turn = await session.get(ChatTurn, seed.turn_id)
                assert turn is not None
                turn.cancel_requested = True
            rejected = json.loads(await get_current_time.ainvoke({}))
            assert rejected["error"] == "CHAT_TURN_CANCELLED"
            assert await restore(factory, seed.turn_id) == (1, len(first) + len(second))
        finally:
            reset_tool_call_identity(it)
            reset_agent_runtime_context(rt)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "tool,args,counted",
    [
        ("get_current_time", {"timezone": "invalid/timezone"}, True),
        ("get_current_time", {"timezone": {"invalid": "structure"}}, True),
        ("get_goal", {"goal_id": "missing"}, True),
        ("generate_learning_plan", {"goal_id": "missing"}, True),
        ("wait_for_task", {"target_type": "JOB", "target_id": "missing"}, True),
        ("unknown_tool", {}, False),
        ("search_library", {"query": "unmounted"}, False),
    ],
)
async def test_real_framework_admits_before_parameter_and_domain_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tool: str, args: dict[str, Any], counted: bool
) -> None:
    replies: list[StubReply] = [ToolCallReply(tool, args), ["结束"]]
    async with recovery_app(tmp_path, monkeypatch, replies=replies) as (_, client, _):
        sid = await create_session(client)
        response = await submit(client, sid, content="检查工具预算", request_id="budget-errors")
        assert response.status_code == 202
        turn = response.json()
        await wait_terminal(client, turn["id"])
        rows = await db_rows(tmp_path, "SELECT tool_name FROM chat_turn_budget_calls")
        assert rows == ([(tool,)] if counted else [])
        assert await db_rows(tmp_path, "SELECT id FROM chat_turn_waits") == []


@pytest.mark.anyio
async def test_real_worker_six_seven_unknown_and_terminal_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replies: list[StubReply] = [
        ToolCallReply("get_current_time", {}, f"time-{i}") for i in range(7)
    ]
    replies += [["结束"]]
    async with recovery_app(tmp_path, monkeypatch, replies=replies) as (app, client, captured):
        sid = await create_session(client)
        response = await submit(client, sid, content="检查七次查询", request_id="budget-seven")
        assert response.status_code == 202
        turn = response.json()
        final = await wait_terminal(client, turn["id"])
        assert final["status"] == "COMPLETED"
        rows = await db_rows(tmp_path, "SELECT id FROM chat_turn_budget_calls")
        assert len(rows) == 6
        tool_messages = [m for msgs in captured for m in msgs if m.type == "tool"]
        assert any("上限" in m.content for m in tool_messages)
        from app.modules.agent.turns.service import ChatTurnService

        await ChatTurnService.compact_events(app.state.session_factory, turn["id"])
        assert await db_rows(tmp_path, "SELECT id FROM chat_turn_budget_calls") == []
        assert await db_rows(tmp_path, "SELECT id FROM chat_turn_budget_outputs") == []
        assert (await snapshot(client, turn["id"]))["status"] == "COMPLETED"


@pytest.mark.anyio
@pytest.mark.parametrize("new_output", [False, True])
async def test_real_checkpoint_restart_keeps_output_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, new_output: bool
) -> None:
    replies: list[StubReply] = [
        ToolCallReply("get_current_time", {}, "time-before"),
        GatedReply(prefix=("重启前",), release=asyncio.Event()),
    ]
    async with recovery_app(tmp_path, monkeypatch, replies=replies) as (app, client, _):
        sid = await create_session(client)
        response = await submit(client, sid, "字符恢复", request_id="budget-chars")
        turn_id = response.json()["id"]
        await wait_running_progress(client, turn_id, min_seq=3)
        before = await restore(app.state.session_factory, turn_id)
        assert before[0] == 1 and before[1] > 0
    continuation: list[StubReply] = (
        [ToolCallReply("get_current_time", {}, "time-after"), ["完成"]]
        if new_output
        else [["完成"]]
    )
    async with recovery_app(tmp_path, monkeypatch, replies=continuation) as (app, client, _):
        assert (await wait_terminal(client, turn_id))["status"] == "COMPLETED"
        after = await restore(app.state.session_factory, turn_id)
        if new_output:
            assert after[0] == 2 and after[1] > before[1]
        else:
            assert after == before


@pytest.mark.anyio
async def test_search_clipping_uses_restarted_character_total(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replies: list[StubReply] = [
        ToolCallReply("search_courses", {}, "courses-1"),
        ToolCallReply("search_courses", {}, "courses-2"),
        GatedReply(prefix=("重启前",), release=asyncio.Event()),
    ]
    async with recovery_app(tmp_path, monkeypatch, replies=replies) as (app, client, _):
        for i in range(50):
            response = await client.post(
                "/api/courses",
                json={
                    "name": f"{i:02d}" + "长课程名" * 20,
                    "learning_context": "INTEREST",
                    "depth": "BEGINNER",
                },
            )
            assert response.status_code == 201
        sid = await create_session(client, scope="ALL")
        response = await submit(client, sid, "查询资料", request_id="budget-clip")
        turn_id = response.json()["id"]
        await wait_running_progress(client, turn_id, min_seq=5)
        before = await restore(app.state.session_factory, turn_id)
        assert before[0] == 2 and before[1] > 12000
    async with recovery_app(
        tmp_path,
        monkeypatch,
        replies=[ToolCallReply("search_library", {"query": "资料"}, "library-new"), ["完成"]],
    ) as (app, client, captured):
        assert (await wait_terminal(client, turn_id))["status"] == "COMPLETED"
        messages = [m for batch in captured for m in batch if m.type == "tool"]
        output = next(json.loads(m.content) for m in messages if m.name == "search_library")
        assert output["truncated"] is True and output["evidence_hits"] == []
        assert "累计已达" in output["message"]
        # 原耗尽提示分支不计字符；不会顺带改变原计量范围。
        assert await restore(app.state.session_factory, turn_id) == (3, before[1])


@pytest.mark.anyio
@pytest.mark.parametrize("status", ["QUEUED", "RUNNING", "WAITING_USER", "WAITING_JOB"])
async def test_legacy_nonterminal_turn_requires_stop_and_new_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    from app.modules.agent.turns.service import ChatTurnService

    replies: list[StubReply] = [GatedReply(prefix=("已保存",), release=asyncio.Event())]
    async with recovery_app(tmp_path, monkeypatch, replies=replies) as (app, client, _):
        sid = await create_session(client)
        turn_id = (await submit(client, sid, "旧问题", request_id="budget-legacy")).json()["id"]
        await wait_running_progress(client, turn_id, min_seq=1)
    async with bare_db(tmp_path) as factory:
        async with factory() as session, session.begin():
            turn = await session.get(ChatTurn, turn_id)
            assert turn is not None
            execution = json.loads(turn.execution_json)
            execution.pop("budget_policy_version")
            turn.execution_json = json.dumps(execution)
            turn.status = status
    # 恢复迁移 0044 的真实 schema，再经生产迁移链升级；不补造旧消费事实。
    async with aiosqlite.connect(tmp_path / "knowrealm.db") as connection:
        await connection.executescript(
            "DROP TABLE chat_turn_budget_outputs; DROP TABLE chat_turn_budget_calls;"
            " DROP TABLE chat_model_requests; DROP TABLE chat_context_inputs;"
            " DROP TABLE chat_context_states;"
            " PRAGMA user_version=44;"
        )
    async with recovery_app(tmp_path, monkeypatch, replies=[["新回答"]]) as (app, client, captured):
        assert await db_rows(tmp_path, "PRAGMA user_version") == [(supported_user_version(),)]
        if status in ("WAITING_USER", "WAITING_JOB"):
            # 旧等待不自动执行模型；兼容检查须复用既有门禁。
            assert not captured
            old = await snapshot(client, turn_id)
            assert old["status"] == status
        else:
            old = await wait_stable_status(client, turn_id, ("WAITING_USER",))
            assert old["waiting_reason"]["kind"] == "GRAPH_INCOMPATIBLE"
            assert not captured
        assert await restore(app.state.session_factory, turn_id) == (0, 0)
        assert old["output_text"] == "已保存"
        with pytest.raises(CodedHTTPException):
            await ChatTurnService.compact_events(app.state.session_factory, turn_id)
        assert (await client.post(f"/api/chat-turns/{turn_id}/cancel")).status_code == 200
        assert (await snapshot(client, turn_id))["status"] == "CANCELLED"
        new = (await submit(client, sid, "新问题", request_id="budget-modern")).json()["id"]
        assert (await wait_terminal(client, new))["status"] == "COMPLETED"


@pytest.mark.anyio
async def test_admitted_last_call_resumes_before_handler_at_full_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.agent.budget import service
    from app.modules.agent.turns.effects import current_tool_call_identity

    entered = asyncio.Event()
    original = service.admit

    async def pause_after_admission(*args: Any, **kwargs: Any) -> str | None:
        result = await original(*args, **kwargs)
        identity = current_tool_call_identity()
        if identity is not None and identity.logical_call_id == "last":
            entered.set()
            await asyncio.Event().wait()
        return result

    monkeypatch.setattr(service, "admit", pause_after_admission)
    replies: list[StubReply] = [
        ToolCallReply("get_current_time", {"timezone": "bad/zone"}, f"bad-{i}") for i in range(5)
    ]
    replies += [ToolCallReply("get_current_time", {}, "last")]
    async with recovery_app(tmp_path, monkeypatch, replies=replies) as (app, client, _):
        sid = await create_session(client)
        turn_id = (await submit(client, sid, "准入中断", request_id="budget-admitted")).json()["id"]
        await asyncio.wait_for(entered.wait(), 15)
        assert await restore(app.state.session_factory, turn_id) == (6, 0)
    monkeypatch.setattr(service, "admit", original)
    async with recovery_app(
        tmp_path, monkeypatch, replies=[ToolCallReply("get_current_time", {}, "seventh"), ["完成"]]
    ) as (app, client, captured):
        assert (await wait_terminal(client, turn_id))["status"] == "COMPLETED"
        calls, chars = await restore(app.state.session_factory, turn_id)
        assert calls == 6 and chars > 0
        messages = [m for batch in captured for m in batch if m.type == "tool"]
        assert any(m.tool_call_id == "last" and json.loads(m.content)["current"] for m in messages)
        assert any(m.tool_call_id == "seventh" and "上限" in m.content for m in messages)


@pytest.mark.anyio
async def test_web_search_shares_budget_and_never_sends_seventh_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.search.integrations.tavily import TavilySearchClient
    from app.modules.settings.config import save_web_search_provider

    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": []})

    def client_for(key: str) -> TavilySearchClient:
        return TavilySearchClient(key, transport=httpx.MockTransport(respond))

    monkeypatch.setattr("app.modules.agent.turns.worker.TavilySearchClient", client_for)
    save_web_search_provider(tmp_path, provider="tavily", api_key="test-key", clear_api_key=False)
    replies: list[StubReply] = [
        ToolCallReply("get_current_time", {"timezone": "bad/zone"}, f"time-{i}") for i in range(5)
    ]
    replies += [
        ToolCallReply("web_search", {"query": "sixth"}, "web-six"),
        ToolCallReply("web_search", {"query": "seventh"}, "web-seven"),
        ["完成"],
    ]
    async with recovery_app(tmp_path, monkeypatch, replies=replies) as (app, client, captured):
        sid = await create_session(client)
        turn_id = (
            await submit(client, sid, "联网预算", request_id="budget-web", web_search=True)
        ).json()["id"]
        assert (await wait_terminal(client, turn_id))["status"] == "COMPLETED"
        assert len(requests) == 1
        assert await restore(app.state.session_factory, turn_id) == (6, 0)
        rejected = next(
            json.loads(m.content)
            for batch in captured
            for m in batch
            if m.type == "tool" and m.tool_call_id == "web-seven"
        )
        assert rejected["ok"] is False and rejected["retryable"] is False
        assert rejected["hits"] == [] and rejected["error_code"] == "TOOL_CALL_LIMIT"


@pytest.mark.anyio
async def test_regenerate_committed_receipt_replays_before_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.agent.budget import middleware
    from app.modules.learning_plan.generation import PlanGenerationOutcome, PlanGenerationService
    from tests.test_plan_editing import GOAL_ID, llm_window_draft, seed_full_plan

    generated = 0
    committed = asyncio.Event()
    original = middleware.execute

    async def generate(**kwargs: Any) -> PlanGenerationOutcome:
        nonlocal generated
        generated += 1
        assert generated == 1, "成功重放不得再调用模型"
        return PlanGenerationOutcome(
            kind="DRAFT", plan=llm_window_draft(), total_minutes=30, materials_used=1
        )

    async def pause_after_receipt(*args: Any, **kwargs: Any) -> Any:
        result = await original(*args, **kwargs)
        if args[0] == "regenerate_plan":
            committed.set()
            await asyncio.Event().wait()
        return result

    monkeypatch.setattr(PlanGenerationService, "generate", staticmethod(generate))
    monkeypatch.setattr(middleware, "execute", pause_after_receipt)
    async with recovery_app(
        tmp_path,
        monkeypatch,
        replies=[ToolCallReply("regenerate_plan", {"goal_id": GOAL_ID}, "regen-call")],
    ) as (app, client, _):
        await seed_full_plan(app.state.session_factory)
        sid = await create_session(client)
        turn_id = (await submit(client, sid, "重新生成", request_id="budget-regen")).json()["id"]
        await asyncio.wait_for(committed.wait(), 15)
        rows = await db_rows(tmp_path, "SELECT result_json FROM chat_turn_tool_effects")
        assert len(rows) == 1
        receipt = json.loads(rows[0][0])
        assert receipt["ok"] is True
    monkeypatch.setattr(middleware, "execute", original)
    async with recovery_app(tmp_path, monkeypatch, replies=[["完成"]]) as (app, client, captured):
        assert (await wait_terminal(client, turn_id))["status"] == "COMPLETED"
        assert generated == 1
        messages = [
            json.loads(m.content)
            for batch in captured
            for m in batch
            if m.type == "tool" and m.tool_call_id == "regen-call"
        ]
        assert messages and all(result == receipt for result in messages)
        assert await db_rows(tmp_path, "SELECT COUNT(*) FROM agent_proposals") == [(1,)]
        assert await restore(app.state.session_factory, turn_id) == (1, 0)


@pytest.mark.anyio
async def test_database_unique_output_constraint_and_active_compression_guard(
    tmp_path: Path,
) -> None:
    from app.modules.agent.turns.service import ChatTurnService

    async with bare_db(tmp_path) as factory:
        seed = await modern_turn(factory)
        rt = bind_agent_runtime_context(_runtime_for(factory, seed))
        it = bind_tool_call_identity(ToolCallIdentity("ns", "call"))
        try:
            await get_current_time.ainvoke({})
        finally:
            reset_tool_call_identity(it)
            reset_agent_runtime_context(rt)
        async with factory() as session:
            row = await session.scalar(select(BudgetCall))
            assert row is not None
        with pytest.raises(IntegrityError):
            async with factory() as session, session.begin():
                session.add(
                    BudgetCall(
                        id="duplicate",
                        turn_id=seed.turn_id,
                        namespace=row.namespace,
                        logical_call_id=row.logical_call_id,
                        tool_name=row.tool_name,
                        args_fingerprint=row.args_fingerprint,
                        policy_version=POLICY_VERSION,
                    )
                )
        before = await restore(factory, seed.turn_id)
        with pytest.raises(CodedHTTPException):
            await ChatTurnService.compact_events(factory, seed.turn_id)
        assert await restore(factory, seed.turn_id) == before
        # 会话物理删除沿已有外键生命周期清除两类事实。
        from app.modules.agent.models import ChatSession

        async with factory() as session, session.begin():
            await session.execute(delete(ChatSession).where(ChatSession.id == seed.session_id))
        assert await restore(factory, seed.turn_id) == (0, 0)


@pytest.mark.anyio
async def test_character_commit_before_tool_checkpoint_survives_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.agent.budget import middleware

    measured = asyncio.Event()
    original = middleware.execute

    async def pause_after_measure(*args: Any, **kwargs: Any) -> Any:
        result = await original(*args, **kwargs)
        measured.set()
        await asyncio.Event().wait()
        return result

    monkeypatch.setattr(middleware, "execute", pause_after_measure)
    async with recovery_app(
        tmp_path, monkeypatch, replies=[ToolCallReply("get_current_time", {}, "measured-call")]
    ) as (app, client, _):
        sid = await create_session(client)
        turn_id = (await submit(client, sid, "计量窗口", request_id="budget-measure")).json()["id"]
        await asyncio.wait_for(measured.wait(), 15)
        before = await restore(app.state.session_factory, turn_id)
        assert before[0] == 1 and before[1] > 0
    monkeypatch.setattr(middleware, "execute", original)
    async with recovery_app(tmp_path, monkeypatch, replies=[["完成"]]) as (app, client, _):
        assert (await wait_terminal(client, turn_id))["status"] == "COMPLETED"
        # 新执行产出的实际结果继续计量；已提交字符事实不会被 checkpoint 回退覆盖。
        after = await restore(app.state.session_factory, turn_id)
        assert after[0] == 1 and after[1] > before[1]
        assert await db_rows(tmp_path, "SELECT COUNT(*) FROM chat_turn_budget_outputs") == [(2,)]


@pytest.mark.anyio
@pytest.mark.parametrize("persistent", [False, True])
async def test_parallel_retrieval_clipping_and_character_commit_are_atomic(
    tmp_path: Path, persistent: bool
) -> None:
    from app.modules.agent.budget.service import execute, format_output, mark_output
    from app.modules.agent.tools.search_library import (
        _truncate_payload,  # pyright: ignore[reportPrivateUsage]
    )

    async with bare_db(tmp_path) as factory:
        seed = await modern_turn(factory)
        runtime = _runtime_for(factory, seed)
        if not persistent:
            runtime.turn_id = None
        rt = bind_agent_runtime_context(runtime)
        gate = asyncio.Event()
        entered = 0

        async def initial() -> str:
            payload = "x" * 8000
            mark_output(payload)
            return payload

        async def retrieved() -> str:
            nonlocal entered
            entered += 1
            if entered == 2:
                gate.set()
            await gate.wait()
            body: dict[str, object] = {
                "evidence_hits": [{"quote": "x" * 3000}],
                "asset_matches": [],
                "concept_hints": [],
            }
            return await format_output(lambda budget: _truncate_payload(body, budget)[0])

        async def call(name: str, handler: Any) -> str:
            token = bind_tool_call_identity(ToolCallIdentity("parallel", name))
            try:
                tool_name = "search_courses" if name == "initial" else "search_library"
                return await execute(tool_name, {"query": name}, handler)
            finally:
                reset_tool_call_identity(token)

        try:
            await call("initial", initial)
            outputs = await asyncio.gather(call("a", retrieved), call("b", retrieved))
            calls, chars = (
                await restore(factory, seed.turn_id)
                if persistent
                else (runtime.budget.calls_used, runtime.budget.chars_fed)
            )
            assert calls == 3 and chars == 8000 + sum(map(len, outputs)) <= 12000
            assert sum(bool(json.loads(output).get("truncated")) for output in outputs) == 1
        finally:
            reset_agent_runtime_context(rt)


@pytest.mark.anyio
async def test_cancel_after_handler_before_measure_uses_cancelled_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.agent.budget import middleware

    produced, release = asyncio.Event(), asyncio.Event()
    original = middleware.execute

    async def held_execute(tool_name: str, args: object, handler: Any) -> Any:
        async def held_handler() -> Any:
            result = await handler()
            produced.set()
            await release.wait()
            return result

        return await original(tool_name, args, held_handler)

    monkeypatch.setattr(middleware, "execute", held_execute)
    monkeypatch.setattr("app.modules.agent.turns.worker.CANCEL_POLL_INTERVAL_SECONDS", 60)
    async with recovery_app(
        tmp_path,
        monkeypatch,
        replies=[ToolCallReply("get_current_time", {}, "cancelled-output"), ["完成"]],
    ) as (app, client, _):
        sid = await create_session(client)
        turn_id = (await submit(client, sid, "计量前停止", request_id="budget-stop")).json()["id"]
        await asyncio.wait_for(produced.wait(), 15)
        assert (await client.post(f"/api/chat-turns/{turn_id}/cancel")).status_code == 200
        release.set()
        assert (await wait_terminal(client, turn_id))["status"] == "CANCELLED"
        assert await restore(app.state.session_factory, turn_id) == (1, 0)
