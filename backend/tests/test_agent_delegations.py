"""单委派：真实 API、迁移库、双槽与图；仅外部模型替身。"""

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import httpx2
import openai
import pytest
from langchain_core.messages import ToolMessage
from langchain_core.outputs import ChatGenerationChunk
from sqlalchemy import text
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


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("scope", "source_suffix"),
    [("COURSE", "（来源：论文精读）"), ("RECORD", ""), ("RECORD", "（来源：论文精读）")],
)
async def test_single_delegation_uses_knowledge_and_returns_to_original_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scope: str, source_suffix: str
) -> None:
    from test_shared_refs import COURSE_ML, REC_AGENT_NOTE, REC_ML_PAPER, seed_full_corpus

    quote = "梯度下降通过反向传播迭代更新参数。"
    async with turns_app(
        tmp_path,
        monkeypatch,
        replies=[
            ToolCallReply("delegate_knowledge", {"task": "检索资料中的梯度下降原理"}, "delegate-1"),
            ToolCallReply("search_library", {"query": quote}, "search-1"),
            [f"本地材料说明[1]。\n[1] {quote}{source_suffix}"],
            ["专业检索已完成，已取得原文证据"],
        ],
    ) as (app, client, captured):
        await seed_full_corpus(app.state.session_factory)
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE records SET title='论文精读', updated_at=:now WHERE id=:id"),
                {"now": "2026-10-21T00:00:00.000000Z", "id": REC_AGENT_NOTE},
            )
            await session.execute(
                text("UPDATE transcripts SET content=:quote WHERE record_id=:id"),
                {"quote": quote, "id": REC_AGENT_NOTE},
            )
        mount = {"course_id": COURSE_ML} if scope == "COURSE" else {"record_id": REC_ML_PAPER}
        session_id = await create_session(client, scope=scope, **mount)
        accepted = await submit(
            client, session_id, "委派检索再汇总", request_id="delegation-success-1"
        )
        assert accepted.status_code == 202
        turn_id = accepted.json()["id"]
        result = await wait_terminal(client, turn_id)
        assert result["status"] == "COMPLETED", result
        assert len(captured) == 4
        reports = [
            json.loads(str(m.content))
            for m in captured[-1]
            if isinstance(m, ToolMessage) and m.name == "delegate_knowledge"
        ]
        assert reports[0]["status"] == "COMPLETED"
        assert reports[0]["contract_version"] == 1
        assert reports[0]["citations"][0]["record_id"] == REC_ML_PAPER
        assert reports[0]["citations"][0]["quote"] == quote
        tasks = result["background_tasks"]
        assert len(tasks) == 1 and tasks[0]["agent_id"] == "knowledge"
        assert tasks[0]["status"] == "COMPLETED"
        async with app.state.session_factory() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT execution_id, status, usage_json "
                        "FROM chat_model_requests ORDER BY created_at"
                    )
                )
            ).all()
            assert [row.execution_id is not None for row in rows] == [False, True, True, False]
            assert all(row.status == "COMPLETED" and row.usage_json is None for row in rows)
            assert await session.scalar(text("SELECT count(*) FROM chat_turn_budget_calls")) == 2
        before = await snapshot(client, turn_id)
        execution_id = tasks[0]["execution_id"]
        process = before["process"]["entries"]
        progress = next(entry for entry in process if entry["kind"] == "delegation")
        assert progress["execution_id"] == execution_id and progress["status"] == "COMPLETED"
        from app.modules.agent.turns.service import ChatTurnService

        await ChatTurnService.compact_events(
            session_factory=app.state.session_factory, turn_id=turn_id
        )
        assert (await snapshot(client, turn_id))["process"] == before["process"]


def timeout_external_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.llm import service

    model = cast(type[StubChatModel], service.ChatOpenAI)

    class TimeoutModel(model):
        async def _astream(
            self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
        ) -> AsyncIterator[ChatGenerationChunk]:
            if type(self).replies and type(self).replies[0] is None:
                type(self).replies.pop(0)
                type(self).captured.append(list(messages))
                raise openai.APITimeoutError(
                    request=httpx2.Request("POST", "https://stub.example.com/v1")
                )
            async for chunk in super()._astream(messages, stop, run_manager, **kwargs):
                yield chunk

    monkeypatch.setattr(service, "ChatOpenAI", TimeoutModel)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("kind", "repeat_timeout"),
    [("RETRY_DELEGATIONS", False), ("RETRY_DELEGATIONS", True), ("ACCEPT_PARTIAL", False)],
)
async def test_unknown_request_requires_bound_choice_and_keeps_unknown_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, repeat_timeout: bool
) -> None:
    release = asyncio.Event()
    async with turns_app(
        tmp_path,
        monkeypatch,
        replies=[
            ToolCallReply("delegate_knowledge", {"task": "检索事务隔离"}, "delegate-unknown"),
            None,
            *([None] if repeat_timeout else []),
            *([GatedReply(("子报告",), release)] if kind == "RETRY_DELEGATIONS" else []),
            ["最终汇总"],
        ],
    ) as (app, client, captured):
        timeout_external_model(monkeypatch)
        session_id = await create_session(client, scope="ALL")
        turn_id = (
            await submit(client, session_id, "委派检索", request_id="delegation-unknown-1")
        ).json()["id"]
        waiting = await wait_status(client, turn_id, "WAITING_USER")
        reason = waiting["waiting_reason"]
        assert reason["kind"] == "DELEGATION_UNCERTAIN"
        assert len(captured) == 2
        from app.modules.agent.delegations.models import AgentDelegation
        from app.modules.agent.turns.worker import (
            _ClaimedTurn as ClaimedTurn,  # pyright: ignore[reportPrivateUsage]
        )
        from app.modules.agent.turns.worker import (
            writeback,
        )

        async with app.state.session_factory() as session:
            child = await session.get(AgentDelegation, reason["delegations"][0]["execution_id"])
            assert child is not None and child.claim_token is not None
            old_claim = ClaimedTurn(
                job_id=child.job_id,
                record_id="",
                turn_id=turn_id,
                delegation_id=child.id,
                claim_token=child.claim_token,
            )
        assert (
            await client.post(
                f"/api/chat-turns/{turn_id}/resume", json={"decision_kind": "RETRY_AFTER_FIX"}
            )
        ).status_code == 409
        decision = {
            "decision_kind": kind,
            "decision_id": "stable-decision-1",
            "snapshot_id": reason["snapshot_id"],
            "delegations": reason["delegations"],
        }
        wrong = {**decision, "snapshot_id": "stale-snapshot"}
        assert (
            await client.post(f"/api/chat-turns/{turn_id}/resume", json=wrong)
        ).status_code == 409
        result = await client.post(f"/api/chat-turns/{turn_id}/resume", json=decision)
        assert result.status_code == 200, result.text
        if repeat_timeout:
            waiting = await wait_status(client, turn_id, "WAITING_USER")
            next_reason = waiting["waiting_reason"]
            assert next_reason["snapshot_id"] != reason["snapshot_id"]
            assert len(captured) == 3
            replay = await client.post(f"/api/chat-turns/{turn_id}/resume", json=decision)
            assert replay.status_code == 200
            assert replay.json()["turn"]["status"] == "WAITING_USER"
            assert (
                await client.post(
                    f"/api/chat-turns/{turn_id}/resume",
                    json={**decision, "decision_id": "stale-decision-2"},
                )
            ).status_code == 409
            decision = {
                **decision,
                "decision_id": "stable-decision-2",
                "snapshot_id": next_reason["snapshot_id"],
                "delegations": next_reason["delegations"],
            }
            result = await client.post(f"/api/chat-turns/{turn_id}/resume", json=decision)
            assert result.status_code == 200, result.text
        if kind == "RETRY_DELEGATIONS":
            for _ in range(100):
                if len(captured) == 3 + int(repeat_timeout):
                    break
                await asyncio.sleep(0.05)
            assert len(captured) == 3 + int(repeat_timeout)
            assert not await writeback(old_claim, True, session_factory=app.state.session_factory)
            async with app.state.session_factory() as session:
                assert (
                    await session.scalar(
                        text("SELECT status FROM processing_jobs WHERE id=:id"),
                        {"id": old_claim.job_id},
                    )
                    == "RUNNING"
                )
            release.set()
        assert (await wait_terminal(client, turn_id))["status"] == "COMPLETED"
        calls = len(captured)
        assert calls == (4 + int(repeat_timeout) if kind == "RETRY_DELEGATIONS" else 3)
        assert (
            await client.post(f"/api/chat-turns/{turn_id}/resume", json=decision)
        ).status_code == 200
        assert len(captured) == calls
        assert (
            await client.post(
                f"/api/chat-turns/{turn_id}/resume",
                json={**decision, "decision_id": "late-decision-2"},
            )
        ).status_code == 409
        async with app.state.session_factory() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT id, status, usage_json, retry_of, decision_id "
                        "FROM chat_model_requests WHERE execution_id IS NOT NULL "
                        "ORDER BY created_at"
                    )
                )
            ).all()
            assert rows[0].status == "STARTED" and rows[0].usage_json is None
            if kind == "RETRY_DELEGATIONS":
                if repeat_timeout:
                    assert rows[1].status == "STARTED" and rows[1].usage_json is None
                    assert rows[1].retry_of == rows[0].id
                    assert rows[1].decision_id == "stable-decision-1"
                assert rows[-1].retry_of == rows[-2].id
                assert rows[-1].decision_id == decision["decision_id"]
                assert rows[-1].status == "COMPLETED"
            assert await session.scalar(text("SELECT count(*) FROM chat_turn_budget_calls")) == 1


@pytest.mark.anyio
async def test_parent_wait_releases_slot_and_cancel_rejects_late_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = asyncio.Event()
    async with turns_app(
        tmp_path,
        monkeypatch,
        replies=[
            ToolCallReply("delegate_knowledge", {"task": "检索事务隔离"}),
            GatedReply(("子输出",), release),
            ["其他会话回答"],
        ],
    ) as (app, client, captured):
        parent = await create_session(client, scope="ALL")
        turn_id = (await submit(client, parent, "委派", request_id="delegation-cancel-1")).json()[
            "id"
        ]
        waiting = await wait_status(client, turn_id, "WAITING_JOB")
        for _ in range(100):
            if len(captured) == 2:
                break
            await asyncio.sleep(0.05)
        assert len(captured) == 2
        child = (await snapshot(client, turn_id))["background_tasks"][0]
        assert child["status"] == "RUNNING"
        from dataclasses import replace

        from app.modules.agent.delegations.models import AgentDelegation
        from app.modules.agent.delegations.schemas import KnowledgeResult
        from app.modules.agent.delegations.service import commit_result
        from app.modules.agent.runtime import AgentRuntimeContext
        from app.modules.agent.schemas import AgentId

        async with app.state.session_factory() as session, session.begin():
            saved_child = await session.get(AgentDelegation, child["execution_id"])
            assert saved_child is not None
            runtime = AgentRuntimeContext(
                app.state.session_factory,
                parent,
                agent_id=AgentId.KNOWLEDGE,
                turn_id=turn_id,
                execution_id=saved_child.id,
                execution_attempt=saved_child.attempt,
                execution_claim_token=saved_child.claim_token,
            )
            assert await runtime.turn_write_allowed(session)
            assert not await replace(runtime, turn_id=None).turn_write_allowed(session)
            assert not await replace(runtime, turn_id="wrong-root").turn_write_allowed(session)
            assert not await replace(
                runtime, execution_claim_token="stale-claim"
            ).turn_write_allowed(session)
            assert not await replace(runtime, execution_attempt=0).turn_write_allowed(session)
            from app.modules.agent.budget.service import BudgetRejected, admit

            with pytest.raises(BudgetRejected, match="AGENT_CONTEXT_UNBOUND"):
                await admit(replace(runtime, turn_id=None), "search_library", {"query": "事务"})
        other = await create_session(client)
        other_id = (
            await submit(client, other, "其他请求", request_id="other-conversation-1")
        ).json()["id"]
        assert (await wait_terminal(client, other_id))["status"] == "COMPLETED"
        assert (await client.post(f"/api/chat-turns/{turn_id}/cancel")).status_code == 200
        release.set()
        cancelled = await wait_terminal(client, turn_id)
        assert cancelled["status"] == "CANCELLED"
        assert "子输出" not in cancelled["output_text"]
        assert len(captured) == 3
        assert cancelled["last_seq"] > waiting["last_seq"]
        assert not await commit_result(
            runtime,
            KnowledgeResult(task_id=child["execution_id"], status="COMPLETED", summary="迟到报告"),
        )
        assert (await snapshot(client, turn_id))["last_seq"] == cancelled["last_seq"]
        async with app.state.session_factory() as session:
            assert await session.scalar(text("SELECT status FROM agent_delegations")) == "CANCELLED"
            assert (
                await session.scalar(
                    text("SELECT status FROM chat_model_requests WHERE execution_id IS NOT NULL")
                )
                == "STARTED"
            )


@pytest.mark.anyio
async def test_restart_does_not_resend_started_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = asyncio.Event()
    async with turns_app(
        tmp_path,
        monkeypatch,
        replies=[
            ToolCallReply("delegate_knowledge", {"task": "检索事务隔离"}),
            GatedReply(("尚未完成",), release),
        ],
    ) as (_, client, captured):
        session_id = await create_session(client, scope="ALL")
        turn_id = (
            await submit(client, session_id, "委派", request_id="delegation-restart-1")
        ).json()["id"]
        await wait_status(client, turn_id, "WAITING_JOB")
        for _ in range(100):
            if len(captured) == 2:
                break
            await asyncio.sleep(0.05)
        assert len(captured) == 2
    async with turns_app(tmp_path, monkeypatch, replies=[]) as (_, client, captured):
        result = await wait_status(client, turn_id, "WAITING_USER")
        assert result["waiting_reason"]["kind"] == "DELEGATION_UNCERTAIN"
        assert not captured
        await client.post(f"/api/chat-turns/{turn_id}/cancel")


@pytest.mark.anyio
async def test_parent_and_child_share_six_admissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with turns_app(
        tmp_path,
        monkeypatch,
        replies=[
            ToolCallReply("delegate_knowledge", {"task": "检索事务隔离"}),
            *[
                ToolCallReply("search_library", {"query": f"事务 隔离 {n}"}, f"search-{n}")
                for n in range(6)
            ],
            ["检索完成"],
            ["汇总完成"],
        ],
    ) as (app, client, captured):
        session_id = await create_session(client, scope="ALL")
        turn_id = (
            await submit(client, session_id, "委派检索", request_id="delegation-budget-1")
        ).json()["id"]
        assert (await wait_terminal(client, turn_id))["status"] == "COMPLETED"
        tool = next(
            m for m in captured[-2] if isinstance(m, ToolMessage) and m.tool_call_id == "search-5"
        )
        assert "本轮检索次数已达上限" in str(tool.content)
        async with app.state.session_factory() as session:
            assert await session.scalar(text("SELECT count(*) FROM chat_turn_budget_calls")) == 6
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM chat_turn_budget_calls WHERE execution_id IS NOT NULL"
                    )
                )
                == 5
            )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "window",
    [
        "registered",
        "graph_completed",
        "result_committed",
        "request_completed",
        "request_completed_budget_changed",
        "provider_wait",
    ],
)
async def test_restart_reconciles_persistence_windows_without_repeating_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, window: str
) -> None:
    blocked = asyncio.Event()
    child_blocked = asyncio.Event()
    async with turns_app(
        tmp_path,
        monkeypatch,
        replies=[
            ToolCallReply("delegate_knowledge", {"task": "检索事务隔离"}),
            ["可靠子报告"],
        ],
    ) as (app, client, captured):
        saver = app.state.chat_checkpointer
        put, delete, put_writes = saver.aput, saver.adelete_thread, saver.aput_writes

        async def request_gate(config: Any, writes: Any, task_id: Any, task_path: str = "") -> None:
            thread = config.get("configurable", {}).get("thread_id", "")
            if (
                window in ("registered", "provider_wait")
                and thread.startswith("chat-turn-")
                and any(key == "__interrupt__" for key, _value in writes)
            ):
                blocked.set()
                await asyncio.Event().wait()
            if (
                window.startswith("request_completed")
                and thread.startswith("agent-delegation-")
                and any(key == "messages" for key, _value in writes)
            ):
                async with app.state.session_factory() as session:
                    completed = await session.scalar(
                        text(
                            "SELECT count(*) FROM chat_model_requests "
                            "WHERE execution_id IS NOT NULL AND status='COMPLETED'"
                        )
                    )
                if completed:
                    if window == "request_completed_budget_changed":
                        from app.modules.agent.budget.service import admit
                        from app.modules.agent.runtime import current_agent_runtime
                        from app.modules.agent.turns.effects import (
                            ToolCallIdentity,
                            bind_tool_call_identity,
                            reset_tool_call_identity,
                        )

                        runtime = current_agent_runtime()
                        assert runtime is not None and runtime.execution_id is not None
                        identity = bind_tool_call_identity(
                            ToolCallIdentity(thread, "concurrent-budget-consumption")
                        )
                        try:
                            # 模型完成但 checkpoint 未保存期间，模拟并发消费改变共享余额。
                            await admit(runtime, "search_library", {"query": "并发消费"})
                        finally:
                            reset_tool_call_identity(identity)
                    blocked.set()
                    await asyncio.Event().wait()
            await put_writes(config, writes, task_id, task_path)

        async def checkpoint_gate(
            config: Any, checkpoint: Any, metadata: Any, versions: Any
        ) -> Any:
            thread = config.get("configurable", {}).get("thread_id", "")
            if window == "provider_wait" and thread.startswith("agent-delegation-"):
                child_blocked.set()
                await asyncio.Event().wait()
            saved = await put(config, checkpoint, metadata, versions)
            if (
                window == "graph_completed"
                and thread.startswith("agent-delegation-")
                and not checkpoint["channel_values"]
            ):
                blocked.set()
                await asyncio.Event().wait()
            return saved

        async def cleanup_gate(thread: str) -> None:
            if (
                window == "result_committed"
                and thread.startswith("agent-delegation-")
                and not blocked.is_set()
            ):
                async with app.state.session_factory() as session:
                    completed = await session.scalar(
                        text("SELECT count(*) FROM agent_delegations WHERE status='COMPLETED'")
                    )
                if completed:
                    blocked.set()
                    await asyncio.Event().wait()
            await delete(thread)

        # 注入只停驻公开 checkpoint I/O；业务登记、模型请求、结果提交均执行真实路径。
        monkeypatch.setattr(saver, "aput", checkpoint_gate)
        monkeypatch.setattr(saver, "adelete_thread", cleanup_gate)
        monkeypatch.setattr(saver, "aput_writes", request_gate)
        session_id = await create_session(client, scope="ALL")
        turn_id = (
            await submit(client, session_id, "委派检索", request_id="delegation-window-1")
        ).json()["id"]
        await asyncio.wait_for(blocked.wait(), 10)
        assert (await snapshot(client, turn_id))["status"] == (
            "RUNNING" if window in ("registered", "provider_wait") else "WAITING_JOB"
        )
        if window == "provider_wait":
            await asyncio.wait_for(child_blocked.wait(), 10)
        if window == "registered":
            completed = 0
            for _ in range(100):
                async with app.state.session_factory() as session:
                    completed = await session.scalar(
                        text("SELECT count(*) FROM agent_delegations WHERE status='COMPLETED'")
                    )
                if completed:
                    break
                await asyncio.sleep(0.05)
            assert completed
        assert len(captured) == (1 if window == "provider_wait" else 2)
    async with turns_app(
        tmp_path,
        monkeypatch,
        replies=[]
        if window.startswith("request_completed")
        else [["可靠子报告"], ["汇总已有子报告"]]
        if window == "provider_wait"
        else [["汇总已有子报告"]],
    ) as (
        app,
        client,
        captured,
    ):
        if window == "provider_wait":
            from app.modules.settings.config import grant_llm_consent, save_llm_provider
            from app.modules.settings.model_budget import ModelBudgetConfig

            save_llm_provider(
                tmp_path,
                base_url="https://changed.example.com/v1",
                api_key="sk-changed",
                model="changed-model",
                clear_api_key=False,
                model_budget=ModelBudgetConfig(context_window=128000),
            )
            grant_llm_consent(tmp_path)
            waiting = await wait_status(client, turn_id, "WAITING_USER")
            assert waiting["waiting_reason"]["kind"] == "PROVIDER_CHANGED"
            async with app.state.session_factory() as session:
                assert (
                    await session.scalar(text("SELECT status FROM agent_delegations")) == "QUEUED"
                )
                assert (
                    await session.scalar(
                        text(
                            "SELECT status FROM processing_jobs "
                            "WHERE id=(SELECT job_id FROM agent_delegations)"
                        )
                    )
                    == "PENDING"
                )
            save_llm_provider(
                tmp_path,
                base_url="https://stub.example.com/v1",
                api_key="sk-test",
                model="stub-chat-model",
                clear_api_key=False,
                model_budget=ModelBudgetConfig(context_window=128000),
            )
            grant_llm_consent(tmp_path)
            assert (
                await client.post(
                    f"/api/chat-turns/{turn_id}/resume", json={"decision_kind": "RETRY_AFTER_FIX"}
                )
            ).status_code == 200
        if window.startswith("request_completed"):
            waiting = await wait_status(client, turn_id, "WAITING_USER")
            assert waiting["waiting_reason"]["kind"] == "CHECKPOINT_MISSING"
            assert not captured
            await client.post(f"/api/chat-turns/{turn_id}/cancel")
            return
        result = await wait_terminal(client, turn_id)
        assert result["status"] == "COMPLETED", (
            result["error_code"],
            result["error_message"],
            len(captured),
            result["background_tasks"],
        )
        assert len(captured) == (2 if window == "provider_wait" else 1)
        async with app.state.session_factory() as session:
            assert await session.scalar(text("SELECT count(*) FROM agent_delegations")) == 1
            assert await session.scalar(text("SELECT count(*) FROM chat_turn_waits")) == 1
            assert await session.scalar(text("SELECT count(*) FROM chat_turn_budget_calls")) == 1
            assert (
                await session.scalar(
                    text("SELECT count(*) FROM chat_model_requests WHERE execution_id IS NOT NULL")
                )
                == 1
            )
