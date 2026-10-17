"""计划练习准备：真实 HTTP、迁移 SQLite、生产 Worker；仅替换外部推理。"""

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.modules.agent.auth_mode import clear_session_auth_override, set_session_auth_override
from app.modules.agent.graph import resolve_agent_config
from app.modules.agent.runs.schemas import AuthMode
from app.modules.agent.runtime import (
    AgentRuntimeContext,
    bind_agent_runtime_context,
    reset_agent_runtime_context,
)
from app.modules.llm import service as llm_service
from app.modules.llm.models import LlmCallLog
from app.modules.quiz.models import Quiz
from app.modules.record.models import Record
from app.modules.settings.config import grant_llm_consent, save_llm_provider
from app.modules.settings.model_budget import ModelBudgetConfig
from tests.test_plan_editing import (
    COURSE_ID,
    ITEM_ID,
    PLAN_ID,
    RECORD_ID,
    plan_app,
    run_sql,
    seed_course,
    seed_goal,
    seed_item,
    seed_plan,
    seed_record,
)

BASE = f"/api/plan-items/{ITEM_ID}/practice"


async def seed(factory: Any) -> None:
    await seed_course(factory)
    await seed_goal(factory)
    await seed_record(factory)
    await seed_plan(factory)
    await seed_item(factory, ITEM_ID, content="做 15 道 Redis 基础题")
    await run_sql(
        "UPDATE learning_plan_items SET action_type='PRACTICE_QUIZ' WHERE id=:id",
        {"id": ITEM_ID},
        factory,
    )


def requirements(**changes: Any) -> dict[str, Any]:
    return {
        "expected_revision": 0,
        "plan_content": "做 15 道 Redis 基础题",
        "topic": "Redis 基础",
        "question_count": 15,
        "question_types": ["SHORT_ANSWER"],
        "record_ids": [RECORD_ID],
        "source_versions": {},
        **changes,
    }


@pytest.mark.anyio
async def test_requirements_revision_and_owned_sources(tmp_path: Path) -> None:
    async with plan_app(tmp_path) as (client, factory):
        await seed(factory)
        state = (await client.get(BASE)).json()
        payload = requirements(
            source_versions={source["record_id"]: source["version"] for source in state["sources"]}
        )
        assert (
            await client.put(BASE + "/requirements", json=requirements(question_count=0))
        ).status_code == 422
        saved = await client.put(BASE + "/requirements", json=payload)
        assert saved.status_code == 200, saved.text
        assert saved.json()["revision"] == 1
        assert (await client.put(BASE + "/requirements", json=payload)).status_code == 409
        invalid = requirements(expected_revision=1, record_ids=[str(uuid4())])
        assert (await client.put(BASE + "/requirements", json=invalid)).status_code == 409
        plan = (await client.get(f"/api/courses/{COURSE_ID}/plans/{PLAN_ID}")).json()
        assert plan["items"][0]["content"] == "做 15 道 Redis 基础题"
        state = (await client.get(BASE)).json()
        assert state["requirements"]["revision"] == 1
        assert "correct_answer" not in json.dumps(state)


class ControlledModel:
    def __init__(self) -> None:
        self.mode = "normal"
        self.calls = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.prompts: list[dict[str, Any]] = []

    async def generate(self, **kwargs: Any) -> llm_service.StructuredModelResult:
        self.calls += 1
        data = json.loads(kwargs["prompt"].split("\n")[-1])
        self.prompts.append(data)
        assert "correct_answer" not in kwargs["prompt"]
        assert "user_answer" not in kwargs["prompt"]
        assert "秘密" not in kwargs["prompt"]
        self.started.set()
        if self.mode == "wait":
            await self.release.wait()
        if self.mode == "fail":
            raise RuntimeError("external provider unavailable")
        decisions = [
            {
                "quiz_id": candidate["quiz_id"],
                "relevant": candidate["stem"].startswith("Redis"),
                "reason": "TOPIC_CONCEPT"
                if candidate["stem"].startswith("Redis")
                else "OUT_OF_TOPIC",
            }
            for candidate in data["candidates"]
        ]
        if self.mode == "forged":
            decisions[0]["quiz_id"] = str(uuid4())
        if self.mode == "duplicate":
            decisions.append(decisions[0])
        if self.mode == "partial":
            decisions.pop()
        if self.mode == "uncertain":
            decisions = [
                {"quiz_id": candidate["quiz_id"], "relevant": False, "reason": "UNCERTAIN"}
                for candidate in data["candidates"]
            ]
        return llm_service.StructuredModelResult(
            output={"decisions": decisions},
            token_usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
        )


def configure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ControlledModel:
    data_dir = tmp_path / "KnowRealm"
    save_llm_provider(
        data_dir,
        base_url="http://127.0.0.1:1/v1",
        api_key="test-key",
        model="test-model",
        clear_api_key=False,
        model_budget=ModelBudgetConfig(input_limit=100_000),
    )
    grant_llm_consent(data_dir)
    model = ControlledModel()

    async def generate(_self: object, **kwargs: Any) -> llm_service.StructuredModelResult:
        return await model.generate(**kwargs)

    monkeypatch.setattr(
        llm_service.OpenAiCompatiblePracticeMatchModel,
        "generate",
        generate,
    )
    return model


async def add_record(factory: Any, course_id: str = COURSE_ID) -> str:
    id_ = str(uuid4())
    async with factory() as session, session.begin():
        session.add(
            Record(
                id=id_,
                course_id=course_id,
                capture_type="DOCUMENT_IMPORT",
                title="Redis 补充资料",
                status="SUMMARY_READY",
                duration_ms=0,
            )
        )
    return id_


async def add_questions(
    factory: Any,
    record_id: str,
    count: int,
    *,
    prefix: str = "Redis",
    start: int = 0,
    question_type: str = "SHORT_ANSWER",
    status: str = "ACTIVE",
) -> None:
    async with factory() as session, session.begin():
        for index in range(start, start + count):
            session.add(
                Quiz(
                    record_id=record_id,
                    generation_status=status,
                    question_type=question_type,
                    stem=f"{prefix} 基础问题 {index}",
                    options_json="[]",
                    correct_answer_json=json.dumps("秘密参考答案"),
                    explanation="秘密解析",
                    difficulty="MEDIUM",
                )
            )


async def save(client: Any, record_ids: list[str], **changes: Any) -> dict[str, Any]:
    state = (await client.get(BASE)).json()
    payload = requirements(
        expected_revision=state["requirements"]["revision"] if state["requirements"] else 0,
        record_ids=record_ids,
        source_versions={
            source["record_id"]: source["version"]
            for source in state["sources"]
            if source["record_id"] in record_ids
        },
        **changes,
    )
    response = await client.put(BASE + "/requirements", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


async def start(client: Any, revision: int, request_id: str | None = None) -> dict[str, Any]:
    response = await client.post(
        BASE + "/preparations",
        json={"request_id": request_id or str(uuid4()), "requirements_revision": revision},
    )
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "PENDING"
    return response.json()


async def terminal(client: Any) -> dict[str, Any]:
    for _ in range(160):
        latest = (await client.get(BASE)).json()["preparations"][0]
        if latest["status"] not in ("PENDING", "RUNNING"):
            return latest
        await asyncio.sleep(0.05)
    pytest.fail("production worker did not finish")


@pytest.mark.anyio
async def test_exact_fifteen_requires_confirmed_eight_plus_seven_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with plan_app(tmp_path) as (client, factory):
        await seed(factory)
        model = configure(tmp_path, monkeypatch)
        second = await add_record(factory)
        await add_questions(factory, RECORD_ID, 8)
        await add_questions(factory, second, 7, start=8)
        await add_questions(factory, RECORD_ID, 1)  # 完全相同副本不凑数
        await add_questions(factory, RECORD_ID, 1, prefix="Docker")
        await add_questions(factory, RECORD_ID, 1, prefix="未采纳", status="DRAFT")
        await add_questions(
            factory, RECORD_ID, 2, prefix="Redis 单选", question_type="MULTIPLE_CHOICE"
        )
        await save(client, [RECORD_ID])
        request_id = str(uuid4())
        accepted = await start(client, 1, request_id)
        gap = await terminal(client)
        assert gap["outcome"] == "INSUFFICIENT"
        assert (gap["target_count"], gap["eligible_count"], gap["related_count"]) == (15, 9, 8)
        assert gap["selected_count"] == 0
        assert gap["suggestions"][0]["record_id"] == second
        assert gap["suggestions"][0]["related_count"] == 7
        assert gap["course_scan_complete"] is True
        replay = await client.post(
            BASE + "/preparations", json={"request_id": request_id, "requirements_revision": 1}
        )
        assert replay.json()["job_id"] == accepted["job_id"]
        assert model.calls == 2
        # 拒绝建议就是不确认，旧要求和结果仍可查。
        assert (await client.get(BASE)).json()["requirements"]["record_ids"] == [RECORD_ID]
        await save(client, [RECORD_ID, second])
        await start(client, 2)
        result = await terminal(client)
        assert (result["outcome"], result["selected_count"], result["related_count"]) == (
            "READY",
            15,
            15,
        )
        serialized = json.dumps((await client.get(BASE)).json(), ensure_ascii=False)
        assert "秘密" not in serialized
        assert "stem" not in serialized
        assert all(
            candidate["question_type"] == "SHORT_ANSWER"
            for prompt in model.prompts
            for candidate in prompt["candidates"]
        )
        async with factory() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(LlmCallLog)
                    .where(LlmCallLog.graph_name == "plan-practice")
                )
                == 3
            )


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["forged", "duplicate", "partial", "fail"])
async def test_bad_model_output_never_becomes_shortage_and_retry_keeps_requirements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    async with plan_app(tmp_path) as (client, factory):
        await seed(factory)
        model = configure(tmp_path, monkeypatch)
        await add_questions(factory, RECORD_ID, 15)
        await save(client, [RECORD_ID])
        model.mode = mode
        await start(client, 1)
        failed = await terminal(client)
        assert failed["status"] == "FAILED"
        assert failed["outcome"] == "INCOMPLETE"
        assert failed["error_code"] == (
            "PROVIDER_REQUEST_FAILED" if mode == "fail" else "PRACTICE_MATCH_INVALID"
        )
        assert (await client.get(BASE)).json()["requirements"]["revision"] == 1
        model.mode = "normal"
        await start(client, 1)
        assert (await terminal(client))["selected_count"] == 15


@pytest.mark.anyio
@pytest.mark.parametrize("change", ["cancel", "revision", "source", "quiz"])
async def test_commit_rejects_changes_while_model_is_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    async with plan_app(tmp_path) as (client, factory):
        await seed(factory)
        model = configure(tmp_path, monkeypatch)
        model.mode = "wait"
        await add_questions(factory, RECORD_ID, 15)
        await save(client, [RECORD_ID])
        accepted = await start(client, 1)
        await asyncio.wait_for(model.started.wait(), 5)
        assert (await client.get(BASE)).json()["preparations"][0]["status"] == "RUNNING"
        if change == "cancel":
            assert (await client.post(BASE + f"/preparations/{accepted['id']}/cancel")).json()[
                "status"
            ] == "CANCELLED"
        elif change == "revision":
            await save(client, [RECORD_ID], question_count=10)
        elif change == "source":
            await run_sql(
                "UPDATE records SET deleted_at=:now WHERE id=:id",
                {"id": RECORD_ID, "now": "2026-10-17T00:00:00Z"},
                factory,
            )
        else:
            await run_sql(
                "UPDATE quizzes SET stem='Redis 修改后的题面' WHERE record_id=:id",
                {"id": RECORD_ID},
                factory,
            )
        model.release.set()
        result = await terminal(client)
        assert result["status"] == ("CANCELLED" if change == "cancel" else "FAILED")
        assert result["selected_count"] == 0
        if change in ("cancel", "revision", "source"):
            async with factory() as session:
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(LlmCallLog)
                        .where(LlmCallLog.graph_name == "plan-practice")
                    )
                    == 0
                )


@pytest.mark.anyio
async def test_confirmed_scope_ready_without_unconfirmed_model_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with plan_app(tmp_path) as (client, factory):
        await seed(factory)
        model = configure(tmp_path, monkeypatch)
        await add_questions(factory, RECORD_ID, 15)
        other = await add_record(factory)
        await add_questions(factory, other, 30, start=100)
        await save(client, [RECORD_ID])
        await start(client, 1)
        final = await terminal(client)
        assert final["status"] == "SUCCEEDED"
        assert final["selected_count"] == 15
        assert final["examined_count"] == 15
        assert final["course_scan_complete"] is False
        assert final["sources"][0]["matching_basis"] == ["TOPIC_CONCEPT"]
        assert model.calls == 1


@pytest.mark.anyio
async def test_uncertain_relevance_is_incomplete_not_inventory_shortage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with plan_app(tmp_path) as (client, factory):
        await seed(factory)
        model = configure(tmp_path, monkeypatch)
        model.mode = "uncertain"
        await add_questions(factory, RECORD_ID, 15)
        await save(client, [RECORD_ID])
        await start(client, 1)
        result = await terminal(client)
        assert result["status"] == "SUCCEEDED"
        assert result["outcome"] == "INCOMPLETE"
        assert result["course_scan_complete"] is False
        assert result["selected_count"] == 0


@pytest.mark.anyio
@pytest.mark.parametrize("blocked", ["consent", "budget", "provider"])
async def test_outbound_gates_preserve_requirements_without_model_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, blocked: str
) -> None:
    async with plan_app(tmp_path) as (client, factory):
        await seed(factory)
        model = configure(tmp_path, monkeypatch)
        await add_questions(factory, RECORD_ID, 15)
        await save(client, [RECORD_ID])
        data_dir = tmp_path / "KnowRealm"
        if blocked == "consent":
            path = data_dir / "config" / "settings.json"
            settings = json.loads(path.read_text(encoding="utf-8"))
            settings.pop("llm_external_processing_consent", None)
            path.write_text(json.dumps(settings), encoding="utf-8")
        else:
            save_llm_provider(
                data_dir,
                base_url="http://127.0.0.1:1/v1",
                api_key="test-key",
                model="test-model",
                clear_api_key=blocked == "provider",
                model_budget=ModelBudgetConfig(input_limit=10),
                replace_model_budget=True,
            )
            grant_llm_consent(data_dir)
        await start(client, 1)
        result = await terminal(client)
        assert result["status"] == "FAILED"
        assert (
            result["error_code"]
            == {
                "consent": "AI_CONSENT_REQUIRED",
                "budget": "MODEL_INPUT_BUDGET_EXCEEDED",
                "provider": "LLM_PROVIDER_UNCONFIGURED",
            }[blocked]
        )
        assert result["outcome"] == "INCOMPLETE"
        assert (await client.get(BASE)).json()["requirements"]["revision"] == 1
        assert model.calls == 0


@pytest.mark.anyio
@pytest.mark.parametrize("auth_mode", list(AuthMode))
async def test_mounted_agent_requires_business_confirmation_in_all_auth_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, auth_mode: AuthMode
) -> None:
    async with plan_app(tmp_path) as (client, factory):
        await seed(factory)
        configure(tmp_path, monkeypatch)
        await add_questions(factory, RECORD_ID, 15)
        chat = (await client.post("/api/chat-sessions", json={})).json()["id"]
        tools = {
            tool.name: tool
            for tool in resolve_agent_config(retrieval=False, web_search_enabled=False).tools
        }
        runtime = AgentRuntimeContext(session_factory=factory, session_id=chat, auth_mode=auth_mode)
        token = bind_agent_runtime_context(runtime)
        try:
            current = (await client.get(BASE)).json()
            payload = requirements(
                source_versions={
                    source["record_id"]: source["version"] for source in current["sources"]
                }
            )
            result = json.loads(
                await tools["confirm_practice_requirements"].ainvoke(
                    {"item_id": ITEM_ID, **payload}
                )
            )
            assert result["ok"] is True, result
            assert "executed" not in result
            assert (await client.get(BASE)).json()["requirements"] is None
            proposal_id = result["proposals"][0]["proposal_id"]
            response = await client.post(f"/api/proposals/{proposal_id}/confirm")
            assert response.status_code == 200, response.text
            prepared = json.loads(
                await tools["prepare_plan_practice"].ainvoke(
                    {"item_id": ITEM_ID, "request_id": str(uuid4()), "requirements_revision": 1}
                )
            )
            if auth_mode == AuthMode.REQUEST_APPROVAL:
                response = await client.post(
                    f"/api/proposals/{prepared['proposals'][0]['proposal_id']}/confirm"
                )
                assert response.status_code == 200, response.text
            assert (await terminal(client))["selected_count"] == 15
            state = json.loads(await tools["get_plan_practice"].ainvoke({"item_id": ITEM_ID}))
            assert state["practice"]["preparations"][0]["selected_count"] == 15
            assert "秘密" not in json.dumps(state, ensure_ascii=False)
        finally:
            reset_agent_runtime_context(token)


@pytest.mark.anyio
async def test_agent_downgrade_blocks_late_matching_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with plan_app(tmp_path) as (client, factory):
        await seed(factory)
        model = configure(tmp_path, monkeypatch)
        model.mode = "wait"
        await add_questions(factory, RECORD_ID, 15)
        await save(client, [RECORD_ID])
        chat = (await client.post("/api/chat-sessions", json={})).json()["id"]
        tools = {
            tool.name: tool
            for tool in resolve_agent_config(retrieval=False, web_search_enabled=False).tools
        }
        token = bind_agent_runtime_context(
            AgentRuntimeContext(
                session_factory=factory, session_id=chat, auth_mode=AuthMode.AUTO_APPROVE
            )
        )
        try:
            result = json.loads(
                await tools["prepare_plan_practice"].ainvoke(
                    {"item_id": ITEM_ID, "request_id": str(uuid4()), "requirements_revision": 1}
                )
            )
            assert result["ok"] is True, result
            await asyncio.wait_for(model.started.wait(), 5)
            set_session_auth_override(chat, AuthMode.REQUEST_APPROVAL)
            model.release.set()
            final = await terminal(client)
            assert final["status"] == "FAILED"
            assert final["error_code"] == "OPERATION_APPROVAL_REQUIRED"
            assert final["selected_count"] == 0
        finally:
            clear_session_auth_override(chat)
            reset_agent_runtime_context(token)


@pytest.mark.anyio
async def test_call_budget_is_incomplete_not_course_shortage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with plan_app(tmp_path) as (client, factory):
        await seed(factory)
        model = configure(tmp_path, monkeypatch)
        await add_questions(factory, RECORD_ID, 601)
        await save(client, [RECORD_ID], question_count=601)
        await start(client, 1)
        result = await terminal(client)
        assert result["outcome"] == "INCOMPLETE"
        assert (result["examined_count"], result["total_candidates"], result["related_count"]) == (
            600,
            601,
            600,
        )
        assert result["course_scan_complete"] is False
        assert result["selected_count"] == 0
        assert model.calls == 20


@pytest.mark.anyio
async def test_restart_reconciles_interrupted_job_without_rebilling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with plan_app(tmp_path) as (client, factory):
        await seed(factory)
        model = configure(tmp_path, monkeypatch)
        await add_questions(factory, RECORD_ID, 15)
        await save(client, [RECORD_ID])
        await start(client, 1)
        assert (await terminal(client))["selected_count"] == 15
    # 模拟进程退出时留有已领取但无法确认外发结局的持久任务。
    import aiosqlite

    async with aiosqlite.connect(tmp_path / "KnowRealm" / "knowrealm.db") as connection:
        await connection.execute(
            "UPDATE processing_jobs SET status='RUNNING', result_json=NULL "
            "WHERE job_type='PRACTICE_PREPARE'"
        )
        await connection.execute("UPDATE practice_preparations SET result_json=NULL")
        await connection.commit()
    async with plan_app(tmp_path) as (client, _factory):
        state = (await client.get(BASE)).json()
        assert state["requirements"]["revision"] == 1
        assert state["preparations"][0]["status"] == "FAILED"
        assert state["preparations"][0]["error_code"] == "WORKER_INTERRUPTED"
        assert model.calls == 1
        await start(client, 1)
        assert (await terminal(client))["selected_count"] == 15


@pytest.mark.anyio
async def test_sources_and_candidate_lifecycle_and_old_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with plan_app(tmp_path) as (client, factory):
        await seed(factory)
        model = configure(tmp_path, monkeypatch)
        other_course = (
            await client.post(
                "/api/courses",
                json={"name": "其他课程", "learning_context": "INTEREST", "depth": "BEGINNER"},
            )
        ).json()["id"]
        other_record = await add_record(factory, other_course)
        from app.modules.library.models import CourseSharedRef, LibraryItem, LibraryItemRecord

        async with factory() as session, session.begin():
            shared = LibraryItem(
                course_id=other_course,
                source_type="DOCUMENT",
                title="仅共享引用",
                content_hash="shared-practice-test",
            )
            session.add(shared)
            await session.flush()
            session.add(LibraryItemRecord(library_item_id=shared.id, record_id=other_record))
            session.add(CourseSharedRef(course_id=COURSE_ID, library_item_id=shared.id))
        await add_questions(factory, other_record, 15, prefix="其他课程")
        await add_questions(factory, RECORD_ID, 8)
        await add_questions(factory, RECORD_ID, 1, prefix="已删除")
        await run_sql(
            "UPDATE quizzes SET deleted_at=:now WHERE stem LIKE '已删除%'",
            {"now": "2026-10-17T00:00:00Z"},
            factory,
        )
        state = (await client.get(BASE)).json()
        assert other_record not in [source["record_id"] for source in state["sources"]]
        invalid = requirements(record_ids=[other_record], source_versions={other_record: "invalid"})
        assert (await client.put(BASE + "/requirements", json=invalid)).status_code == 409
        stale = requirements(
            source_versions={source["record_id"]: source["version"] for source in state["sources"]}
        )
        await add_questions(factory, RECORD_ID, 1, start=9)
        assert (await client.put(BASE + "/requirements", json=stale)).json()[
            "code"
        ] == "PRACTICE_SOURCE_INVALID"
        await save(client, [RECORD_ID])
        await start(client, 1)
        final = await terminal(client)
        assert final["related_count"] == 9
        assert all(
            candidate["title"] != "其他课程"
            and not candidate["stem"].startswith(("其他课程", "已删除"))
            for prompt in model.prompts
            for candidate in prompt["candidates"]
        )
        async with factory() as session:
            from app.modules.record.models import LearningEvent

            assert await session.scalar(select(func.count()).select_from(LearningEvent)) == 0
