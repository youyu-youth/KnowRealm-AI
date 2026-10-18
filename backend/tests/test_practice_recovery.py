"""04：经真实 HTTP、SQLite 与 Worker 验证定向恢复及原子重练。"""

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiosqlite
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.modules.agent.graph import resolve_agent_config
from app.modules.agent.runs.schemas import AuthMode
from app.modules.agent.runtime import (
    AgentRuntimeContext,
    bind_agent_runtime_context,
    reset_agent_runtime_context,
)
from app.modules.llm.service import StructuredModelResult
from app.modules.quiz.models import PracticeGradingRequest
from app.modules.record.models import LearningEvent
from tests.test_plan_editing import ITEM_ID, RECORD_ID, run_sql
from tests.test_practice_preparation import (
    BASE,
    add_questions,
    configure,
    save,
    seed,
    start,
    terminal,
)
from tests.test_practice_round import (
    GradingModel,
    answer_all,
    begin,
    practice_app,
    ready_fifteen,
    wait_status,
)


@pytest.mark.anyio
async def test_retry_completed_partial_round_only_grades_missing_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = GradingModel(16, invalid_count=1)
    async with practice_app(tmp_path, model) as (client, factory):
        await seed(factory)
        await ready_fifteen(client, factory, tmp_path, monkeypatch)
        test_id = (await begin(client, 1)).json()["test_id"]
        paper = (await client.get(f"/api/quiz-tests/{test_id}")).json()
        await answer_all(client, paper)
        await client.post(f"/api/quiz-tests/{test_id}/submit")
        partial = await wait_status(client, test_id, ("COMPLETED",))
        async with factory() as session:
            before_events = {event.id for event in await session.scalars(select(LearningEvent))}
        assert sum(item["result"] is not None for item in partial["items"]) == 14
        request = {"request_id": str(uuid4())}
        retry = await client.post(BASE + f"/rounds/{test_id}/retries", json=request)
        assert retry.status_code == 200, retry.text
        job_id = retry.json()["grading_job_id"]
        assert job_id
        done = await wait_status(client, test_id, ("COMPLETED",))
        assert model.calls == 16
        async with factory() as session:
            after_events = {event.id for event in await session.scalars(select(LearningEvent))}
        assert before_events < after_events
        assert len(after_events - before_events) == 1
        assert all(item["score"] == 0.5 for item in done["items"])
        assert done["items"][1:] == partial["items"][1:]
        replay = await client.post(BASE + f"/rounds/{test_id}/retries", json=request)
        assert replay.status_code == 200
        assert replay.json()["grading_job_id"] == job_id
        assert model.calls == 16
        completed_request = {"request_id": str(uuid4())}
        no_op = await client.post(BASE + f"/rounds/{test_id}/retries", json=completed_request)
        assert no_op.status_code == 200
        async with factory() as session:
            binding = await session.get(PracticeGradingRequest, completed_request["request_id"])
            assert binding is not None and binding.test_id == test_id and binding.job_id is None
        assert model.calls == 16


@pytest.mark.anyio
async def test_repractice_requires_confirmation_and_keeps_answers_until_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with practice_app(tmp_path, GradingModel(0)) as (client, factory):
        await seed(factory)
        await ready_fifteen(client, factory, tmp_path, monkeypatch)
        test_id = (await begin(client, 1)).json()["test_id"]
        paper = (await client.get(f"/api/quiz-tests/{test_id}")).json()
        await answer_all(client, paper, upto=6)
        current = (await client.get(BASE)).json()["round"]
        request = {
            "request_id": str(uuid4()),
            "requirements_revision": 1,
            "expected_round_id": test_id,
            "expected_round_version": current["version"],
        }
        denied = await client.post(BASE + "/preparations", json=request)
        assert denied.status_code == 409, denied.text
        request["abandon_confirmed"] = True
        prepared = await client.post(BASE + "/preparations", json=request)
        assert prepared.status_code == 202, prepared.text
        ready = await terminal(client)
        assert ready["outcome"] == "READY", ready
        assert ready["reused_count"] == 15
        unchanged = (await client.get(f"/api/quiz-tests/{test_id}")).json()
        assert unchanged["status"] == "IN_PROGRESS"
        assert unchanged["answered_count"] == 6
        body = {
            "request_id": str(uuid4()),
            "requirements_revision": 1,
            "preparation_id": prepared.json()["id"],
        }
        created = await client.post(BASE + "/rounds", json=body)
        assert created.status_code == 200, created.text
        assert created.json()["round_no"] == 2
        assert created.json()["test_id"] != test_id
        assert (await client.post(BASE + "/rounds", json=body)).json()["test_id"] == created.json()[
            "test_id"
        ]
        old = (await client.get(f"/api/quiz-tests/{test_id}")).json()
        assert old["status"] == "ABANDONED"
        assert old["answered_count"] == 6
        assert all(item["correct_answer"] is None for item in old["items"])
        state = (await client.get(BASE)).json()
        assert [row["round_no"] for row in state["rounds"]] == [2, 1]
        assert state["round"]["test_id"] == created.json()["test_id"]


async def restart_request(client: AsyncClient) -> dict[str, Any]:
    current = (await client.get(BASE)).json()["round"]
    return {
        "request_id": str(uuid4()),
        "requirements_revision": 1,
        "expected_round_id": current["test_id"],
        "expected_round_version": current["version"],
        "abandon_confirmed": current["status"] == "IN_PROGRESS",
    }


@pytest.mark.anyio
async def test_repractice_prioritizes_unused_and_concurrent_starts_share_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with practice_app(tmp_path, GradingModel(0)) as (client, factory):
        await seed(factory)
        configure(tmp_path, monkeypatch)
        await add_questions(factory, RECORD_ID, 30)
        await save(client, [RECORD_ID])
        await start(client, 1)
        await terminal(client)
        old_id = (await begin(client, 1)).json()["test_id"]
        old = (await client.get(f"/api/quiz-tests/{old_id}")).json()
        request = await restart_request(client)
        prepared = await client.post(BASE + "/preparations", json=request)
        assert prepared.status_code == 202, prepared.text
        ready = await terminal(client)
        assert ready["reused_count"] == 0
        bodies = [
            {
                "request_id": str(uuid4()),
                "requirements_revision": 1,
                "preparation_id": prepared.json()["id"],
            }
            for _ in range(2)
        ]
        responses = await asyncio.gather(
            *(client.post(BASE + "/rounds", json=body) for body in bodies)
        )
        assert [r.status_code for r in responses] == [200, 200]
        assert responses[0].json()["test_id"] == responses[1].json()["test_id"]
        changed = await client.post(
            BASE + "/rounds", json={**bodies[1], "preparation_id": str(uuid4())}
        )
        assert changed.status_code == 409, changed.text
        assert changed.json()["code"] == "PRACTICE_REQUEST_CONFLICT"
        new = (await client.get(f"/api/quiz-tests/{responses[0].json()['test_id']}")).json()
        assert len(new["items"]) == 15
        assert not ({q["quiz_id"] for q in old["items"]} & {q["quiz_id"] for q in new["items"]})


@pytest.mark.anyio
@pytest.mark.parametrize("change", ["fail", "cancel", "progress", "requirements", "source"])
async def test_unsuccessful_repractice_preserves_answerable_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    async with practice_app(tmp_path, GradingModel(0)) as (client, factory):
        await seed(factory)
        await ready_fifteen(client, factory, tmp_path, monkeypatch)
        test_id = (await begin(client, 1)).json()["test_id"]
        paper = (await client.get(f"/api/quiz-tests/{test_id}")).json()
        await answer_all(client, paper, upto=6)
        saved_answers = (await client.get(f"/api/quiz-tests/{test_id}")).json()["items"][:6]
        matcher = configure(tmp_path, monkeypatch)
        if change == "fail":
            matcher.mode = "forged"
        if change == "cancel":
            matcher.mode = "wait"
        prepared = await client.post(BASE + "/preparations", json=await restart_request(client))
        assert prepared.status_code == 202, prepared.text
        preparation_id = prepared.json()["id"]
        try:
            if change == "cancel":
                await asyncio.wait_for(matcher.started.wait(), 5)
                cancelled = await client.post(BASE + f"/preparations/{preparation_id}/cancel")
                assert cancelled.status_code == 200
                assert cancelled.json()["status"] == "CANCELLED"
            else:
                await terminal(client)
                if change == "progress":
                    await answer_all(client, paper, upto=7)
                elif change == "requirements":
                    await save(client, [RECORD_ID], question_count=14)
                elif change == "source":
                    await run_sql(
                        "UPDATE records SET deleted_at='2026-10-18' WHERE id=:id",
                        {"id": RECORD_ID},
                        factory,
                    )
            response = await client.post(
                BASE + "/rounds",
                json={
                    "request_id": str(uuid4()),
                    "requirements_revision": 1,
                    "preparation_id": preparation_id,
                },
            )
            assert response.status_code == 409, response.text
        finally:
            matcher.release.set()
        old = (await client.get(f"/api/quiz-tests/{test_id}")).json()
        assert old["status"] == "IN_PROGRESS"
        assert old["answered_count"] == (7 if change == "progress" else 6)
        assert [item["user_answer"] for item in old["items"][:6]] == [
            item["user_answer"] for item in saved_answers
        ]
        assert [item["answered_at"] for item in old["items"][:6]] == [
            item["answered_at"] for item in saved_answers
        ]
        state = (await client.get(BASE)).json()
        assert len(state["rounds"]) == 1


@pytest.mark.anyio
async def test_old_grading_finishes_after_new_round_without_changing_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_practice_round import COMPLETE

    model = GradingModel(15)
    model.pause = True
    async with practice_app(tmp_path, model) as (client, factory):
        await seed(factory)
        await ready_fifteen(client, factory, tmp_path, monkeypatch)
        test_id = (await begin(client, 1)).json()["test_id"]
        paper = (await client.get(f"/api/quiz-tests/{test_id}")).json()
        await answer_all(client, paper)
        await client.post(f"/api/quiz-tests/{test_id}/submit")
        try:
            await asyncio.wait_for(model.started.wait(), 5)
            first = (await client.post(COMPLETE)).json()
            prepared = await client.post(BASE + "/preparations", json=await restart_request(client))
            assert prepared.status_code == 202, prepared.text
            await terminal(client)
            next_round = await client.post(
                BASE + "/rounds",
                json={
                    "request_id": str(uuid4()),
                    "requirements_revision": 1,
                    "preparation_id": prepared.json()["id"],
                },
            )
            assert next_round.status_code == 200, next_round.text
        finally:
            model.release.set()
        await wait_status(client, test_id, ("COMPLETED",))
        state = (await client.get(BASE)).json()
        assert state["round"]["test_id"] == next_round.json()["test_id"]
        assert state["round"]["graded_count"] == 0
        assert state["rounds"][1]["score_denominator"] == 15
        repeated = (await client.post(COMPLETE)).json()
        assert repeated["completed_at"] == first["completed_at"]


class UnavailableGradingModel(GradingModel):
    unavailable = True

    async def generate(self, **kwargs: Any) -> StructuredModelResult:
        if self.unavailable:
            self.calls += 1
            raise TimeoutError("external model timed out")
        return await super().generate(**kwargs)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "invalidate",
    [
        "UPDATE learning_plans SET status='SUPERSEDED'",
        "UPDATE learning_goals SET status='COMPLETED'",
        "UPDATE learning_plan_items SET status='SKIPPED'",
    ],
)
async def test_retry_entry_respects_readonly_plan_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalidate: str
) -> None:
    async with practice_app(tmp_path, GradingModel(15, invalid_count=1)) as (client, factory):
        await seed(factory)
        await ready_fifteen(client, factory, tmp_path, monkeypatch)
        test_id = (await begin(client, 1)).json()["test_id"]
        await answer_all(client, (await client.get(f"/api/quiz-tests/{test_id}")).json())
        await client.post(f"/api/quiz-tests/{test_id}/submit")
        before = await wait_status(client, test_id, ("COMPLETED",))
        await run_sql(invalidate, {}, factory)
        response = await client.post(
            BASE + f"/rounds/{test_id}/retries", json={"request_id": str(uuid4())}
        )
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "PRACTICE_ITEM_UNAVAILABLE"
        assert (await client.get(f"/api/quiz-tests/{test_id}")).json()["items"] == before["items"]
        state = (await client.get(BASE)).json()
        assert state["editable"] is False
        assert state["round"]["retry_available"] is False


@pytest.mark.anyio
async def test_zero_score_concurrent_retry_replays_same_task_after_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = UnavailableGradingModel(15)
    async with practice_app(tmp_path, model) as (client, factory):
        await seed(factory)
        await ready_fifteen(client, factory, tmp_path, monkeypatch)
        test_id = (await begin(client, 1)).json()["test_id"]
        await answer_all(client, (await client.get(f"/api/quiz-tests/{test_id}")).json())
        await client.post(f"/api/quiz-tests/{test_id}/submit")
        await wait_status(client, test_id, ("COMPLETED",))
        partial = (await client.get(BASE)).json()["round"]
        assert partial["score"] is None
        assert partial["score_denominator"] is None
        assert partial["graded_count"] == 0
        assert len(partial["grading_errors"]) == 15
        model.unavailable = False
        model.pause = True
        bodies = [{"request_id": str(uuid4())} for _ in range(2)]
        try:
            responses = await asyncio.gather(
                *(client.post(BASE + f"/rounds/{test_id}/retries", json=body) for body in bodies)
            )
            assert [r.status_code for r in responses] == [200, 200]
            job_id = responses[0].json()["grading_job_id"]
            assert responses[1].json()["grading_job_id"] == job_id
        finally:
            model.release.set()
        done = await wait_status(client, test_id, ("COMPLETED",))
        assert model.calls == 30
        assert all(item["score"] == 0.5 for item in done["items"])
    async with practice_app(tmp_path, model) as (client, _factory):
        for body in bodies:
            replay = await client.post(BASE + f"/rounds/{test_id}/retries", json=body)
            assert replay.status_code == 200
            assert replay.json()["grading_job_id"] == job_id
        assert model.calls == 30


@pytest.mark.anyio
async def test_agent_retry_and_repractice_use_controlled_operations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = GradingModel(16, invalid_count=1)
    async with practice_app(tmp_path, model) as (client, factory):
        await seed(factory)
        await ready_fifteen(client, factory, tmp_path, monkeypatch)
        test_id = (await begin(client, 1)).json()["test_id"]
        await answer_all(client, (await client.get(f"/api/quiz-tests/{test_id}")).json())
        await client.post(f"/api/quiz-tests/{test_id}/submit")
        await wait_status(client, test_id, ("COMPLETED",))
        chat_id = (await client.post("/api/chat-sessions", json={})).json()["id"]
        tools = {
            tool.name: tool
            for tool in resolve_agent_config(retrieval=False, web_search_enabled=False).tools
        }
        token = bind_agent_runtime_context(
            AgentRuntimeContext(
                session_factory=factory, session_id=chat_id, auth_mode=AuthMode.REQUEST_APPROVAL
            )
        )
        try:
            result = json.loads(
                await tools["retry_plan_practice_grading"].ainvoke(
                    {
                        "item_id": ITEM_ID,
                        "test_id": test_id,
                        "request_id": str(uuid4()),
                    }
                )
            )
            assert result["ok"] is True, result
            assert "executed" not in result
            proposal_id = result["proposals"][0]["proposal_id"]
            confirmed = await client.post(f"/api/proposals/{proposal_id}/confirm")
            assert confirmed.status_code == 200, confirmed.text
            assert confirmed.json()["result"]["grading_job_id"]
            await wait_status(client, test_id, ("COMPLETED",))
            assert model.calls == 16
        finally:
            reset_agent_runtime_context(token)

        # 已交卷可直接准备下一轮；未交卷轮必须人工确认放弃影响。
        prepared = await client.post(BASE + "/preparations", json=await restart_request(client))
        await terminal(client)
        next_round = await client.post(
            BASE + "/rounds",
            json={
                "request_id": str(uuid4()),
                "requirements_revision": 1,
                "preparation_id": prepared.json()["id"],
            },
        )
        assert next_round.status_code == 200
        token = bind_agent_runtime_context(
            AgentRuntimeContext(
                session_factory=factory, session_id=chat_id, auth_mode=AuthMode.AUTO_APPROVE
            )
        )
        try:
            request = await restart_request(client)
            result = json.loads(
                await tools["prepare_plan_practice"].ainvoke({"item_id": ITEM_ID, **request})
            )
            assert result["ok"] is True, result
            assert "executed" not in result  # 自动档也不能替代业务上的放弃确认。
            proposal_id = result["proposals"][0]["proposal_id"]
            confirmed = await client.post(f"/api/proposals/{proposal_id}/confirm")
            assert confirmed.status_code == 200, confirmed.text
            assert confirmed.json()["result"]["expected_round_id"] == next_round.json()["test_id"]
            assert (await terminal(client))["outcome"] == "READY"
        finally:
            reset_agent_runtime_context(token)


class HoldLastGradingModel(GradingModel):
    async def generate(self, **kwargs: Any) -> StructuredModelResult:
        if self.calls == 14:
            self.pause = True
        return await super().generate(**kwargs)


@pytest.mark.anyio
async def test_real_running_snapshot_recovers_and_retries_only_last_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = HoldLastGradingModel(15)
    recovery_root = tmp_path / "recovery"
    (recovery_root / "KnowRealm").mkdir(parents=True)
    async with practice_app(tmp_path, model) as (client, factory):
        await seed(factory)
        await ready_fifteen(client, factory, tmp_path, monkeypatch)
        test_id = (await begin(client, 1)).json()["test_id"]
        await answer_all(client, (await client.get(f"/api/quiz-tests/{test_id}")).json())
        await client.post(f"/api/quiz-tests/{test_id}/submit")
        try:
            state: dict[str, Any] = {}
            for _ in range(160):
                state = (await client.get(BASE)).json()["round"]
                if state["graded_count"] == 14 and model.calls == 15:
                    break
                await asyncio.sleep(0.05)
            assert state["graded_count"] == 14
            assert state["grading_job_status"] == "RUNNING"
            original_request = {"request_id": str(uuid4())}
            accepted = await client.post(BASE + f"/rounds/{test_id}/retries", json=original_request)
            assert accepted.status_code == 200
            original_job_id = accepted.json()["grading_job_id"]
            # 备份真实在途事务的持久状态；不伪造 job 或逐题评分终态。
            async with (
                aiosqlite.connect(tmp_path / "KnowRealm/knowrealm.db") as source,
                aiosqlite.connect(recovery_root / "KnowRealm/knowrealm.db") as target,
            ):
                await source.backup(target)
        finally:
            model.release.set()
    configure(recovery_root, monkeypatch)
    recovered_model = GradingModel(1)
    async with practice_app(recovery_root, recovered_model) as (client, _factory):
        recovered = (await client.get(BASE)).json()["round"]
        assert recovered["status"] == "GRADING_FAILED"
        assert recovered["graded_count"] == 14
        assert recovered["error_code"] == "WORKER_INTERRUPTED"
        assert recovered["score"] == 0.5
        retry = await client.post(
            BASE + f"/rounds/{test_id}/retries", json={"request_id": str(uuid4())}
        )
        assert retry.status_code == 200, retry.text
        done = await wait_status(client, test_id, ("COMPLETED",))
        assert all(item["score"] == 0.5 for item in done["items"])
        assert recovered_model.calls == 1
        original = await client.post(BASE + f"/rounds/{test_id}/retries", json=original_request)
        assert original.json()["grading_job_id"] == original_job_id
        assert original.json()["grading_job_status"] == "FAILED"
        assert original.json()["error_code"] == "WORKER_INTERRUPTED"
        assert original.json()["score_denominator"] == 15
