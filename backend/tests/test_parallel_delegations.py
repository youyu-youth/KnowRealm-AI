"""双调用协作：公开 API、真实迁移库/双槽/Graph，仅替换外部模型。"""

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any, cast

import httpx2
import openai
import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGenerationChunk
from sqlalchemy import Row, text
from test_chat_turns import (
    GatedReply,
    StubChatModel,
    ToolCallReply,
    create_session,
    snapshot,
    submit,
    turns_app,
    wait_terminal,
)
from test_chat_turns_background import wait_status


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def route_model(monkeypatch: pytest.MonkeyPatch, routes: dict[str, list[Any]]) -> None:
    from app.modules.llm import service

    base = cast(type[StubChatModel], service.ChatOpenAI)

    class RoutedModel(base):
        async def _astream(
            self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
        ) -> AsyncIterator[ChatGenerationChunk]:
            type(self).captured.append(list(messages))
            prompt = str(next(m.content for m in reversed(messages) if isinstance(m, HumanMessage)))
            key = next(key for key in routes if key in prompt)
            reply = routes[key].pop(0)
            if isinstance(reply, asyncio.Event):
                await reply.wait()
                reply = routes[key].pop(0)
            if reply is None:
                raise openai.APITimeoutError(
                    request=httpx2.Request("POST", "https://stub.example.com/v1")
                )
            if isinstance(reply, tuple):
                yield ChatGenerationChunk(
                    message=AIMessageChunk(
                        content="",
                        tool_call_chunks=[
                            {
                                "name": call.tool,
                                "args": json.dumps(call.args),
                                "id": call.call_id,
                                "index": index,
                            }
                            for index, call in enumerate(cast(tuple[ToolCallReply, ...], reply))
                        ],
                    )
                )
                return
            if isinstance(reply, GatedReply):
                for part in reply.prefix:
                    yield ChatGenerationChunk(message=AIMessageChunk(content=part))
                await reply.release.wait()
                reply = reply.rest
            for part in reply:
                yield ChatGenerationChunk(message=AIMessageChunk(content=part))

    monkeypatch.setattr(service, "ChatOpenAI", RoutedModel)


def delegates(root: str) -> tuple[ToolCallReply, ...]:
    return tuple(
        ToolCallReply(
            "delegate_knowledge", {"task": f"child:{root}:{branch}"}, f"delegate-{branch}"
        )
        for branch in ("A", "B")
    )


@pytest.mark.anyio
async def test_two_waiting_roots_share_two_slots_and_resume_by_interrupt_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = asyncio.Event()
    routes = {
        **{f"root:{root}": [delegates(root), [f"汇总 {root}"]] for root in ("R1", "R2")},
        **{
            f"child:{root}:{branch}": [GatedReply((f"证据 {root}{branch}",), release)]
            for root in ("R1", "R2")
            for branch in ("A", "B")
        },
    }
    async with turns_app(tmp_path, monkeypatch) as (app, client, captured):
        route_model(monkeypatch, routes)
        sessions = [await create_session(client, scope="ALL") for _ in range(2)]
        roots = [
            (
                await submit(client, sid, f"root:R{index + 1}", request_id=f"parallel-{index}")
            ).json()["id"]
            for index, sid in enumerate(sessions)
        ]
        try:
            for root in roots:
                waiting = await wait_status(client, root, "WAITING_JOB")
                assert len(waiting["background_tasks"]) == 2
            peak = 0
            running_children = 0
            for _ in range(100):
                async with app.state.session_factory() as session:
                    active = await session.scalar(
                        text(
                            "SELECT count(*) FROM processing_jobs "
                            "WHERE job_type='CHAT_TURN' AND status='RUNNING'"
                        )
                    )
                    running_children = await session.scalar(
                        text("SELECT count(*) FROM agent_delegations WHERE status='RUNNING'")
                    )
                peak = max(peak, active)
                assert active <= 2
                if running_children == 2:
                    break
                await asyncio.sleep(0.05)
            assert peak == 2 and running_children == 2
            assert (
                await submit(client, sessions[0], "busy", request_id="parallel-busy")
            ).status_code == 409
            for root in roots:
                state = await snapshot(client, root)
                assert state["status"] == "WAITING_JOB"
                assert not state["output_text"]
        finally:
            release.set()
        for root in roots:
            result = await wait_terminal(client, root)
            assert result["status"] == "COMPLETED", result
            assert len(result["background_tasks"]) == 2
        async with app.state.session_factory() as session:
            waits = (
                await session.execute(
                    text("SELECT turn_id, interrupt_id, result_json FROM chat_turn_waits")
                )
            ).all()
            assert len(waits) == 4 and len({row.interrupt_id for row in waits}) == 4
            assert all(json.loads(row.result_json)["status"] == "COMPLETED" for row in waits)
            assert await session.scalar(text("SELECT count(*) FROM agent_delegations")) == 4
            assert await session.scalar(text("SELECT count(*) FROM chat_turn_budget_calls")) == 4
        summaries = [
            messages
            for messages in captured
            if sum(isinstance(m, ToolMessage) and m.name == "delegate_knowledge" for m in messages)
            == 2
        ]
        assert len(summaries) == 2 and len(captured) == 8
        for messages in summaries:
            for message in messages:
                if isinstance(message, ToolMessage) and message.name == "delegate_knowledge":
                    assert message.tool_call_id[-1] in json.loads(str(message.content))["summary"]


@pytest.mark.anyio
@pytest.mark.parametrize("failed", [1, 2])
async def test_reliable_failures_return_both_reports_without_rerunning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failed: int
) -> None:
    routes = {
        "root:fail": [delegates("fail"), ["证据不足，缺失分支未完成"]],
        "child:fail:A": [["A 的证据"] if failed == 1 else [""]],
        "child:fail:B": [[""]],
    }
    async with turns_app(tmp_path, monkeypatch) as (_app, client, captured):
        route_model(monkeypatch, routes)
        sid = await create_session(client, scope="ALL")
        tid = (await submit(client, sid, "root:fail", request_id="parallel-fail")).json()["id"]
        result = await wait_terminal(client, tid)
        assert result["status"] == "COMPLETED", result
        reports = [json.loads(m.text) for m in captured[-1] if isinstance(m, ToolMessage)]
        assert sum(report["status"] == "FAILED" for report in reports) == failed
        assert all(report["gaps"] for report in reports if report["status"] == "FAILED")
        assert len(captured) == 4


@pytest.mark.anyio
@pytest.mark.parametrize("choice", ["RETRY_DELEGATIONS", "ACCEPT_PARTIAL"])
async def test_uncertain_sibling_waits_for_safe_branch_then_retries_only_selected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, choice: str
) -> None:
    safe, retry = asyncio.Event(), asyncio.Event()
    routes = {
        "root:choice": [delegates("choice"), ["汇总已有证据并说明缺口"]],
        "child:choice:A": [GatedReply(("成功证据 A",), safe)],
        "child:choice:B": [None, GatedReply(("重试证据 B",), retry)],
    }
    async with turns_app(tmp_path, monkeypatch) as (app, client, captured):
        route_model(monkeypatch, routes)
        sid = await create_session(client, scope="ALL")
        tid = (await submit(client, sid, "root:choice", request_id="parallel-choice")).json()["id"]
        try:
            state = await snapshot(client, tid)
            for _ in range(100):
                state = await snapshot(client, tid)
                if len(captured) == 3 and any(
                    task["status"] == "INTERRUPTED" for task in state["background_tasks"]
                ):
                    break
                await asyncio.sleep(0.05)
            assert state["status"] == "WAITING_JOB", state
            assert len(captured) == 3
            safe.set()
            waiting = await wait_status(client, tid, "WAITING_USER")
            reason = waiting["waiting_reason"]
            assert len(reason["delegations"]) == 1
            successful = next(
                task for task in waiting["background_tasks"] if task["status"] == "COMPLETED"
            )
            failed_id = reason["delegations"][0]["execution_id"]
            async with app.state.session_factory() as session:
                success = (
                    await session.execute(
                        text("SELECT result_json, input_json FROM agent_delegations WHERE id=:id"),
                        {"id": successful["execution_id"]},
                    )
                ).one()
                waits_before = (
                    (
                        await session.execute(
                            text(
                                "SELECT interrupt_id FROM chat_turn_waits "
                                "WHERE turn_id=:id ORDER BY id"
                            ),
                            {"id": tid},
                        )
                    )
                    .scalars()
                    .all()
                )
            decision = {
                "decision_kind": choice,
                "decision_id": "parallel-decision",
                "snapshot_id": reason["snapshot_id"],
                "delegations": reason["delegations"],
            }
            responses = await asyncio.gather(
                *(
                    client.post(
                        f"/api/chat-turns/{tid}/resume",
                        json={**decision, "decision_id": f"parallel-decision-{i}"},
                    )
                    for i in range(2)
                )
            )
            assert sorted(response.status_code for response in responses) == [200, 409]
            if choice == "RETRY_DELEGATIONS":
                for _ in range(100):
                    if len(captured) == 4:
                        break
                    await asyncio.sleep(0.05)
                assert len(captured) == 4
                assert (await snapshot(client, tid))["status"] == "WAITING_JOB"
                async with app.state.session_factory() as session:
                    assert (
                        await session.execute(
                            text(
                                "SELECT result_json, input_json FROM agent_delegations WHERE id=:id"
                            ),
                            {"id": successful["execution_id"]},
                        )
                    ).one() == success
                    assert (
                        await session.scalar(
                            text(
                                "SELECT result_json FROM chat_turn_waits WHERE target_id="
                                "(SELECT job_id FROM agent_delegations WHERE id=:id)"
                            ),
                            {"id": failed_id},
                        )
                        is None
                    )
                retry.set()
            result = await wait_terminal(client, tid)
            assert result["status"] == "COMPLETED", result
            assert len(captured) == (5 if choice == "RETRY_DELEGATIONS" else 4)
            async with app.state.session_factory() as session:
                assert (
                    await session.scalar(
                        text("SELECT count(*) FROM chat_model_requests WHERE execution_id=:id"),
                        {"id": successful["execution_id"]},
                    )
                    == 1
                )
                assert (
                    await session.scalar(
                        text("SELECT count(*) FROM chat_turn_budget_calls WHERE turn_id=:id"),
                        {"id": tid},
                    )
                    == 2
                )
                assert (
                    await session.execute(
                        text(
                            "SELECT interrupt_id FROM chat_turn_waits WHERE turn_id=:id ORDER BY id"
                        ),
                        {"id": tid},
                    )
                ).scalars().all() == waits_before
            reports = [json.loads(m.text) for m in captured[-1] if isinstance(m, ToolMessage)]
            assert {report["status"] for report in reports} == (
                {"COMPLETED"} if choice == "RETRY_DELEGATIONS" else {"COMPLETED", "CANCELLED"}
            )
        finally:
            safe.set()
            retry.set()


@pytest.mark.anyio
async def test_parallel_children_compete_for_last_shared_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = asyncio.Event()

    def search(call_id: str) -> ToolCallReply:
        return ToolCallReply("search_library", {"query": "事务隔离"}, call_id)

    routes = {
        "root:budget": [delegates("budget"), ["汇总"]],
        "child:budget:A": [(search("A1"), search("A2")), release, (search("last-A"),), ["报告 A"]],
        "child:budget:B": [(search("B1"),), release, (search("last-B"),), ["报告 B"]],
    }
    async with turns_app(tmp_path, monkeypatch) as (app, client, captured):
        route_model(monkeypatch, routes)
        sid = await create_session(client, scope="ALL")
        tid = (await submit(client, sid, "root:budget", request_id="parallel-budget")).json()["id"]
        try:
            for _ in range(100):
                if len(captured) == 5:
                    break
                await asyncio.sleep(0.05)
            assert len(captured) == 5
            async with app.state.session_factory() as session:
                assert (
                    await session.scalar(
                        text("SELECT count(*) FROM chat_turn_budget_calls WHERE turn_id=:id"),
                        {"id": tid},
                    )
                    == 5
                )
            release.set()
            assert (await wait_terminal(client, tid))["status"] == "COMPLETED"
            final_tools = {
                m.tool_call_id: m.text
                for messages in captured
                for m in messages
                if isinstance(m, ToolMessage) and m.tool_call_id in ("last-A", "last-B")
            }
            assert len(final_tools) == 2
            assert sum("本轮检索次数已达上限" in value for value in final_tools.values()) == 1
            async with app.state.session_factory() as session:
                assert (
                    await session.scalar(
                        text("SELECT count(*) FROM chat_turn_budget_calls WHERE turn_id=:id"),
                        {"id": tid},
                    )
                    == 6
                )
                assert (
                    await session.scalar(
                        text(
                            "SELECT count(*) FROM chat_turn_budget_calls "
                            "WHERE turn_id=:id AND execution_id IS NOT NULL"
                        ),
                        {"id": tid},
                    )
                    == 4
                )
        finally:
            release.set()


@pytest.mark.anyio
async def test_reverse_completion_rejects_third_child_and_nested_delegation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = asyncio.Event()
    routes = {
        "root:limits": [
            delegates("limits"),
            (ToolCallReply("delegate_knowledge", {"task": "third child"}, "delegate-C"),),
            ["已有两个报告，第三任务未受理"],
        ],
        "child:limits:A": [GatedReply(("证据 A",), release)],
        "child:limits:B": [
            (ToolCallReply("delegate_knowledge", {"task": "nested child"}, "nested"),),
            ["证据 B"],
        ],
    }
    async with turns_app(tmp_path, monkeypatch) as (app, client, captured):
        route_model(monkeypatch, routes)
        sid = await create_session(client, scope="ALL")
        tid = (await submit(client, sid, "root:limits", request_id="parallel-limits")).json()["id"]
        try:
            state = await snapshot(client, tid)
            for _ in range(100):
                state = await snapshot(client, tid)
                if any(task["status"] == "COMPLETED" for task in state["background_tasks"]):
                    break
                await asyncio.sleep(0.05)
            assert state["status"] == "WAITING_JOB"
            assert {task["status"] for task in state["background_tasks"]} == {
                "COMPLETED",
                "RUNNING",
            }
            assert len(captured) == 4
            nested = next(m for m in captured[-1] if isinstance(m, ToolMessage))
            assert nested.status == "error" and nested.name == "delegate_knowledge"
            assert not state["output_text"]
            from app.modules.agent.turns.service import ChatTurnService

            assert (await snapshot(client, tid))["process"] == state["process"]
            release.set()
            result = await wait_terminal(client, tid)
            assert result["status"] == "COMPLETED", result
            third = next(
                m
                for m in captured[-1]
                if isinstance(m, ToolMessage) and m.tool_call_id == "delegate-C"
            )
            assert json.loads(third.text)["ok"] is False
            assert len(result["background_tasks"]) == 2
            async with app.state.session_factory() as session:
                assert await session.scalar(text("SELECT count(*) FROM agent_delegations")) == 2
                events = (
                    (
                        await session.execute(
                            text("SELECT seq FROM chat_turn_events WHERE turn_id=:id ORDER BY seq"),
                            {"id": tid},
                        )
                    )
                    .scalars()
                    .all()
                )
                assert len(events) == len(set(events))
                assert events[-1] == result["last_seq"]
            await ChatTurnService.compact_events(
                session_factory=app.state.session_factory, turn_id=tid
            )
            assert (await snapshot(client, tid))["process"] == result["process"]
        finally:
            release.set()


@pytest.mark.anyio
@pytest.mark.parametrize("action", ["cancel", "restart"])
async def test_successful_sibling_survives_cancel_or_restart_of_inflight_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    release = asyncio.Event()
    routes = {
        "root:recovery": [delegates("recovery"), ["保留证据 A，B 未完成"]],
        "child:recovery:A": [["证据 A"]],
        "child:recovery:B": [GatedReply(("不应进入父正文",), release)],
    }
    async with turns_app(tmp_path, monkeypatch) as (app, client, captured):
        route_model(monkeypatch, routes)
        sid = await create_session(client, scope="ALL")
        tid = (await submit(client, sid, "root:recovery", request_id="parallel-recovery")).json()[
            "id"
        ]
        state = await snapshot(client, tid)
        for _ in range(100):
            state = await snapshot(client, tid)
            if (
                any(task["status"] == "COMPLETED" for task in state["background_tasks"])
                and len(captured) == 3
            ):
                break
            await asyncio.sleep(0.05)
        assert state["status"] == "WAITING_JOB" and len(captured) == 3
        assert not state["output_text"]
        success_id = next(
            task["execution_id"]
            for task in state["background_tasks"]
            if task["status"] == "COMPLETED"
        )
        if action == "cancel":
            assert (await client.post(f"/api/chat-turns/{tid}/cancel")).status_code == 200
            release.set()
            final = await wait_terminal(client, tid)
            assert final["status"] == "CANCELLED"
            assert {task["status"] for task in final["background_tasks"]} == {
                "COMPLETED",
                "CANCELLED",
            }
            assert len(captured) == 3
    if action == "restart":
        async with turns_app(tmp_path, monkeypatch, replies=[]) as (app, client, captured):
            waiting = await wait_status(client, tid, "WAITING_USER")
            assert waiting["waiting_reason"]["kind"] == "DELEGATION_UNCERTAIN"
            assert not captured
            async with app.state.session_factory() as session:
                assert (
                    await session.scalar(
                        text("SELECT count(*) FROM chat_model_requests WHERE execution_id=:id"),
                        {"id": success_id},
                    )
                    == 1
                )
            await client.post(f"/api/chat-turns/{tid}/cancel")


@pytest.mark.anyio
async def test_two_unknown_branches_allow_one_retry_then_new_choice_for_remaining(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    routes = {
        "root:unknown": [delegates("unknown"), ["证据 B，A 缺失"]],
        "child:unknown:A": [None],
        "child:unknown:B": [None, ["证据 B"]],
    }
    async with turns_app(tmp_path, monkeypatch) as (app, client, captured):
        route_model(monkeypatch, routes)
        sid = await create_session(client, scope="ALL")
        tid = (await submit(client, sid, "root:unknown", request_id="parallel-unknown")).json()[
            "id"
        ]
        waiting = await wait_status(client, tid, "WAITING_USER")
        reason = waiting["waiting_reason"]
        assert len(reason["delegations"]) == 2
        async with app.state.session_factory() as session:
            branch_b = await session.scalar(
                text("SELECT id FROM agent_delegations WHERE logical_call_id='delegate-B'")
            )
        selected = next(item for item in reason["delegations"] if item["execution_id"] == branch_b)
        decision = {
            "decision_kind": "RETRY_DELEGATIONS",
            "decision_id": "retry-only-B",
            "snapshot_id": reason["snapshot_id"],
            "delegations": [selected],
        }
        assert (
            await client.post(f"/api/chat-turns/{tid}/resume", json=decision)
        ).status_code == 200
        for _ in range(100):
            waiting = await snapshot(client, tid)
            if (
                waiting["status"] == "WAITING_USER"
                and waiting["waiting_reason"]["snapshot_id"] != reason["snapshot_id"]
            ):
                break
            await asyncio.sleep(0.05)
        assert waiting["status"] == "WAITING_USER", waiting
        new_reason = waiting["waiting_reason"]
        assert new_reason["snapshot_id"] != reason["snapshot_id"]
        assert len(new_reason["delegations"]) == 1 and len(captured) == 4
        assert (
            await client.post(
                f"/api/chat-turns/{tid}/resume", json={**decision, "decision_id": "stale-choice"}
            )
        ).status_code == 409
        accept = {
            "decision_kind": "ACCEPT_PARTIAL",
            "decision_id": "accept-A-missing",
            "snapshot_id": new_reason["snapshot_id"],
            "delegations": new_reason["delegations"],
        }
        assert (await client.post(f"/api/chat-turns/{tid}/resume", json=accept)).status_code == 200
        assert (await wait_terminal(client, tid))["status"] == "COMPLETED"
        assert len(captured) == 5


@pytest.mark.anyio
async def test_parent_input_validates_report_contract_and_branch_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.agent.context_budget.retrieval import validate_read_results

    routes = {
        "root:contract": [delegates("contract"), ["汇总"]],
        "child:contract:A": [["证据 A"]],
        "child:contract:B": [["证据 B"]],
    }
    async with turns_app(tmp_path, monkeypatch) as (app, client, captured):
        route_model(monkeypatch, routes)
        sid = await create_session(client, scope="ALL")
        tid = (await submit(client, sid, "root:contract", request_id="parallel-contract")).json()[
            "id"
        ]
        assert (await wait_terminal(client, tid))["status"] == "COMPLETED"
        reports = [m for m in captured[-1] if isinstance(m, ToolMessage)]
        valid = reports[0]
        body = json.loads(valid.text)
        invalid = [
            valid.model_copy(update={"content": "不是合法报告 JSON"}),
            valid.model_copy(update={"content": json.dumps({**body, "contract_version": 2})}),
            valid.model_copy(update={"tool_call_id": reports[1].tool_call_id}),
            valid.model_copy(update={"content": json.dumps({**body, "summary": "无来源注入结论"})}),
            valid.model_copy(update={"content": json.dumps({**body, "ok": False})}),
        ]
        projected = await validate_read_results(app.state.session_factory, sid, [valid, *invalid])
        assert projected[0] == valid
        assert all(json.loads(m.text).get("ok") is False for m in projected[1:])


@pytest.mark.anyio
async def test_long_reports_remain_readable_after_budget_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_conversation_compaction import configure
    from test_shared_refs import COURSE_ML, REC_ML_PAPER, seed_full_corpus

    from app.modules.agent.context_budget.retrieval import validate_read_results

    summary = "长报告正文。" * 5000
    quote = "梯度下降通过反向传播迭代更新参数。"
    routes = {
        "root:long": [delegates("long"), ["汇总"]],
        "child:long:A": [[f"{summary}\n证据[1]。\n[1] {quote}（来源：论文精读）"]],
        "child:long:B": [[summary]],
    }
    async with turns_app(tmp_path, monkeypatch) as (app, client, captured):
        factory = app.state.session_factory
        await seed_full_corpus(factory)
        route_model(monkeypatch, routes)
        sid = await create_session(client, scope="COURSE", course_id=COURSE_ML)
        await configure(client, 60000)
        tid = (await submit(client, sid, "root:long", request_id="parallel-long")).json()["id"]
        result = await wait_terminal(client, tid)
        assert result["status"] == "COMPLETED", result
        reports = {m.tool_call_id: m for m in captured[-1] if isinstance(m, ToolMessage)}
        pointers = {key: json.loads(m.text) for key, m in reports.items()}
        assert len(pointers) == 2
        assert all(body.get("ok") is True and body.get("truncated") for body in pointers.values())
        base = f"/api/chat-sessions/{sid}/context/sources/read"
        for call_id, pointer in pointers.items():
            request = {
                "source_id": pointer["source_id"],
                "version": pointer["version"],
                "max_chars": 2400,
            }
            page = await client.post(base, json=request)
            assert page.status_code == 200, page.text
            body = page.json()
            assert body["source"]["locator"]["tool_call_id"] == call_id
            assert summary[:2000] in body["content"]
            second = await client.post(base, json={**request, "cursor": body["next_cursor"]})
            assert second.status_code == 200, second.text
            assert second.json()["offset"] == 2400
            assert body["remaining"] + 2400 == pointer["total_chars"]
        valid = reports["delegate-A"]
        pointer = pointers["delegate-A"]
        invalid = [
            valid.model_copy(update={"content": reports["delegate-B"].text}),
            *[
                valid.model_copy(update={"content": json.dumps({**pointer, **change})})
                for change in (
                    {"preview": "无来源注入结论"},
                    {"version": "stale-version"},
                    {"summary": "伪造的完整报告"},
                )
            ],
        ]
        checked = await validate_read_results(factory, sid, [valid, *invalid])
        assert checked[0] == valid
        assert all(json.loads(m.text).get("ok") is False for m in checked[1:])
        other = await create_session(client, scope="COURSE", course_id=COURSE_ML)
        checked = await validate_read_results(factory, other, [valid])
        assert json.loads(checked[0].text)["ok"] is False
        assert (await client.delete(f"/api/records/{REC_ML_PAPER}")).status_code == 204
        checked = await validate_read_results(factory, sid, list(reports.values()))
        by_call = {m.tool_call_id: m for m in checked if isinstance(m, ToolMessage)}
        assert json.loads(by_call["delegate-A"].text)["ok"] is False
        assert by_call["delegate-B"] == reports["delegate-B"]
        unavailable = await client.post(base, json={"source_id": pointer["source_id"]})
        assert unavailable.status_code == 404


@pytest.mark.anyio
async def test_deleted_source_is_removed_before_parallel_reports_enter_parent_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_shared_refs import COURSE_ML, REC_ML_PAPER, seed_full_corpus

    release = asyncio.Event()
    quote = "梯度下降通过反向传播迭代更新参数。"
    routes = {
        "root:sources": [delegates("sources"), ["A 来源失效，保留 B"]],
        "child:sources:A": [[f"证据[1]。\n[1] {quote}（来源：论文精读）"]],
        "child:sources:B": [GatedReply(("B 的报告",), release)],
    }
    async with turns_app(tmp_path, monkeypatch) as (app, client, captured):
        await seed_full_corpus(app.state.session_factory)
        route_model(monkeypatch, routes)
        sid = await create_session(client, scope="COURSE", course_id=COURSE_ML)
        tid = (await submit(client, sid, "root:sources", request_id="parallel-sources")).json()[
            "id"
        ]
        try:
            state = await snapshot(client, tid)
            for _ in range(100):
                state = await snapshot(client, tid)
                if any(task["status"] == "COMPLETED" for task in state["background_tasks"]):
                    break
                await asyncio.sleep(0.05)
            assert state["status"] == "WAITING_JOB"
            async with app.state.session_factory() as session:
                result_json = await session.scalar(
                    text("SELECT result_json FROM agent_delegations WHERE status='COMPLETED'")
                )
                assert json.loads(result_json)["citations"][0]["record_id"] == REC_ML_PAPER
            assert (await client.delete(f"/api/records/{REC_ML_PAPER}")).status_code == 204
            release.set()
            assert (await wait_terminal(client, tid))["status"] == "COMPLETED"
            tools = {
                m.tool_call_id: json.loads(m.text)
                for m in captured[-1]
                if isinstance(m, ToolMessage)
            }
            assert tools["delegate-A"]["ok"] is False
            assert "citations" not in tools["delegate-A"]
            assert tools["delegate-B"]["status"] == "COMPLETED"
        finally:
            release.set()


@pytest.mark.anyio
async def test_stop_cancels_both_running_children_and_rejects_late_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = asyncio.Event()
    routes = {
        "root:stop": [delegates("stop")],
        **{
            f"child:stop:{branch}": [GatedReply((f"子正文 {branch}",), release)]
            for branch in ("A", "B")
        },
    }
    async with turns_app(tmp_path, monkeypatch) as (app, client, captured):
        route_model(monkeypatch, routes)
        sid = await create_session(client, scope="ALL")
        tid = (await submit(client, sid, "root:stop", request_id="parallel-stop")).json()["id"]
        try:
            state = await snapshot(client, tid)
            for _ in range(100):
                state = await snapshot(client, tid)
                if len(captured) == 3 and all(
                    task["status"] == "RUNNING" for task in state["background_tasks"]
                ):
                    break
                await asyncio.sleep(0.05)
            assert len(state["background_tasks"]) == 2 and len(captured) == 3
            assert state["status"] == "WAITING_JOB" and not state["output_text"]
            assert (await client.post(f"/api/chat-turns/{tid}/cancel")).status_code == 200
            release.set()
            final = await wait_terminal(client, tid)
            assert final["status"] == "CANCELLED"
            assert {task["status"] for task in final["background_tasks"]} == {"CANCELLED"}
            async with app.state.session_factory() as session:
                results = (
                    (
                        await session.execute(
                            text("SELECT result_json FROM agent_delegations WHERE turn_id=:id"),
                            {"id": tid},
                        )
                    )
                    .scalars()
                    .all()
                )
                assert all(not json.loads(result)["summary"] for result in results)
            assert len(captured) == 3
        finally:
            release.set()


@pytest.mark.anyio
@pytest.mark.parametrize("window", ["registered", "result_committed"])
async def test_restart_before_parent_wake_reuses_both_branches_and_preserves_parent_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, window: str
) -> None:
    blocked = asyncio.Event()
    routes = {
        "root:window": [delegates("window"), ["原两份报告汇总"]],
        "child:window:A": [["证据 A"]],
        "child:window:B": [["证据 B"]],
    }
    async with turns_app(tmp_path, monkeypatch) as (app, client, captured):
        route_model(monkeypatch, routes)
        saver = app.state.chat_checkpointer
        put_writes, delete = saver.aput_writes, saver.adelete_thread
        deleted: list[str] = []
        gated_children: set[str] = set()

        async def gate_writes(config: Any, writes: Any, task_id: Any, task_path: str = "") -> None:
            thread = config.get("configurable", {}).get("thread_id", "")
            if (
                window == "registered"
                and thread.startswith("chat-turn-")
                and any(key == "__interrupt__" for key, _ in writes)
            ):
                blocked.set()
                await asyncio.Event().wait()
            await put_writes(config, writes, task_id, task_path)

        async def gate_cleanup(thread: str) -> None:
            if thread.startswith("agent-delegation-"):
                deleted.append(thread)
                if window == "result_committed":
                    async with app.state.session_factory() as session:
                        status = await session.scalar(
                            text("SELECT status FROM agent_delegations WHERE id=:id"),
                            {"id": thread.removeprefix("agent-delegation-")},
                        )
                    if status == "COMPLETED" and thread not in gated_children:
                        gated_children.add(thread)
                        blocked.set()
                        await asyncio.Event().wait()
            await delete(thread)

        monkeypatch.setattr(saver, "aput_writes", gate_writes)
        monkeypatch.setattr(saver, "adelete_thread", gate_cleanup)
        sid = await create_session(client, scope="ALL")
        tid = (await submit(client, sid, "root:window", request_id="parallel-window")).json()["id"]
        await asyncio.wait_for(blocked.wait(), 10)
        completed = 0
        for _ in range(100):
            async with app.state.session_factory() as session:
                completed = await session.scalar(
                    text("SELECT count(*) FROM agent_delegations WHERE status='COMPLETED'")
                )
            if completed == 2:
                break
            await asyncio.sleep(0.05)
        assert completed == 2 and len(captured) == 3
        state = await snapshot(client, tid)
        assert state["status"] == ("RUNNING" if window == "registered" else "WAITING_JOB")
        assert (
            await saver.aget_tuple({"configurable": {"thread_id": f"chat-turn-{tid}"}}) is not None
        )
        async with app.state.session_factory() as session:
            before = (
                await session.execute(
                    text(
                        "SELECT id,job_id,input_json,result_json FROM agent_delegations "
                        "ORDER BY logical_call_id"
                    )
                )
            ).all()
            parent_input = await session.scalar(
                text("SELECT messages_json FROM chat_context_inputs WHERE turn_id=:id"), {"id": tid}
            )
        assert len(before) == 2
        for row, branch in zip(before, ("A", "B"), strict=True):
            frozen = json.loads(row.input_json)
            assert frozen["task"] == f"child:window:{branch}"
            assert frozen["task_id"] == row.id
        if window == "registered":
            assert {f"agent-delegation-{row.id}" for row in before} <= set(deleted)
            for row in before:
                assert (
                    await saver.aget_tuple(
                        {"configurable": {"thread_id": f"agent-delegation-{row.id}"}}
                    )
                    is None
                )
    async with turns_app(tmp_path, monkeypatch) as (app, client, captured):
        route_model(monkeypatch, routes)
        result = await wait_terminal(client, tid)
        assert result["status"] == "COMPLETED", result
        assert len(captured) == 1
        async with app.state.session_factory() as session:
            after = (
                await session.execute(
                    text(
                        "SELECT id,job_id,input_json,result_json FROM agent_delegations "
                        "ORDER BY logical_call_id"
                    )
                )
            ).all()
            assert after == before
            assert (
                await session.scalar(
                    text("SELECT messages_json FROM chat_context_inputs WHERE turn_id=:id"),
                    {"id": tid},
                )
                == parent_input
            )
            assert await session.scalar(text("SELECT count(*) FROM chat_turn_budget_calls")) == 2
            assert (
                await session.scalar(
                    text("SELECT count(DISTINCT interrupt_id) FROM chat_turn_waits")
                )
                == 2
            )
            assert (
                await session.scalar(
                    text("SELECT count(*) FROM chat_model_requests WHERE execution_id IS NOT NULL")
                )
                == 2
            )
        for row in before:
            assert (
                await app.state.chat_checkpointer.aget_tuple(
                    {"configurable": {"thread_id": f"agent-delegation-{row.id}"}}
                )
                is None
            )


@pytest.mark.anyio
async def test_one_slot_writeback_fault_keeps_sibling_claim_and_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.agent.turns import worker

    release, fault = asyncio.Event(), asyncio.Event()
    original = worker.writeback
    routes = {
        "root:slot": [delegates("slot"), ["汇总 A 与 B"]],
        "child:slot:A": [GatedReply(("证据 A",), release)],
        "child:slot:B": [["证据 B"]],
        "root:fresh": [["执行槽仍可用"]],
    }
    async with turns_app(tmp_path, monkeypatch) as (app, client, captured):
        route_model(monkeypatch, routes)

        async def fail_one_writeback(ctx: Any, result: bool, **kwargs: Any) -> bool:
            if ctx.delegation_id and not fault.is_set():
                async with app.state.session_factory() as session:
                    branch = await session.scalar(
                        text("SELECT logical_call_id FROM agent_delegations WHERE id=:id"),
                        {"id": ctx.delegation_id},
                    )
                if branch == "delegate-B":
                    fault.set()
                    raise RuntimeError("isolated slot writeback fault")
            return await original(ctx, result, **kwargs)

        monkeypatch.setattr(worker, "writeback", fail_one_writeback)
        sid = await create_session(client, scope="ALL")
        tid = (await submit(client, sid, "root:slot", request_id="parallel-slot-fault")).json()[
            "id"
        ]
        try:
            await asyncio.wait_for(fault.wait(), 10)
            jobs: Sequence[Row[Any]] = []
            for _ in range(100):
                async with app.state.session_factory() as session:
                    jobs = (
                        await session.execute(
                            text(
                                "SELECT d.id,d.status,d.claim_token,j.status AS job_status "
                                "FROM agent_delegations d JOIN processing_jobs j "
                                "ON j.id=d.job_id ORDER BY d.logical_call_id"
                            )
                        )
                    ).all()
                if len(jobs) == 2 and jobs[1].job_status == "FAILED":
                    break
                await asyncio.sleep(0.05)
            assert jobs[0].status == "RUNNING" and jobs[1].status == "COMPLETED"
            assert jobs[1].job_status == "FAILED" and len(captured) == 3
            saver = app.state.chat_checkpointer
            assert (
                await saver.aget_tuple({"configurable": {"thread_id": f"chat-turn-{tid}"}})
                is not None
            )
            assert (
                await saver.aget_tuple(
                    {"configurable": {"thread_id": f"agent-delegation-{jobs[0].id}"}}
                )
                is not None
            )
            assert (
                await saver.aget_tuple(
                    {"configurable": {"thread_id": f"agent-delegation-{jobs[1].id}"}}
                )
                is None
            )
            claim = jobs[0].claim_token
            release.set()
            assert (await wait_terminal(client, tid))["status"] == "COMPLETED"
            async with app.state.session_factory() as session:
                assert (
                    await session.scalar(
                        text("SELECT claim_token FROM agent_delegations WHERE id=:id"),
                        {"id": jobs[0].id},
                    )
                    == claim
                )
            fresh = await create_session(client)
            next_id = (
                await submit(client, fresh, "root:fresh", request_id="after-slot-fault")
            ).json()["id"]
            assert (await wait_terminal(client, next_id))["status"] == "COMPLETED"
        finally:
            release.set()
