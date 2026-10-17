"""计划练习轮次：真实 HTTP、迁移 SQLite、生产 Worker；仅替换外部推理。"""

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.db.migrations import run_migrations
from app.modules.agent.graph import resolve_agent_config
from app.modules.agent.runs.schemas import AuthMode
from app.modules.agent.runtime import (
    AgentRuntimeContext,
    bind_agent_runtime_context,
    reset_agent_runtime_context,
)
from app.modules.llm import service as llm_service
from app.modules.quiz.models import QuizTest, QuizTestItem
from app.modules.record.models import LearningEvent
from tests.test_plan_editing import (
    COURSE_ID,
    ITEM_ID,
    PLAN_ID,
    RECORD_ID,
    TOKEN,
    run_sql,
)
from tests.test_practice_preparation import (
    BASE,
    add_questions,
    configure,
    save,
    seed,
    start,
    terminal,
)

COMPLETE = f"/api/courses/{COURSE_ID}/plans/{PLAN_ID}/items/{ITEM_ID}/complete"


class GradingModel:
    """顺序吐 CORRECT/PARTIAL；可暂停以制造 GRADING 在途窗口。"""

    def __init__(self, count: int) -> None:
        self.remaining = count
        self.calls = 0
        self.prompts: list[str] = []
        self.pause = False
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def generate(self, **kwargs: Any) -> llm_service.StructuredModelResult:
        self.calls += 1
        self.prompts.append(kwargs["prompt"])
        self.started.set()
        if self.pause:
            await self.release.wait()
        self.remaining -= 1
        return llm_service.StructuredModelResult(
            output={
                "verdict": "PARTIAL",
                "score": 0.5,
                "confidence": 0.9,
                "rationale": "覆盖一半要点",
            },
            token_usage={"total_tokens": 31},
        )


@asynccontextmanager
async def practice_app(tmp_path: Path, model: GradingModel):
    from app.main import create_app

    app: FastAPI = create_app(
        data_dir=tmp_path / "KnowRealm", launch_token=TOKEN, quiz_grading_model=model
    )
    async with app.router.lifespan_context(app):
        await app.state.course_tombstone_cleanup_task
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield client, app.state.session_factory


async def begin(client: Any, revision: int, request_id: str | None = None) -> Any:
    response = await client.post(
        BASE + "/rounds",
        json={
            "request_id": request_id or str(uuid4()),
            "requirements_revision": revision,
        },
    )
    return response


async def ready_fifteen(
    client: Any, factory: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    configure(tmp_path, monkeypatch)
    await add_questions(factory, RECORD_ID, 15)
    await add_questions(factory, RECORD_ID, 1, prefix="Docker")
    await save(client, [RECORD_ID])
    await start(client, 1)
    result = await terminal(client)
    assert result["outcome"] == "READY", result
    return result


async def answer_all(client: Any, paper: dict[str, Any], upto: int | None = None) -> None:
    for item in paper["items"][:upto]:
        response = await client.post(
            f"/api/quiz-tests/{paper['id']}/answers",
            json={"item_id": item["id"], "answer": "我的简答作答"},
        )
        assert response.status_code == 200, response.text


async def wait_status(client: Any, test_id: str, statuses: tuple[str, ...]) -> dict[str, Any]:
    for _ in range(160):
        detail = (await client.get(f"/api/quiz-tests/{test_id}")).json()
        if detail["status"] in statuses:
            return detail
        await asyncio.sleep(0.05)
    pytest.fail(f"grading did not reach {statuses}")


@pytest.mark.anyio
async def test_round_freezes_fifteen_without_leaking_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = GradingModel(0)
    async with practice_app(tmp_path, model) as (client, factory):
        await seed(factory)
        await ready_fifteen(client, factory, tmp_path, monkeypatch)
        request_id2 = str(uuid4())
        created = await begin(client, 1, request_id2)
        assert created.status_code == 200, created.text
        round_ = created.json()
        assert (round_["round_no"], round_["status"], round_["total_count"]) == (
            1,
            "IN_PROGRESS",
            15,
        )
        assert round_["requirements_revision"] == 1
        assert round_["paper_path"] == f"/spaces/{COURSE_ID}/tests/{round_['test_id']}"
        paper = (await client.get(f"/api/quiz-tests/{round_['test_id']}")).json()
        assert paper["mode"] == "PLAN"
        assert paper["plan_item_id"] == ITEM_ID
        assert len(paper["items"]) == 15
        assert all(item["quiz_id"] for item in paper["items"])
        assert all(item["source_valid"] is True for item in paper["items"])
        serialized = json.dumps(paper, ensure_ascii=False)
        assert "秘密" not in serialized  # 作答期不揭示参考答案与解析
        state = (await client.get(BASE)).json()
        assert state["round"]["test_id"] == round_["test_id"]
        assert "秘密" not in json.dumps(state, ensure_ascii=False)
        # 同请求身份改变参数：拒绝执行，不返回旧轮。
        replay_changed = await begin(client, 99, request_id2)
        assert replay_changed.status_code == 409
        assert replay_changed.json()["code"] == "PRACTICE_REQUEST_CONFLICT"
        # 普通模拟测试列表不混入计划练习轮次。
        listing = (await client.get(f"/api/courses/{COURSE_ID}/quiz-tests")).json()
        assert listing["items"] == []
        async with factory() as session:
            rows = list(await session.scalars(select(QuizTestItem)))
            assert len(rows) == 15
            frozen = [json.loads(row.frozen_json or "null") for row in rows]
            assert all(face and face["correct_answer"] for face in frozen)
            assert {face["record_title"] for face in frozen} == {"第 1 讲 Agent 概论"}
            # 建卷本身是确定性事实，不制造学习证据。
            assert await session.scalar(select(func.count()).select_from(LearningEvent)) == 0


@pytest.mark.anyio
async def test_round_same_across_replay_restart_and_grading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with practice_app(tmp_path, GradingModel(0)) as (client, factory):
        await seed(factory)
        await ready_fifteen(client, factory, tmp_path, monkeypatch)
        request_id = str(uuid4())
        created = (await begin(client, 1, request_id)).json()
        test_id = created["test_id"]
        # 重放同一请求：返回同一轮。
        replay = await begin(client, 1, request_id)
        assert replay.status_code == 200
        assert replay.json()["test_id"] == test_id
        paper = (await client.get(f"/api/quiz-tests/{test_id}")).json()
        await answer_all(client, paper, upto=6)
    # 应用重启后继续同一轮，普通开始不建新轮。
    async with practice_app(tmp_path, GradingModel(15)) as (client, factory):
        state = (await client.get(BASE)).json()
        assert state["round"]["test_id"] == test_id
        assert state["round"]["answered_count"] == 6
        again = await begin(client, 1)
        assert again.status_code == 200
        assert again.json()["test_id"] == test_id
        paper = (await client.get(f"/api/quiz-tests/{test_id}")).json()
        await answer_all(client, paper)
        submit = await client.post(f"/api/quiz-tests/{test_id}/submit")
        assert submit.status_code == 200
        assert submit.json()["status"] == "GRADING"
        # 评分在途：普通开始返回该轮状态，不自动创建下一轮。
        during = await begin(client, 1)
        assert during.status_code == 200
        assert (during.json()["test_id"], during.json()["status"]) == (test_id, "GRADING")
        done = await wait_status(client, test_id, ("COMPLETED", "GRADING_FAILED"))
        assert done["status"] == "COMPLETED"
        assert done["score"] == 0.5
        round_ = (await client.get(BASE)).json()["round"]
        assert round_["answered_count"] == 15
        assert round_["graded_count"] == 15
        assert round_["unscored_count"] == 0
        assert round_["score_denominator"] == 15
        assert round_["grading_complete"] is True
        async with factory() as session:
            events = list(await session.scalars(select(LearningEvent)))
            answered = [e for e in events if e.event_type == "QUIZ_ANSWERED"]
            completed = [e for e in events if e.event_type == "QUIZ_TEST_COMPLETED"]
            assert len(answered) == 15
            assert len(completed) == 1
        duplicate_submit = await client.post(f"/api/quiz-tests/{test_id}/submit")
        assert duplicate_submit.status_code == 409


@pytest.mark.anyio
async def test_frozen_paper_survives_source_change_and_invalidation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = GradingModel(15)
    async with practice_app(tmp_path, model) as (client, factory):
        await seed(factory)
        await ready_fifteen(client, factory, tmp_path, monkeypatch)
        test_id = (await begin(client, 1)).json()["test_id"]
        paper = (await client.get(f"/api/quiz-tests/{test_id}")).json()
        original_stems = [item["stem"] for item in paper["items"]]
        await answer_all(client, paper, upto=6)
        # 原题修改 + 来源移出课程：当前轮固定题面，来源标注失效。
        await run_sql(
            "UPDATE quizzes SET stem = stem || ' 已改写' WHERE record_id = :id",
            {"id": RECORD_ID},
            factory,
        )
        await run_sql(
            "INSERT INTO courses (id, name, learning_context, depth, status, created_at,"
            " updated_at) VALUES ('99999999-9999-4999-8999-999999999999', '其他课程',"
            " 'INTEREST', 'INTERMEDIATE', 'ACTIVE', '2026-10-17T00:00:00Z',"
            " '2026-10-17T00:00:00Z')",
            {},
            factory,
        )
        await run_sql(
            "UPDATE records SET course_id = '99999999-9999-4999-8999-999999999999' WHERE id = :id",
            {"id": RECORD_ID},
            factory,
        )
        moved = (await client.get(f"/api/quiz-tests/{test_id}")).json()
        assert [item["stem"] for item in moved["items"]] == original_stems
        assert all(item["source_valid"] is False for item in moved["items"])
        # 来源再软删：同样失效，作答与评分继续。
        await run_sql(
            "UPDATE records SET deleted_at = '2026-10-18T00:00:00Z' WHERE id = :id",
            {"id": RECORD_ID},
            factory,
        )
        unchanged = (await client.get(f"/api/quiz-tests/{test_id}")).json()
        assert [item["stem"] for item in unchanged["items"]] == original_stems
        assert all(item["source_valid"] is False for item in unchanged["items"])
        round_ = (await client.get(BASE)).json()["round"]
        assert [source["valid"] for source in round_["sources"]] == [False]
        await answer_all(client, unchanged)
        submit = await client.post(f"/api/quiz-tests/{test_id}/submit")
        assert submit.status_code == 200
        done = await wait_status(client, test_id, ("COMPLETED", "GRADING_FAILED"))
        assert done["status"] == "COMPLETED"
        async with factory() as session:
            answer_events = await session.scalar(
                select(func.count())
                .select_from(LearningEvent)
                .where(LearningEvent.event_type == "QUIZ_ANSWERED")
            )
            assert answer_events == 15


@pytest.mark.anyio
async def test_new_round_rejects_invalidated_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with practice_app(tmp_path, GradingModel(0)) as (client, factory):
        await seed(factory)
        await ready_fifteen(client, factory, tmp_path, monkeypatch)
        await run_sql(
            "UPDATE records SET deleted_at = '2026-10-18T00:00:00Z' WHERE id = :id",
            {"id": RECORD_ID},
            factory,
        )
        rejected = await begin(client, 1)
        assert rejected.status_code == 409
        assert rejected.json()["code"] == "PRACTICE_SOURCE_INVALID"
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(QuizTest)) == 0


@pytest.mark.anyio
async def test_record_purge_not_blocked_by_practice_references(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = GradingModel(15)
    async with practice_app(tmp_path, model) as (client, factory):
        await seed(factory)
        await ready_fifteen(client, factory, tmp_path, monkeypatch)
        test_id = (await begin(client, 1)).json()["test_id"]
        paper = (await client.get(f"/api/quiz-tests/{test_id}")).json()
        await answer_all(client, paper, upto=3)
        # 来源资料物理删除：原题身份置空，不再阻塞清理；轮次题面与评分不受影响。
        await run_sql("DELETE FROM quizzes WHERE record_id = :id", {"id": RECORD_ID}, factory)
        await run_sql("DELETE FROM records WHERE id = :id", {"id": RECORD_ID}, factory)
        async with factory() as session:
            rows = list(await session.scalars(select(QuizTestItem)))
            assert all(row.quiz_id is None for row in rows)
        survived = (await client.get(f"/api/quiz-tests/{test_id}")).json()
        assert len(survived["items"]) == 15
        assert all(item["source_valid"] is False for item in survived["items"])
        await answer_all(client, survived)
        submit = await client.post(f"/api/quiz-tests/{test_id}/submit")
        assert submit.status_code == 200
        done = await wait_status(client, test_id, ("COMPLETED", "GRADING_FAILED"))
        assert done["status"] == "COMPLETED"


async def add_true_false(factory: Any, record_id: str, count: int) -> None:
    from app.modules.quiz.models import Quiz

    async with factory() as session, session.begin():
        for index in range(count):
            session.add(
                Quiz(
                    record_id=record_id,
                    generation_status="ACTIVE",
                    question_type="TRUE_FALSE",
                    stem=f"Redis 判断 {index}",
                    options_json='["对", "错"]',
                    correct_answer_json="0",
                    explanation="解析",
                    difficulty="EASY",
                )
            )


@pytest.mark.anyio
async def test_manual_completion_keeps_first_timestamp_after_objective_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with practice_app(tmp_path, GradingModel(0)) as (client, factory):
        await seed(factory)
        configure(tmp_path, monkeypatch)
        await add_true_false(factory, RECORD_ID, 15)
        await save(client, [RECORD_ID], question_types=["TRUE_FALSE"])
        await start(client, 1)
        result = await terminal(client)
        assert result["outcome"] == "READY", result
        test_id = (await begin(client, 1)).json()["test_id"]
        paper = (await client.get(f"/api/quiz-tests/{test_id}")).json()
        for item in paper["items"]:
            answer = await client.post(
                f"/api/quiz-tests/{test_id}/answers",
                json={"item_id": item["id"], "answer": 0},
            )
            assert answer.status_code == 200, answer.text
        submit = await client.post(f"/api/quiz-tests/{test_id}/submit")
        assert submit.status_code == 200
        assert submit.json()["status"] == "COMPLETED"  # 客观题同步落终态
        first = await client.post(COMPLETE)
        assert first.status_code == 200, first.text
        assert first.json()["status"] == "DONE"
        completed_at = first.json()["completed_at"]
        assert completed_at is not None
        async with factory() as session:
            events = await session.scalar(select(func.count()).select_from(LearningEvent))
        second = await client.post(COMPLETE)
        assert second.status_code == 200
        assert second.json()["completed_at"] == completed_at
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(LearningEvent)) == events


@pytest.mark.anyio
async def test_legacy_answer_entry_respects_plan_constraints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with practice_app(tmp_path, GradingModel(0)) as (client, factory):
        await seed(factory)
        await ready_fifteen(client, factory, tmp_path, monkeypatch)
        test_id = (await begin(client, 1)).json()["test_id"]
        paper = (await client.get(f"/api/quiz-tests/{test_id}")).json()
        item = paper["items"][0]
        await run_sql(
            "UPDATE learning_plans SET status = 'SUPERSEDED' WHERE id = :id",
            {"id": PLAN_ID},
            factory,
        )
        answer = await client.post(
            f"/api/quiz-tests/{test_id}/answers",
            json={"item_id": item["id"], "answer": "我的简答作答"},
        )
        assert answer.status_code == 409
        assert answer.json()["code"] == "PRACTICE_ITEM_UNAVAILABLE"
        submit = await client.post(f"/api/quiz-tests/{test_id}/submit")
        assert submit.status_code == 409
        assert submit.json()["code"] == "PRACTICE_ITEM_UNAVAILABLE"
        abandon = await client.post(f"/api/quiz-tests/{test_id}/abandon")
        assert abandon.status_code == 409
        assert abandon.json()["code"] == "PRACTICE_ROUND_OP_UNAVAILABLE"
        readable = await client.get(f"/api/quiz-tests/{test_id}")
        assert readable.status_code == 200  # 历史仍可查看既有结果


@pytest.mark.anyio
async def test_migration_0054_upgrades_existing_rows(tmp_path: Path) -> None:
    import aiosqlite

    from tests.test_agent_runs import apply_migrations_upto

    db_path = tmp_path / "old.db"
    await apply_migrations_upto(db_path, 53)
    now = "2026-10-17T00:00:00Z"
    seed_sql = f"""
    INSERT INTO courses (id, name, learning_context, depth, status, created_at, updated_at)
      VALUES ('c1', '课', 'INTEREST', 'INTERMEDIATE', 'ACTIVE', '{now}', '{now}');
    INSERT INTO records (id, course_id, capture_type, title, status, duration_ms,
      created_at, updated_at)
      VALUES ('r1', 'c1', 'DOCUMENT_IMPORT', '资料', 'SUMMARY_READY', 0, '{now}', '{now}');
    INSERT INTO quizzes (id, record_id, generation_status, question_type, stem,
      options_json, correct_answer_json, explanation, difficulty, created_at, updated_at)
      VALUES ('q1', 'r1', 'ACTIVE', 'SHORT_ANSWER', '题干', '[]', '"答案"', '解析',
      'MEDIUM', '{now}', '{now}');
    INSERT INTO quiz_tests (id, course_id, record_id, mode, status, started_at,
      created_at, updated_at)
      VALUES ('t1', 'c1', NULL, 'MOCK', 'COMPLETED', '{now}', '{now}', '{now}');
    INSERT INTO quiz_test_items (id, test_id, quiz_id, sequence_no, answered_at,
      created_at, updated_at)
      VALUES ('i1', 't1', 'q1', 1, '{now}', '{now}', '{now}');
    """
    async with aiosqlite.connect(db_path) as connection:
        await connection.executescript(seed_sql)
    await run_migrations(db_path)
    async with aiosqlite.connect(db_path) as connection:
        row = await (
            await connection.execute(
                "SELECT plan_item_id, practice_round_no, requirements_id, request_id,"
                " mode FROM quiz_tests WHERE id = 't1'"
            )
        ).fetchone()
        assert row == (None, None, None, None, "MOCK")
        item = await (
            await connection.execute(
                "SELECT quiz_id, frozen_json FROM quiz_test_items WHERE id = 'i1'"
            )
        ).fetchone()
        assert item == ("q1", None)
        # 原题身份改为弱引用：物理删除不再被旧卷面阻塞，身份就地置空。
        await connection.execute("PRAGMA foreign_keys=ON")
        await connection.execute("DELETE FROM quizzes WHERE id = 'q1'")
        await connection.commit()
        kept = await (
            await connection.execute("SELECT quiz_id FROM quiz_test_items WHERE id = 'i1'")
        ).fetchone()
        assert kept == (None,)


@pytest.mark.anyio
async def test_agent_starts_round_via_controlled_tool_without_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with practice_app(tmp_path, GradingModel(0)) as (client, factory):
        await seed(factory)
        await ready_fifteen(client, factory, tmp_path, monkeypatch)
        chat = (await client.post("/api/chat-sessions", json={})).json()["id"]
        tools = {
            tool.name: tool
            for tool in resolve_agent_config(retrieval=False, web_search_enabled=False).tools
        }
        token = bind_agent_runtime_context(
            AgentRuntimeContext(
                session_factory=factory,
                session_id=chat,
                auth_mode=AuthMode.AUTO_APPROVE,
            )
        )
        try:
            result = json.loads(
                await tools["start_plan_practice"].ainvoke(
                    {
                        "item_id": ITEM_ID,
                        "request_id": str(uuid4()),
                        "requirements_revision": 1,
                    }
                )
            )
            assert result["ok"] is True, result
            round_ = result["executed"]["result"]
            assert round_["round_no"] == 1
            assert round_["total_count"] == 15
            assert round_["paper_path"].startswith(f"/spaces/{COURSE_ID}/tests/")
            assert "秘密" not in json.dumps(result, ensure_ascii=False)
            state = json.loads(await tools["get_plan_practice"].ainvoke({"item_id": ITEM_ID}))
            assert state["practice"]["round"]["test_id"] == round_["test_id"]
            assert "stem" not in json.dumps(state, ensure_ascii=False)
        finally:
            reset_agent_runtime_context(token)


@pytest.mark.anyio
async def test_concurrent_second_start_returns_same_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.learning_plan import practice_round as round_module

    async with practice_app(tmp_path, GradingModel(0)) as (client, factory):
        await seed(factory)
        await ready_fifteen(client, factory, tmp_path, monkeypatch)
        first = (await begin(client, 1)).json()

        original = round_module.start_round

        async def lose_race(session: Any, item_id: str, payload: Any) -> Any:
            del session, item_id, payload
            raise round_module._round_conflict()

        monkeypatch.setattr(round_module, "start_round", lose_race)
        # 模拟并发败方：建卷事务被部分唯一索引拦截后重查返回同一轮。
        second = await begin(client, 1)
        assert second.status_code == 200, second.text
        assert second.json()["test_id"] == first["test_id"]
        monkeypatch.setattr(round_module, "start_round", original)
        # 无任何轮次时同错误如实透出，不凭空造轮。
        monkeypatch.setattr(round_module, "start_round", lose_race)
        orphan = await client.post(
            f"/api/plan-items/{str(uuid4())}/practice/rounds",
            json={"request_id": str(uuid4()), "requirements_revision": 1},
        )
        assert orphan.status_code in (404, 409)
