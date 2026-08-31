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
