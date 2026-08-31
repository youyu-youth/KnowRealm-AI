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

    assert version is not None and version[0] == 16
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
        assert all("correct_answer" not in item and "explanation" not in item for item in items)

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
                        "record_id, result, score FROM learning_events "
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
