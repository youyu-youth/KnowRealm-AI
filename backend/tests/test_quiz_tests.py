import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.db.migrations import run_migrations
from app.main import create_app
from app.modules.llm.service import StructuredModelResult
from app.shared.prompts import CONTENT_LANGUAGE_INSTRUCTION

TOKEN = "test-launch-token"
COURSE_ID = "11111111-1111-4111-8111-111111111111"
RECORD_ID = "22222222-2222-4222-8222-222222222222"
NOW = "2026-08-31T08:00:00.000000Z"


@asynccontextmanager
async def running_app(data_dir: Path) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(data_dir=data_dir, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client


async def seed_course_quizzes(
    app: FastAPI,
    *,
    course_status: str = "ACTIVE",
    question_types: tuple[str, ...] = ("MULTIPLE_CHOICE", "TRUE_FALSE"),
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO courses "
                "(id, name, learning_context, education_stage, depth, course_type, description, "
                "hot_words, status, created_at, updated_at, deleted_at) "
                "VALUES (:id, '操作系统', 'SCHOOL', 'UNDERGRADUATE', NULL, NULL, NULL, '[]', "
                ":status, :now, :now, NULL)"
            ),
            {"id": COURSE_ID, "status": course_status, "now": NOW},
        )
        await session.execute(
            text(
                "INSERT INTO records "
                "(id, course_id, capture_type, title, status, duration_ms, summary_confirmed_at, "
                "created_at, updated_at, deleted_at) "
                "VALUES (:id, :course_id, 'QUICK_NOTE', '调度', 'COMPLETED', 0, "
                ":now, :now, :now, NULL)"
            ),
            {"id": RECORD_ID, "course_id": COURSE_ID, "now": NOW},
        )
        for index, question_type in enumerate(question_types, 1):
            options = [] if question_type in {"FILL_BLANK", "SHORT_ANSWER"} else ["甲", "乙"]
            answer: object = "参考答案" if question_type == "SHORT_ANSWER" else 0
            await session.execute(
                text(
                    "INSERT INTO quizzes "
                    "(id, record_id, batch_id, generated_from_summary_id, generation_status, "
                    "question_type, stem, options_json, correct_answer_json, explanation, "
                    "difficulty, user_answer_json, answer_result, answered_at, created_at, "
                    "updated_at, deleted_at) VALUES (:id, :record_id, NULL, NULL, 'ACTIVE', "
                    ":question_type, :stem, :options, "
                    ":answer, '解析', 'MEDIUM', NULL, NULL, NULL, :now, :now, NULL)"
                ),
                {
                    "id": f"33333333-3333-4333-8333-{index:012d}",
                    "record_id": RECORD_ID,
                    "question_type": question_type,
                    "stem": f"第 {index} 题",
                    "options": json.dumps(options, ensure_ascii=False),
                    "answer": json.dumps(answer, ensure_ascii=False),
                    "now": NOW,
                },
            )
        await session.execute(
            text(
                "INSERT INTO quizzes "
                "(id, record_id, batch_id, generated_from_summary_id, generation_status, "
                "question_type, stem, options_json, correct_answer_json, explanation, difficulty, "
                "user_answer_json, "
                "answer_result, answered_at, created_at, updated_at, deleted_at) "
                "VALUES ('44444444-4444-4444-8444-444444444444', :record_id, NULL, NULL, 'DRAFT', "
                "'MULTIPLE_CHOICE', '候选题', '[\"甲\",\"乙\"]', '0', '解析', 'EASY', NULL, NULL, "
                "NULL, :now, :now, NULL)"
            ),
            {"record_id": RECORD_ID, "now": NOW},
        )


@pytest.mark.anyio
async def test_migration_0016_creates_quiz_test_tables_and_grading_job_type(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)

    async with aiosqlite.connect(db_path) as connection:
        version = await (await connection.execute("PRAGMA user_version")).fetchone()
        tables = {
            cast(str, row[0])
            for row in await (
                await connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'quiz_test%'"
                )
            ).fetchall()
        }
        await connection.execute(
            "INSERT INTO processing_jobs "
            "(id, record_id, job_type, status, progress, attempts, max_attempts, next_run_at, "
            "input_json, result_json, error_code, error_message, started_at, finished_at, "
            "created_at, updated_at, waiting_reason) "
            "VALUES ('job', NULL, 'QUIZ_GRADING', 'PENDING', 0, 0, 3, NULL, '{}', NULL, NULL, "
            "NULL, NULL, NULL, ?, ?, NULL)",
            (NOW, NOW),
        )

    assert version is not None and version[0] == 25
    assert tables == {"quiz_tests", "quiz_test_items"}


@pytest.mark.anyio
async def test_create_list_and_detail_quiz_test_use_only_active_selected_questions(
    tmp_path: Path,
) -> None:
    async with running_app(tmp_path) as (app, client):
        await seed_course_quizzes(
            app,
            question_types=("MULTIPLE_CHOICE", "TRUE_FALSE", "TRUE_FALSE"),
        )

        created = await client.post(
            f"/api/courses/{COURSE_ID}/quiz-tests",
            json={"question_types": ["TRUE_FALSE"], "total_count": 5},
        )

        assert created.status_code == 201
        body = created.json()
        assert body["requested_count"] == 5
        assert body["selected_count"] == 2
        assert body["shortage"] is True
        assert body["test"]["record_id"] is None
        test_id = cast(str, body["test"]["id"])

        listed = await client.get(f"/api/courses/{COURSE_ID}/quiz-tests")
        assert listed.status_code == 200
        assert listed.json()["blocked_reason"] is None
        assert listed.json()["items"] == [body["test"]]

        detail = await client.get(f"/api/quiz-tests/{test_id}")
        assert detail.status_code == 200
        items = detail.json()["items"]
        assert [item["sequence_no"] for item in items] == [1, 2]
        assert {item["question_type"] for item in items} == {"TRUE_FALSE"}
        # 作答期不泄漏答案：字段存在但恒为 null（终态才揭示）
        assert all(
            item["correct_answer"] is None
            and item["explanation"] is None
            and item["ai_grade"] is None
            for item in items
        )

        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE courses SET status = 'ARCHIVED' WHERE id = :course_id"),
                {"course_id": COURSE_ID},
            )
        archived_detail = await client.get(f"/api/quiz-tests/{test_id}")
        assert archived_detail.status_code == 409
        assert archived_detail.json()["blocked_reason"] == "COURSE_ARCHIVED"


@pytest.mark.anyio
async def test_create_quiz_test_rejects_empty_bank_and_archived_course(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    async with running_app(empty_dir) as (app, client):
        await seed_course_quizzes(app, question_types=())
        listed = await client.get(f"/api/courses/{COURSE_ID}/quiz-tests")
        assert listed.json() == {"items": [], "blocked_reason": "NO_AVAILABLE_QUIZZES"}
        response = await client.post(
            f"/api/courses/{COURSE_ID}/quiz-tests",
            json={"question_types": ["MULTIPLE_CHOICE"], "total_count": 5},
        )
        assert response.status_code == 409
        assert response.json()["detail"] == "课程题库暂无可用习题"

    archived_dir = tmp_path / "archived"
    async with running_app(archived_dir) as (app, client):
        await seed_course_quizzes(app, course_status="ARCHIVED")
        listed = await client.get(f"/api/courses/{COURSE_ID}/quiz-tests")
        assert listed.status_code == 200
        assert listed.json() == {"items": [], "blocked_reason": "COURSE_ARCHIVED"}

        created = await client.post(
            f"/api/courses/{COURSE_ID}/quiz-tests",
            json={"question_types": ["MULTIPLE_CHOICE"], "total_count": 5},
        )
        assert created.status_code == 409
        assert created.json() == {
            "detail": "已归档课程不能开始模拟测试",
            "blocked_reason": "COURSE_ARCHIVED",
        }


BANK_FIXTURES: dict[str, tuple[list[str], object]] = {
    "MULTIPLE_CHOICE": (["甲", "乙", "丙"], 2),
    "MULTIPLE_SELECT": (["甲", "乙", "丙", "丁"], [0, 2]),
    "TRUE_FALSE": (["对", "错"], 0),
    "FILL_BLANK": ([], [["16"], ["1/2", "0.5"]]),
    "SHORT_ANSWER": ([], "参考答案文本"),
}

type QuizItem = dict[str, object]


async def seed_quiz_bank(
    app: FastAPI,
    specs: list[tuple[str, object]],
    *,
    course_status: str = "ACTIVE",
) -> None:
    """specs 为 (question_type, correct_answer)；选项由题型固定 fixture 给出。"""
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO courses "
                "(id, name, learning_context, education_stage, depth, course_type, description, "
                "hot_words, status, created_at, updated_at, deleted_at) "
                "VALUES (:id, '操作系统', 'SCHOOL', 'UNDERGRADUATE', NULL, NULL, NULL, '[]', "
                ":status, :now, :now, NULL)"
            ),
            {"id": COURSE_ID, "status": course_status, "now": NOW},
        )
        await session.execute(
            text(
                "INSERT INTO records "
                "(id, course_id, capture_type, title, status, duration_ms, summary_confirmed_at, "
                "created_at, updated_at, deleted_at) "
                "VALUES (:id, :course_id, 'QUICK_NOTE', '调度', 'COMPLETED', 0, "
                ":now, :now, :now, NULL)"
            ),
            {"id": RECORD_ID, "course_id": COURSE_ID, "now": NOW},
        )
        for index, (question_type, answer) in enumerate(specs, 1):
            options = BANK_FIXTURES[question_type][0]
            await session.execute(
                text(
                    "INSERT INTO quizzes "
                    "(id, record_id, batch_id, generated_from_summary_id, generation_status, "
                    "question_type, stem, options_json, correct_answer_json, explanation, "
                    "difficulty, user_answer_json, answer_result, answered_at, created_at, "
                    "updated_at, deleted_at) VALUES (:id, :record_id, NULL, NULL, 'ACTIVE', "
                    ":question_type, :stem, :options, :answer, '解析', 'MEDIUM', NULL, NULL, "
                    "NULL, :now, :now, NULL)"
                ),
                {
                    "id": f"33333333-3333-4333-8333-{index:012d}",
                    "record_id": RECORD_ID,
                    "question_type": question_type,
                    "stem": f"第 {index} 题",
                    "options": json.dumps(options, ensure_ascii=False),
                    "answer": json.dumps(answer, ensure_ascii=False),
                    "now": NOW,
                },
            )


async def create_test_from_bank(
    client: httpx.AsyncClient,
    question_types: list[str],
) -> tuple[str, list[QuizItem]]:
    response = await client.post(
        f"/api/courses/{COURSE_ID}/quiz-tests",
        json={"question_types": question_types, "total_count": 20},
    )
    assert response.status_code == 201
    test_id = cast(str, response.json()["test"]["id"])
    detail = await client.get(f"/api/quiz-tests/{test_id}")
    assert detail.status_code == 200
    items = cast(list[QuizItem], detail.json()["items"])
    return test_id, items


async def fetch_test_answer_events(app: FastAPI) -> list[dict[str, object]]:
    async with app.state.session_factory() as session:
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT idempotency_key, event_type, source_type, source_id, course_id, "
                        "record_id, concept_id, result, score FROM learning_events "
                        "WHERE idempotency_key LIKE 'quiz-answered:test:%'"
                    )
                )
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


def item_of(items: list[QuizItem], item_id: object) -> QuizItem:
    return next(item for item in items if item["id"] == item_id)


@pytest.mark.anyio
async def test_answer_objective_grades_and_emits_event_idempotently(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (app, client):
        await seed_quiz_bank(app, [("MULTIPLE_CHOICE", 2), ("TRUE_FALSE", 0)])
        test_id, items = await create_test_from_bank(client, ["MULTIPLE_CHOICE", "TRUE_FALSE"])
        mc = next(item for item in items if item["question_type"] == "MULTIPLE_CHOICE")
        tf = next(item for item in items if item["question_type"] == "TRUE_FALSE")

        wrong = await client.post(
            f"/api/quiz-tests/{test_id}/answers",
            json={"item_id": mc["id"], "answer": 0},
        )
        assert wrong.status_code == 200
        mc_row = item_of(wrong.json()["items"], mc["id"])
        assert mc_row["user_answer"] == 0
        assert mc_row["result"] == "WRONG"
        assert mc_row["score"] == 0.0
        assert mc_row["answered_at"] is not None
        assert wrong.json()["answered_count"] == 1

        right = await client.post(
            f"/api/quiz-tests/{test_id}/answers",
            json={"item_id": tf["id"], "answer": 0},
        )
        assert right.status_code == 200
        tf_row = item_of(right.json()["items"], tf["id"])
        assert tf_row["result"] == "CORRECT"
        assert tf_row["score"] == 1.0
        assert right.json()["answered_count"] == 2

        events = await fetch_test_answer_events(app)
        assert len(events) == 2
        mc_event = next(
            event
            for event in events
            if event["idempotency_key"] == f"quiz-answered:test:{mc['id']}"
        )
        assert mc_event["event_type"] == "QUIZ_ANSWERED"
        assert mc_event["source_type"] == "QUIZ_QUESTION"
        assert mc_event["source_id"] == mc["quiz_id"]
        assert mc_event["course_id"] == COURSE_ID
        assert mc_event["record_id"] is None
        assert mc_event["result"] == "WRONG"
        assert mc_event["score"] == 0.0

        # 幂等：重复提交不报错、不覆盖已答、不重复落事件
        replay = await client.post(
            f"/api/quiz-tests/{test_id}/answers",
            json={"item_id": tf["id"], "answer": 1},
        )
        assert replay.status_code == 200
        tf_replay = item_of(replay.json()["items"], tf["id"])
        assert tf_replay["user_answer"] == 0
        assert tf_replay["result"] == "CORRECT"
        assert replay.json()["answered_count"] == 2
        assert len(await fetch_test_answer_events(app)) == 2


@pytest.mark.anyio
async def test_multiple_select_full_match_and_fill_blank_partial(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (app, client):
        await seed_quiz_bank(
            app,
            [
                ("MULTIPLE_SELECT", [0, 2]),
                ("MULTIPLE_SELECT", [0, 1]),
                ("FILL_BLANK", [["16"], ["1/2", "0.5"]]),
            ],
        )
        test_id, items = await create_test_from_bank(client, ["MULTIPLE_SELECT", "FILL_BLANK"])
        ms_items = [item for item in items if item["question_type"] == "MULTIPLE_SELECT"]
        fb = next(item for item in items if item["question_type"] == "FILL_BLANK")

        # 两题正确答案不同（[0,2] 与 [0,1]）、抽题顺序随机：同样提交 [2,0]，
        # 全对的那题 CORRECT、缺选的那题 WRONG
        rows: list[QuizItem] = []
        for ms_item in ms_items:
            response = await client.post(
                f"/api/quiz-tests/{test_id}/answers",
                json={"item_id": ms_item["id"], "answer": [2, 0]},
            )
            assert response.status_code == 200
            rows.append(item_of(cast(list[QuizItem], response.json()["items"]), ms_item["id"]))
        assert {row["result"] for row in rows} == {"CORRECT", "WRONG"}
        for row in rows:
            assert row["score"] == (1.0 if row["result"] == "CORRECT" else 0.0)

        partial = await client.post(
            f"/api/quiz-tests/{test_id}/answers",
            json={"item_id": fb["id"], "answer": ["16", "2"]},
        )
        partial_row = item_of(partial.json()["items"], fb["id"])
        assert partial_row["result"] == "PARTIAL"
        assert partial_row["score"] == 0.5

        events = {event["idempotency_key"]: event for event in await fetch_test_answer_events(app)}
        assert events[f"quiz-answered:test:{fb['id']}"]["result"] == "PARTIAL"
        assert events[f"quiz-answered:test:{fb['id']}"]["score"] == 0.5


@pytest.mark.anyio
async def test_fill_blank_strips_and_short_answer_pends_without_event(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (app, client):
        await seed_quiz_bank(
            app, [("FILL_BLANK", [["16"], ["1/2", "0.5"]]), ("SHORT_ANSWER", "参考答案文本")]
        )
        test_id, items = await create_test_from_bank(client, ["FILL_BLANK", "SHORT_ANSWER"])
        fb = next(item for item in items if item["question_type"] == "FILL_BLANK")
        short = next(item for item in items if item["question_type"] == "SHORT_ANSWER")

        trimmed = await client.post(
            f"/api/quiz-tests/{test_id}/answers",
            json={"item_id": fb["id"], "answer": [" 16 ", "0.5"]},
        )
        fb_row = item_of(trimmed.json()["items"], fb["id"])
        assert fb_row["user_answer"] == ["16", "0.5"]
        assert fb_row["result"] == "CORRECT"

        short_response = await client.post(
            f"/api/quiz-tests/{test_id}/answers",
            json={"item_id": short["id"], "answer": "我的简答作答"},
        )
        assert short_response.status_code == 200
        short_row = item_of(short_response.json()["items"], short["id"])
        assert short_row["user_answer"] == "我的简答作答"
        assert short_row["result"] is None
        assert short_row["score"] is None
        assert short_row["answered_at"] is not None
        assert short_response.json()["answered_count"] == 2

        # 简答提交只锁定待评，不落 QUIZ_ANSWERED（评分成功才落，见 15 号功能评分票）；
        # 事件仅有填空客观题那一条
        events = await fetch_test_answer_events(app)
        assert [event["idempotency_key"] for event in events] == [f"quiz-answered:test:{fb['id']}"]

        blank = await client.post(
            f"/api/quiz-tests/{test_id}/answers",
            json={"item_id": short["id"], "answer": "   "},
        )
        assert blank.status_code == 422


@pytest.mark.anyio
async def test_answer_rejects_foreign_item_bad_shape_and_answered_state(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (app, client):
        await seed_quiz_bank(app, [("MULTIPLE_CHOICE", 2)])
        test_id, items = await create_test_from_bank(client, ["MULTIPLE_CHOICE"])
        mc = items[0]

        foreign = await client.post(
            f"/api/quiz-tests/{test_id}/answers",
            json={"item_id": "55555555-5555-4555-8555-555555555555", "answer": 0},
        )
        assert foreign.status_code == 404

        not_choice = await client.post(
            f"/api/quiz-tests/{test_id}/answers",
            json={"item_id": mc["id"], "answer": ["甲"]},
        )
        assert not_choice.status_code == 409
        assert not_choice.json()["detail"] == "该题需要提交一个选项"

        out_of_range = await client.post(
            f"/api/quiz-tests/{test_id}/answers",
            json={"item_id": mc["id"], "answer": 5},
        )
        assert out_of_range.status_code == 400

        answered = await client.post(
            f"/api/quiz-tests/{test_id}/answers",
            json={"item_id": mc["id"], "answer": 2},
        )
        assert answered.status_code == 200

        abandoned = await client.post(f"/api/quiz-tests/{test_id}/abandon")
        assert abandoned.status_code == 200
        assert abandoned.json()["status"] == "ABANDONED"

        after = await client.post(
            f"/api/quiz-tests/{test_id}/answers",
            json={"item_id": mc["id"], "answer": 0},
        )
        assert after.status_code == 409


@pytest.mark.anyio
async def test_abandon_preserves_answers_and_lands_no_events(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (app, client):
        await seed_quiz_bank(app, [("MULTIPLE_CHOICE", 2), ("SHORT_ANSWER", "参考答案文本")])
        test_id, items = await create_test_from_bank(client, ["MULTIPLE_CHOICE", "SHORT_ANSWER"])
        mc = next(item for item in items if item["question_type"] == "MULTIPLE_CHOICE")

        answered = await client.post(
            f"/api/quiz-tests/{test_id}/answers",
            json={"item_id": mc["id"], "answer": 2},
        )
        assert answered.status_code == 200

        abandoned = await client.post(f"/api/quiz-tests/{test_id}/abandon")
        assert abandoned.status_code == 200
        assert abandoned.json()["status"] == "ABANDONED"
        assert abandoned.json()["answered_count"] == 1

        # 放弃本身不落任何事件：事件仍只有先前客观题作答那一条；已答内容保留不清理
        events = await fetch_test_answer_events(app)
        assert [event["idempotency_key"] for event in events] == [f"quiz-answered:test:{mc['id']}"]

        again = await client.post(f"/api/quiz-tests/{test_id}/abandon")
        assert again.status_code == 409

        listed = await client.get(f"/api/courses/{COURSE_ID}/quiz-tests")
        assert listed.json()["items"][0]["status"] == "ABANDONED"


@pytest.mark.anyio
async def test_answering_never_touches_quizzes_answer_columns(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (app, client):
        await seed_quiz_bank(app, [("MULTIPLE_CHOICE", 2), ("SHORT_ANSWER", "参考答案文本")])
        test_id, items = await create_test_from_bank(client, ["MULTIPLE_CHOICE", "SHORT_ANSWER"])

        for item in items:
            answer: object = "我的作答" if item["question_type"] == "SHORT_ANSWER" else 2
            response = await client.post(
                f"/api/quiz-tests/{test_id}/answers",
                json={"item_id": item["id"], "answer": answer},
            )
            assert response.status_code == 200

        async with app.state.session_factory() as session:
            rows = (
                await session.execute(
                    text("SELECT user_answer_json, answer_result, answered_at FROM quizzes")
                )
            ).all()
        assert rows and all(row == (None, None, None) for row in rows)


@pytest.mark.anyio
async def test_archived_course_blocks_answer_and_abandon(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (app, client):
        await seed_quiz_bank(app, [("MULTIPLE_CHOICE", 2)])
        test_id, items = await create_test_from_bank(client, ["MULTIPLE_CHOICE"])

        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE courses SET status = 'ARCHIVED' WHERE id = :course_id"),
                {"course_id": COURSE_ID},
            )

        answer = await client.post(
            f"/api/quiz-tests/{test_id}/answers",
            json={"item_id": items[0]["id"], "answer": 2},
        )
        assert answer.status_code == 409
        assert answer.json()["detail"] == "已归档课程的模拟测试不能再作答"

        abandon = await client.post(f"/api/quiz-tests/{test_id}/abandon")
        assert abandon.status_code == 409
        assert abandon.json()["detail"] == "已归档课程的模拟测试不能再放弃"


@pytest.mark.anyio
async def test_resume_after_interrupt_keeps_answers_without_duplicate_events(
    tmp_path: Path,
) -> None:
    async with running_app(tmp_path) as (app, client):
        await seed_quiz_bank(app, [("MULTIPLE_CHOICE", 2), ("TRUE_FALSE", 0)])
        test_id, items = await create_test_from_bank(client, ["MULTIPLE_CHOICE", "TRUE_FALSE"])
        mc = next(item for item in items if item["question_type"] == "MULTIPLE_CHOICE")
        tf = next(item for item in items if item["question_type"] == "TRUE_FALSE")

        first = await client.post(
            f"/api/quiz-tests/{test_id}/answers",
            json={"item_id": mc["id"], "answer": 2},
        )
        assert first.status_code == 200

        # 中断后重进：重新读取详情，已答状态与判分仍在
        resumed = await client.get(f"/api/quiz-tests/{test_id}")
        mc_row = item_of(resumed.json()["items"], mc["id"])
        assert mc_row["result"] == "CORRECT"
        assert resumed.json()["answered_count"] == 1

        replay = await client.post(
            f"/api/quiz-tests/{test_id}/answers",
            json={"item_id": mc["id"], "answer": 2},
        )
        assert replay.status_code == 200
        assert replay.json()["answered_count"] == 1

        continue_second = await client.post(
            f"/api/quiz-tests/{test_id}/answers",
            json={"item_id": tf["id"], "answer": 0},
        )
        assert continue_second.json()["answered_count"] == 2
        assert len(await fetch_test_answer_events(app)) == 2


# ---------- 04 交卷评分链路（简答 AI 评分 / 失败语义 / 事件 / 重评） ----------


class FakeGradingModel:
    """逐题顺序吐出预置输出；输出不合规由 pydantic 校验转为 LLM_OUTPUT_INVALID。"""

    def __init__(self, outputs: list[object]) -> None:
        self.outputs = list(outputs)
        self.prompts: list[str] = []

    async def generate(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
    ) -> StructuredModelResult:
        assert base_url == "https://example.com/v1"
        assert api_key == "sk-test"
        assert model == "qwen-plus"
        self.prompts.append(prompt)
        return StructuredModelResult(output=self.outputs.pop(0), token_usage={"total_tokens": 31})


@asynccontextmanager
async def running_grading_app(
    data_dir: Path,
    model: FakeGradingModel,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(data_dir=data_dir, launch_token=TOKEN, quiz_grading_model=model)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client


async def configure_llm_provider(client: httpx.AsyncClient) -> None:
    provider = await client.put(
        "/api/settings/providers/llm",
        json={
            "base_url": "https://example.com/v1",
            "api_key": "sk-test",
            "model": "qwen-plus",
        },
    )
    assert provider.status_code == 200
    consent = await client.post("/api/settings/external-processing-consents/llm")
    assert consent.status_code == 200


async def answer_all(client: httpx.AsyncClient, test_id: str, items: list[QuizItem]) -> None:
    for item in items:
        answer: object = "我的简答作答"
        if item["question_type"] == "FILL_BLANK":
            answer = ["16", "0.5"]
        elif item["question_type"] != "SHORT_ANSWER":
            answer = 2 if item["question_type"] == "MULTIPLE_CHOICE" else 0
        response = await client.post(
            f"/api/quiz-tests/{test_id}/answers",
            json={"item_id": item["id"], "answer": answer},
        )
        assert response.status_code == 200


async def wait_for_test_status(
    client: httpx.AsyncClient,
    test_id: str,
    status: str,
) -> dict[str, object]:
    for _ in range(200):
        detail = await client.get(f"/api/quiz-tests/{test_id}")
        assert detail.status_code == 200
        if detail.json()["status"] == status:
            return cast(dict[str, object], detail.json())
        await asyncio.sleep(0.02)
    pytest.fail(f"测试状态未进入 {status}")


async def fetch_learning_events(app: FastAPI, key_pattern: str) -> list[dict[str, object]]:
    async with app.state.session_factory() as session:
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT idempotency_key, event_type, source_type, source_id, "
                        "result, score, duration_ms, metadata_json, occurred_at "
                        "FROM learning_events "
                        "WHERE idempotency_key LIKE :pattern"
                    ),
                    {"pattern": key_pattern},
                )
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


def ai_grade_of(item: QuizItem) -> dict[str, object]:
    return cast(dict[str, object], item["ai_grade"])


@pytest.mark.anyio
async def test_submit_requires_all_answers_and_objective_only_completes_synchronously(
    tmp_path: Path,
) -> None:
    async with running_app(tmp_path) as (app, client):
        await seed_quiz_bank(app, [("MULTIPLE_CHOICE", 2), ("TRUE_FALSE", 0)])
        test_id, items = await create_test_from_bank(client, ["MULTIPLE_CHOICE", "TRUE_FALSE"])
        mc = next(item for item in items if item["question_type"] == "MULTIPLE_CHOICE")
        tf = next(item for item in items if item["question_type"] == "TRUE_FALSE")

        unanswered = await client.post(f"/api/quiz-tests/{test_id}/submit")
        assert unanswered.status_code == 409
        assert unanswered.json()["detail"] == "还有题目未作答，全部作答后方可交卷"

        # MC 答对（correct=2）、判断答错（correct=0 提交 1）
        for item, answer in ((mc, 2), (tf, 1)):
            response = await client.post(
                f"/api/quiz-tests/{test_id}/answers",
                json={"item_id": item["id"], "answer": answer},
            )
            assert response.status_code == 200

        submitted = await client.post(f"/api/quiz-tests/{test_id}/submit")
        assert submitted.status_code == 200
        body = cast(dict[str, object], submitted.json())
        # 无简答题：同步判分直达 COMPLETED，score=已计分题等权平均（0.5）
        assert body["status"] == "COMPLETED"
        assert body["score"] == 0.5
        assert body["completed_at"] is not None

        # 终态揭示正确答案与解析；重复交卷 409
        mc_row = item_of(cast(list[QuizItem], body["items"]), mc["id"])
        assert mc_row["correct_answer"] == 2
        assert mc_row["explanation"] == "解析"
        again = await client.post(f"/api/quiz-tests/{test_id}/submit")
        assert again.status_code == 409

        events = await fetch_learning_events(app, "quiz-test-completed:%")
        assert len(events) == 1
        completed = events[0]
        assert completed["event_type"] == "QUIZ_TEST_COMPLETED"
        assert completed["source_type"] == "QUIZ_TEST"
        assert completed["source_id"] == test_id
        assert completed["score"] == 0.5
        assert cast(int, completed["duration_ms"]) >= 0
        # occurred_at=完成时刻（同步判分：与交卷响应的 completed_at 同值）。
        assert completed["occurred_at"] == body["completed_at"]
        metadata = json.loads(cast(str, completed["metadata_json"]))
        assert metadata["question_count"] == 2
        assert metadata["unscored_count"] == 0
        assert metadata["question_types"] == {"MULTIPLE_CHOICE": 1, "TRUE_FALSE": 1}

        async with app.state.session_factory() as session:
            jobs = cast(
                int,
                await session.scalar(text("SELECT count(*) FROM processing_jobs")),
            )
        assert jobs == 0


@pytest.mark.anyio
async def test_short_answer_grading_job_completes_test_with_events_and_telemetry(
    tmp_path: Path,
) -> None:
    model = FakeGradingModel(
        [
            {
                "verdict": "PARTIAL",
                "score": 0.6,
                "confidence": 0.9,
                "rationale": "覆盖了部分核心要点。",
            }
        ]
    )
    async with running_grading_app(tmp_path, model) as (app, client):
        await seed_quiz_bank(app, [("MULTIPLE_CHOICE", 2), ("SHORT_ANSWER", "参考答案文本")])
        test_id, items = await create_test_from_bank(client, ["MULTIPLE_CHOICE", "SHORT_ANSWER"])
        mc = next(item for item in items if item["question_type"] == "MULTIPLE_CHOICE")
        short = next(item for item in items if item["question_type"] == "SHORT_ANSWER")

        right = await client.post(
            f"/api/quiz-tests/{test_id}/answers",
            json={"item_id": mc["id"], "answer": 2},
        )
        assert right.status_code == 200
        short_answered = await client.post(
            f"/api/quiz-tests/{test_id}/answers",
            json={"item_id": short["id"], "answer": "我的简答作答"},
        )
        assert short_answered.status_code == 200

        # 未配置供应商：交卷被 409 拦截
        unconfigured = await client.post(f"/api/quiz-tests/{test_id}/submit")
        assert unconfigured.status_code == 409
        assert unconfigured.json()["detail"] == "请先配置 LLM Provider"
        await configure_llm_provider(client)

        submitted = await client.post(f"/api/quiz-tests/{test_id}/submit")
        assert submitted.status_code == 200
        assert submitted.json()["status"] == "GRADING"
        grading_item = item_of(cast(list[QuizItem], submitted.json()["items"]), short["id"])
        # 评分中不揭示正确答案
        assert grading_item["correct_answer"] is None

        completed = await wait_for_test_status(client, test_id, "COMPLETED")
        assert completed["score"] == 0.8  # (1.0 + 0.6) / 2

        short_row = item_of(cast(list[QuizItem], completed["items"]), short["id"])
        assert short_row["result"] == "PARTIAL"
        assert short_row["score"] == 0.6
        assert short_row["correct_answer"] == "参考答案文本"
        ai_grade = ai_grade_of(short_row)
        assert ai_grade["verdict"] == "PARTIAL"
        assert ai_grade["confidence"] == 0.9
        assert ai_grade["rationale"] == "覆盖了部分核心要点。"
        assert ai_grade["needs_review"] is False

        # 简答评分成功才落 QUIZ_ANSWERED；整卷完成事件同事务落
        answered = await fetch_learning_events(app, "quiz-answered:test:%")
        assert {event["idempotency_key"] for event in answered} == {
            f"quiz-answered:test:{mc['id']}",
            f"quiz-answered:test:{short['id']}",
        }
        short_event = next(
            event
            for event in answered
            if event["idempotency_key"] == f"quiz-answered:test:{short['id']}"
        )
        assert short_event["result"] == "PARTIAL"
        assert short_event["score"] == 0.6
        # 评分路径的作答事件：occurred_at 取作答时刻（answered_at），非评分时刻。
        async with app.state.session_factory() as session:
            short_answered_at = await session.scalar(
                text("SELECT answered_at FROM quiz_test_items WHERE id=:id"), {"id": short["id"]}
            )
        assert short_event["occurred_at"] == short_answered_at
        completed_events = await fetch_learning_events(app, "quiz-test-completed:%")
        assert len(completed_events) == 1
        metadata = json.loads(cast(str, completed_events[0]["metadata_json"]))
        assert metadata["unscored_count"] == 0

        # 埋点链路：token/latency/model 照记（prompt 与输出全文不落）
        async with app.state.session_factory() as session:
            logs = (
                (
                    await session.execute(
                        text(
                            "SELECT graph_name, graph_node, model, token_usage_json "
                            "FROM llm_call_logs"
                        )
                    )
                )
                .mappings()
                .all()
            )
        assert len(logs) == 1
        assert logs[0]["graph_name"] == "quiz"
        assert logs[0]["graph_node"] == "grade"
        assert logs[0]["model"] == "qwen-plus"
        assert "31" in cast(str, logs[0]["token_usage_json"])


@pytest.mark.anyio
async def test_failed_item_is_unscored_excluded_and_low_confidence_flagged(
    tmp_path: Path,
) -> None:
    # 首题输出违反松一致性（WRONG 但 score=0.5）→ LLM_OUTPUT_INVALID；
    # 次题低置信（0.4 < 0.7）→ needs_review 标记
    model = FakeGradingModel(
        [
            {"verdict": "WRONG", "score": 0.5, "confidence": 0.9, "rationale": "矛盾输出"},
            {"verdict": "PARTIAL", "score": 0.5, "confidence": 0.4, "rationale": "只答到一半。"},
        ]
    )
    async with running_grading_app(tmp_path, model) as (app, client):
        await seed_quiz_bank(
            app,
            [
                ("MULTIPLE_CHOICE", 2),
                ("SHORT_ANSWER", "参考答案一"),
                ("SHORT_ANSWER", "参考答案二"),
            ],
        )
        await configure_llm_provider(client)
        test_id, items = await create_test_from_bank(client, ["MULTIPLE_CHOICE", "SHORT_ANSWER"])
        await answer_all(client, test_id, items)
        shorts = [item for item in items if item["question_type"] == "SHORT_ANSWER"]

        submitted = await client.post(f"/api/quiz-tests/{test_id}/submit")
        assert submitted.status_code == 200

        completed = await wait_for_test_status(client, test_id, "COMPLETED")
        # 失败题排除出分母：score = (1.0 + 0.5) / 2，整卷照常 COMPLETED
        assert completed["score"] == 0.75
        rows = {cast(str, item["id"]): item for item in cast(list[QuizItem], completed["items"])}

        failed = next(
            rows[cast(str, short["id"])]
            for short in shorts
            if ai_grade_of(rows[cast(str, short["id"])]).get("error_code") is not None
        )
        assert failed["result"] is None
        assert failed["score"] is None
        assert ai_grade_of(failed)["error_code"] == "LLM_OUTPUT_INVALID"

        graded = next(
            rows[cast(str, short["id"])] for short in shorts if short["id"] != failed["id"]
        )
        assert ai_grade_of(graded)["needs_review"] is True

        # 失败题不落 QUIZ_ANSWERED；未计分数入完成事件 metadata
        answered_keys = {
            event["idempotency_key"]
            for event in await fetch_learning_events(app, "quiz-answered:test:%")
        }
        assert f"quiz-answered:test:{failed['id']}" not in answered_keys
        assert f"quiz-answered:test:{graded['id']}" in answered_keys
        metadata = json.loads(
            cast(
                str,
                (await fetch_learning_events(app, "quiz-test-completed:%"))[0]["metadata_json"],
            )
        )
        assert metadata["unscored_count"] == 1


@pytest.mark.anyio
async def test_crash_recovery_flips_grading_failed_and_regrade_skips_graded(
    tmp_path: Path,
) -> None:
    model = FakeGradingModel(
        [
            {
                "verdict": "CORRECT",
                "score": 0.9,
                "confidence": 0.95,
                "rationale": "要点齐全。",
            }
        ]
    )
    async with running_grading_app(tmp_path, model) as (app, client):
        await seed_quiz_bank(
            app,
            [("SHORT_ANSWER", "参考答案一"), ("SHORT_ANSWER", "参考答案二")],
        )
        await configure_llm_provider(client)
        test_id, items = await create_test_from_bank(client, ["SHORT_ANSWER"])
        await answer_all(client, test_id, items)

    # 壳外模拟崩溃残留：RUNNING 评分 job + GRADING 卷面 + 其中一题已评成功
    first, second = items[0], items[1]
    now = "2026-08-31T09:00:00.000000Z"
    async with aiosqlite.connect(tmp_path / "knowrealm.db") as connection:
        await connection.execute(
            "UPDATE quiz_tests SET status = 'GRADING' WHERE id = :test_id",
            {"test_id": test_id},
        )
        await connection.execute(
            "UPDATE quiz_test_items SET result = 'CORRECT', score = 0.9, "
            "ai_grade_json = :grade WHERE id = :item_id",
            {
                "item_id": first["id"],
                "grade": json.dumps(
                    {
                        "verdict": "CORRECT",
                        "score": 0.9,
                        "confidence": 0.95,
                        "rationale": "要点齐全。",
                    }
                ),
            },
        )
        await connection.execute(
            "INSERT INTO learning_events (id, course_id, record_id, concept_id, event_type, "
            "source_type, source_id, result, score, difficulty, duration_ms, metadata_json, "
            "idempotency_key, schema_version, occurred_at, created_at) VALUES "
            "('66666666-6666-4666-8666-666666666666', :course_id, NULL, NULL, 'QUIZ_ANSWERED', "
            "'QUIZ_QUESTION', :quiz_id, 'CORRECT', 0.9, 'MEDIUM', NULL, '{}', :key, 1, :now, :now)",
            {
                "course_id": COURSE_ID,
                "quiz_id": first["quiz_id"],
                "key": f"quiz-answered:test:{first['id']}",
                "now": now,
            },
        )
        await connection.execute(
            "INSERT INTO processing_jobs (id, record_id, job_type, status, progress, attempts, "
            "max_attempts, next_run_at, input_json, result_json, error_code, error_message, "
            "started_at, finished_at, created_at, updated_at, waiting_reason) VALUES "
            "('77777777-7777-4777-8777-777777777777', NULL, 'QUIZ_GRADING', 'RUNNING', 0, 1, 3, "
            "NULL, :input_json, NULL, NULL, NULL, :now, NULL, :now, :now, NULL)",
            {"input_json": json.dumps({"test_id": test_id}), "now": now},
        )
        await connection.commit()

    # 重启 sidecar：恢复钩子把 RUNNING job 收编为 FAILED、卷面翻 GRADING_FAILED
    async with running_grading_app(tmp_path, model) as (app, client):
        detail = await client.get(f"/api/quiz-tests/{test_id}")
        assert detail.status_code == 200
        assert detail.json()["status"] == "GRADING_FAILED"

        # 非 GRADING_FAILED 态重评被拒
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE quiz_tests SET status = 'COMPLETED' WHERE id = :test_id"),
                {"test_id": test_id},
            )
        not_failed = await client.post(f"/api/quiz-tests/{test_id}/regrade")
        assert not_failed.status_code == 409
        assert not_failed.json()["detail"] == "只有评分失败的测试可以重新评分"
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE quiz_tests SET status = 'GRADING_FAILED' WHERE id = :test_id"),
                {"test_id": test_id},
            )

        regraded = await client.post(f"/api/quiz-tests/{test_id}/regrade")
        assert regraded.status_code == 200
        assert regraded.json()["status"] == "GRADING"

        completed = await wait_for_test_status(client, test_id, "COMPLETED")
        # 已评成功题跳过：模型只被调一次（评第二题），首题分数原样保留
        assert len(model.prompts) == 1
        assert CONTENT_LANGUAGE_INSTRUCTION in model.prompts[0]
        assert completed["score"] == 0.9
        rows = {cast(str, item["id"]): item for item in cast(list[QuizItem], completed["items"])}
        assert rows[cast(str, first["id"])]["score"] == 0.9
        assert rows[cast(str, second["id"])]["result"] == "CORRECT"

        # 事件键保证不重复：每题一条 + 完成事件一条
        answered_keys = {
            event["idempotency_key"]
            for event in await fetch_learning_events(app, "quiz-answered:test:%")
        }
        assert answered_keys == {
            f"quiz-answered:test:{first['id']}",
            f"quiz-answered:test:{second['id']}",
        }
        assert len(await fetch_learning_events(app, "quiz-test-completed:%")) == 1


@pytest.mark.anyio
async def test_archived_course_cancels_grading_job_at_claim(tmp_path: Path) -> None:
    model = FakeGradingModel([])
    async with running_grading_app(tmp_path, model) as (app, client):
        await seed_quiz_bank(app, [("SHORT_ANSWER", "参考答案文本")])
        await configure_llm_provider(client)
        test_id, items = await create_test_from_bank(client, ["SHORT_ANSWER"])
        await answer_all(client, test_id, items)

    # 第三道闸门：归档后残留的评分 job 在领取时静默取消，卷面翻 GRADING_FAILED
    now = "2026-08-31T09:30:00.000000Z"
    async with aiosqlite.connect(tmp_path / "knowrealm.db") as connection:
        await connection.execute(
            "UPDATE courses SET status = 'ARCHIVED' WHERE id = :course_id",
            {"course_id": COURSE_ID},
        )
        await connection.execute(
            "UPDATE quiz_tests SET status = 'GRADING' WHERE id = :test_id",
            {"test_id": test_id},
        )
        await connection.execute(
            "INSERT INTO processing_jobs (id, record_id, job_type, status, progress, attempts, "
            "max_attempts, next_run_at, input_json, result_json, error_code, error_message, "
            "started_at, finished_at, created_at, updated_at, waiting_reason) VALUES "
            "('88888888-8888-4888-8888-888888888888', NULL, 'QUIZ_GRADING', 'PENDING', 0, 0, 3, "
            "NULL, :input_json, NULL, NULL, NULL, NULL, NULL, :now, :now, NULL)",
            {"input_json": json.dumps({"test_id": test_id}), "now": now},
        )
        await connection.commit()

    async with running_grading_app(tmp_path, model) as (app, client):
        job_status = ""
        test_status = ""
        for _ in range(100):
            async with app.state.session_factory() as session:
                job_status = cast(
                    str,
                    await session.scalar(
                        text("SELECT status FROM processing_jobs WHERE job_type = 'QUIZ_GRADING'")
                    ),
                )
                test_status = cast(
                    str,
                    await session.scalar(
                        text("SELECT status FROM quiz_tests WHERE id = :test_id"),
                        {"test_id": test_id},
                    ),
                )
            if job_status == "CANCELLED" and test_status == "GRADING_FAILED":
                break
            await asyncio.sleep(0.05)
        assert job_status == "CANCELLED"
        assert test_status == "GRADING_FAILED"
        # 未发生任何 LLM 调用
        assert model.prompts == []


TEST_CONCEPT_ID = "55555555-5555-4555-8555-555555555565"


async def seed_confirmed_concept(app: FastAPI, concept_id: str, name: str) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO concepts "
                "(id, course_id, canonical_name, normalized_name, description, concept_type, "
                "importance, status, source, created_at, updated_at) "
                "VALUES (:id, :course_id, :name, :name, '', 'TERM', 3, 'CONFIRMED', "
                "'AI_EXTRACTED', :now, :now)"
            ),
            {"id": concept_id, "course_id": COURSE_ID, "name": name, "now": NOW},
        )


@pytest.mark.anyio
async def test_concept_binds_before_answer_fixes_on_test_answer(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (app, client):
        await seed_quiz_bank(app, [("MULTIPLE_CHOICE", 2), ("TRUE_FALSE", 0)])
        await seed_confirmed_concept(app, TEST_CONCEPT_ID, "进程调度")
        test_id, items = await create_test_from_bank(client, ["MULTIPLE_CHOICE", "TRUE_FALSE"])
        mc = next(item for item in items if item["question_type"] == "MULTIPLE_CHOICE")
        tf = next(item for item in items if item["question_type"] == "TRUE_FALSE")
        assert mc["record_id"] and mc["concept_id"] is None

        # 作答前：模拟测试题位可经记录端点修改主概念
        rebound = await client.put(
            f"/api/records/{mc['record_id']}/quizzes/{mc['quiz_id']}/concept",
            json={"concept_id": TEST_CONCEPT_ID},
        )
        assert rebound.status_code == 200, rebound.text
        assert rebound.json()["concept_id"] == TEST_CONCEPT_ID
        assert rebound.json()["concept_name"] == "进程调度"

        answered = await client.post(
            f"/api/quiz-tests/{test_id}/answers",
            json={"item_id": mc["id"], "answer": 2},
        )
        assert answered.status_code == 200
        mc_row = item_of(cast(list[QuizItem], answered.json()["items"]), mc["id"])
        assert mc_row["concept_id"] == TEST_CONCEPT_ID
        assert mc_row["concept_name"] == "进程调度"

        events = await fetch_test_answer_events(app)
        assert len(events) == 1
        assert events[0]["concept_id"] == TEST_CONCEPT_ID

        # 未绑定主概念的题位直接作答后，同样锁定（409 QUIZ_CONCEPT_LOCKED）
        tf_answered = await client.post(
            f"/api/quiz-tests/{test_id}/answers",
            json={"item_id": tf["id"], "answer": 0},
        )
        assert tf_answered.status_code == 200
        tf_locked = await client.put(
            f"/api/records/{tf['record_id']}/quizzes/{tf['quiz_id']}/concept",
            json={"concept_id": None},
        )
        assert tf_locked.status_code == 409
        assert cast(dict[str, object], tf_locked.json())["code"] == "QUIZ_CONCEPT_LOCKED"

        # 无主概念的作答事件照常落库，concept_id 为空
        events = await fetch_test_answer_events(app)
        assert len(events) == 2
        tf_event = next(
            event
            for event in events
            if event["idempotency_key"] == f"quiz-answered:test:{tf['id']}"
        )
        assert tf_event["concept_id"] is None
