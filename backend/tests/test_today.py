from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.db.base import utcnow
from app.main import create_app

TOKEN = "test-launch-token"


@asynccontextmanager
async def running_today_app(
    data_dir: Path,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(data_dir=data_dir, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client


def _iso_ms(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


async def insert_stats_record(
    app: FastAPI,
    record_id: str,
    *,
    course_id: str | None,
    capture_type: str = "DOCUMENT_IMPORT",
    status: str = "COMPLETED",
    duration_ms: int = 0,
    created_at: datetime | None = None,
    deleted: bool = False,
) -> None:
    moment = _iso_ms(created_at or utcnow())
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO records "
                "(id, course_id, capture_type, title, status, duration_ms, "
                "summary_confirmed_at, created_at, updated_at, deleted_at) "
                "VALUES (:id, :course_id, :capture_type, :title, :status, :duration_ms, "
                "NULL, :created_at, :created_at, :deleted_at)"
            ),
            {
                "id": record_id,
                "course_id": course_id,
                "capture_type": capture_type,
                "title": f"记录-{record_id[:4]}",
                "status": status,
                "duration_ms": duration_ms,
                "created_at": moment,
                "deleted_at": _iso_ms(utcnow()) if deleted else None,
            },
        )


async def insert_stats_summary(
    app: FastAPI,
    summary_id: str,
    record_id: str,
    *,
    version_no: int,
    status: str = "GENERATED",
) -> None:
    now = _iso_ms(utcnow())
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO ai_summaries "
                "(id, record_id, version_no, transcript_source_version, topic, abstract, "
                "summary_json, status, model, prompt_version, token_usage_json, latency_ms, "
                "user_feedback, confirmed_at, created_at, updated_at, deleted_at) "
                "VALUES (:id, :record_id, :version_no, 1, '主题', '摘要', '{}', :status, "
                "'qwen-plus', 'summary-v1', '{}', 10, NULL, NULL, :now, :now, NULL)"
            ),
            {
                "id": summary_id,
                "record_id": record_id,
                "version_no": version_no,
                "status": status,
                "now": now,
            },
        )


async def insert_stats_quiz(
    app: FastAPI,
    quiz_id: str,
    record_id: str,
    *,
    generation_status: str = "ACTIVE",
    answered: bool = False,
) -> None:
    now = _iso_ms(utcnow())
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO quizzes "
                "(id, record_id, batch_id, generated_from_summary_id, generation_status, "
                "question_type, stem, options_json, correct_answer_json, explanation, "
                "difficulty, user_answer_json, answer_result, answered_at, "
                "created_at, updated_at, deleted_at) "
                "VALUES (:id, :record_id, NULL, NULL, :generation_status, 'MULTIPLE_CHOICE', "
                "'题干', '[]', '{}', '解析', 'EASY', :user_answer_json, :answer_result, "
                ":answered_at, :now, :now, NULL)"
            ),
            {
                "id": quiz_id,
                "record_id": record_id,
                "generation_status": generation_status,
                "user_answer_json": '"B"' if answered else None,
                "answer_result": "CORRECT" if answered else None,
                "answered_at": now if answered else None,
                "now": now,
            },
        )


async def insert_stats_chat_message(
    app: FastAPI,
    message_id: str,
    session_id: str,
    role: str,
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO chat_messages (id, session_id, role, content, created_at) "
                "VALUES (:id, :session_id, :role, '消息内容', :now)"
            ),
            {
                "id": message_id,
                "session_id": session_id,
                "role": role,
                "now": _iso_ms(utcnow()),
            },
        )


async def insert_stats_quiz_test_item(
    app: FastAPI,
    test_id: str,
    item_id: str,
    quiz_id: str,
    course_id: str,
) -> None:
    now = _iso_ms(utcnow())
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO quiz_tests "
                "(id, course_id, record_id, mode, status, score, started_at, completed_at, "
                "created_at, updated_at, deleted_at) "
                "VALUES (:id, :course_id, NULL, 'MOCK', 'COMPLETED', 1.0, :now, "
                ":now, :now, :now, NULL)"
            ),
            {"id": test_id, "course_id": course_id, "now": now},
        )
        await session.execute(
            text(
                "INSERT INTO quiz_test_items "
                "(id, test_id, quiz_id, sequence_no, user_answer_json, result, score, "
                "ai_grade_json, answered_at, created_at, updated_at, deleted_at) "
                "VALUES (:id, :test_id, :quiz_id, 1, '\"A\"', 'CORRECT', 1.0, NULL, "
                ":now, :now, :now, NULL)"
            ),
            {"id": item_id, "test_id": test_id, "quiz_id": quiz_id, "now": now},
        )


async def create_course(client: httpx.AsyncClient, name: str) -> str:
    course = await client.post(
        "/api/courses",
        json={
            "name": name,
            "learning_context": "SCHOOL",
            "education_stage": "UNDERGRADUATE",
        },
    )
    assert course.status_code == 201
    return str(course.json()["id"])


@pytest.mark.anyio
async def test_today_lists_only_live_summary_ready_records(tmp_path: Path) -> None:
    async with running_today_app(tmp_path / "KnowRealm") as (app, client):
        active_course = await client.post(
            "/api/courses",
            json={
                "name": "操作系统",
                "learning_context": "SCHOOL",
                "education_stage": "UNDERGRADUATE",
            },
        )
        archived_course = await client.post(
            "/api/courses",
            json={
                "name": "已归档课程",
                "learning_context": "INTEREST",
                "depth": "ADVANCED",
            },
        )
        active_id = active_course.json()["id"]
        archived_id = archived_course.json()["id"]
        await client.patch(f"/api/courses/{archived_id}", json={"status": "ARCHIVED"})

        async def insert_record(
            record_id: str,
            course_id: str,
            status: str,
            updated_at: str,
            *,
            deleted: bool = False,
        ) -> None:
            async with app.state.session_factory() as session, session.begin():
                await session.execute(
                    text(
                        "INSERT INTO records "
                        "(id, course_id, capture_type, title, status, duration_ms, "
                        "summary_confirmed_at, created_at, updated_at, deleted_at) "
                        "VALUES (:id, :course_id, 'DOCUMENT_IMPORT', :title, :status, 0, "
                        "NULL, :updated_at, :updated_at, :deleted_at)"
                    ),
                    {
                        "id": record_id,
                        "course_id": course_id,
                        "title": f"记录-{record_id[:4]}",
                        "status": status,
                        "updated_at": updated_at,
                        "deleted_at": "2026-08-23T13:00:00.000000Z" if deleted else None,
                    },
                )

        await insert_record(
            "11111111-1111-4111-8111-111111111111",
            active_id,
            "SUMMARY_READY",
            "2026-08-23T12:00:00.000000Z",
        )
        await insert_record(
            "22222222-2222-4222-8222-222222222222",
            active_id,
            "SUMMARY_PENDING",
            "2026-08-23T12:30:00.000000Z",
        )
        await insert_record(
            "33333333-3333-4333-8333-333333333333",
            active_id,
            "COMPLETED",
            "2026-08-23T12:40:00.000000Z",
        )
        await insert_record(
            "44444444-4444-4444-8444-444444444444",
            active_id,
            "SUMMARY_READY",
            "2026-08-23T12:50:00.000000Z",
            deleted=True,
        )
        await insert_record(
            "55555555-5555-4555-8555-555555555555",
            archived_id,
            "SUMMARY_READY",
            "2026-08-23T11:00:00.000000Z",
        )

        todos = await client.get("/api/today/pending-summaries")

    assert todos.status_code == 200
    assert todos.json() == [
        {
            "record_id": "11111111-1111-4111-8111-111111111111",
            "title": "记录-1111",
            "course_id": active_id,
            "course_name": "操作系统",
            "ready_at": "2026-08-23T12:00:00.000000Z",
        },
        {
            "record_id": "55555555-5555-4555-8555-555555555555",
            "title": "记录-5555",
            "course_id": archived_id,
            "course_name": "已归档课程",
            "ready_at": "2026-08-23T11:00:00.000000Z",
        },
    ]


@pytest.mark.anyio
async def test_stats_and_trend_empty_database_all_zeros_and_flat_line(
    tmp_path: Path,
) -> None:
    async with running_today_app(tmp_path / "KnowRealm") as (_app, client):
        stats = await client.get("/api/today/stats")
        trend = await client.get("/api/today/stats/trend", params={"days": 7})

    assert stats.status_code == 200
    assert stats.json() == {
        "total_learning_ms": 0,
        "record_count": 0,
        "course_count": 0,
        "ai_summary_count": 0,
        "quiz_generated_count": 0,
        "quiz_answered_count": 0,
        "chat_turn_count": 0,
    }
    assert trend.status_code == 200
    points = trend.json()
    today = utcnow().date()
    assert [point["date"] for point in points] == [
        (today - timedelta(days=offset)).isoformat() for offset in range(6, -1, -1)
    ]
    assert [point["total_ms"] for point in points] == [0] * 7


@pytest.mark.anyio
async def test_stats_seven_metrics_follow_defined_scopes(tmp_path: Path) -> None:
    async with running_today_app(tmp_path / "KnowRealm") as (app, client):
        course_id = await create_course(client, "操作系统")
        archived_id = await create_course(client, "已归档课程")
        archived = await client.patch(f"/api/courses/{archived_id}", json={"status": "ARCHIVED"})
        assert archived.status_code == 200

        await insert_stats_record(
            app,
            "11111111-1111-4111-8111-111111111111",
            course_id=course_id,
            capture_type="RECORDING",
            duration_ms=3_600_000,
        )
        await insert_stats_record(
            app,
            "22222222-2222-4222-8222-222222222222",
            course_id=course_id,
            capture_type="AUDIO_IMPORT",
            duration_ms=1_800_000,
        )
        # FAILED 记录计入记录数、时长为 0。
        await insert_stats_record(
            app,
            "33333333-3333-4333-8333-333333333333",
            course_id=course_id,
            capture_type="RECORDING",
            status="FAILED",
        )
        # 速记（NOTE）计入记录数。
        await insert_stats_record(
            app,
            "44444444-4444-4444-8444-444444444444",
            course_id=course_id,
            capture_type="QUICK_NOTE",
            status="NOTE",
        )
        # 收件箱未归类（course_id 为空）计入记录数。
        await insert_stats_record(
            app,
            "55555555-5555-4555-8555-555555555555",
            course_id=None,
            status="SUMMARY_PENDING",
        )
        # 重新生成版本（SUPERSEDED）与最新版（GENERATED）都计入 AI 总结次数。
        await insert_stats_summary(
            app,
            "66666666-6666-4666-8666-666666666666",
            "11111111-1111-4111-8111-111111111111",
            version_no=1,
            status="SUPERSEDED",
        )
        await insert_stats_summary(
            app,
            "77777777-7777-4777-8777-777777777777",
            "11111111-1111-4111-8111-111111111111",
            version_no=2,
            status="GENERATED",
        )
        # 历史批次（SUPERSEDED）计入生成次数；已作答计入完成次数。
        await insert_stats_quiz(
            app,
            "88888888-8888-4888-8888-888888888888",
            "11111111-1111-4111-8111-111111111111",
            answered=True,
        )
        await insert_stats_quiz(
            app,
            "99999999-9999-4999-8999-999999999999",
            "11111111-1111-4111-8111-111111111111",
            generation_status="DRAFT",
        )
        await insert_stats_quiz(
            app,
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "11111111-1111-4111-8111-111111111111",
            generation_status="SUPERSEDED",
        )
        session = (await client.post("/api/chat-sessions", json={})).json()
        await insert_stats_chat_message(
            app, "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1", session["id"], "USER"
        )
        await insert_stats_chat_message(
            app, "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2", session["id"], "ASSISTANT"
        )
        await insert_stats_chat_message(
            app, "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb3", session["id"], "USER"
        )
        await insert_stats_chat_message(
            app, "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb4", session["id"], "ASSISTANT"
        )
        await insert_stats_chat_message(
            app, "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb5", session["id"], "USER"
        )

        stats = await client.get("/api/today/stats")

    assert stats.status_code == 200
    assert stats.json() == {
        "total_learning_ms": 5_400_000,
        "record_count": 5,
        "course_count": 2,
        "ai_summary_count": 2,
        "quiz_generated_count": 3,
        "quiz_answered_count": 1,
        "chat_turn_count": 3,
    }


@pytest.mark.anyio
async def test_stats_fall_back_after_record_soft_delete(tmp_path: Path) -> None:
    async with running_today_app(tmp_path / "KnowRealm") as (app, client):
        course_id = await create_course(client, "操作系统")
        await insert_stats_record(
            app,
            "11111111-1111-4111-8111-111111111111",
            course_id=course_id,
            capture_type="RECORDING",
            duration_ms=1_800_000,
        )
        await insert_stats_summary(
            app,
            "22222222-2222-4222-8222-222222222222",
            "11111111-1111-4111-8111-111111111111",
            version_no=1,
        )
        await insert_stats_quiz(
            app,
            "33333333-3333-4333-8333-333333333333",
            "11111111-1111-4111-8111-111111111111",
            answered=True,
        )
        await insert_stats_quiz(
            app,
            "44444444-4444-4444-8444-444444444444",
            "11111111-1111-4111-8111-111111111111",
        )
        # 未删除的第二条记录：证明回落只作用于被删记录名下的指标。
        await insert_stats_record(
            app,
            "55555555-5555-4555-8555-555555555555",
            course_id=course_id,
            capture_type="RECORDING",
            duration_ms=600_000,
        )
        await insert_stats_summary(
            app,
            "66666666-6666-4666-8666-666666666666",
            "55555555-5555-4555-8555-555555555555",
            version_no=1,
        )
        await insert_stats_quiz(
            app,
            "77777777-7777-4777-8777-777777777777",
            "55555555-5555-4555-8555-555555555555",
            answered=True,
        )
        before = (await client.get("/api/today/stats")).json()
        assert before == {
            "total_learning_ms": 2_400_000,
            "record_count": 2,
            "course_count": 1,
            "ai_summary_count": 2,
            "quiz_generated_count": 3,
            "quiz_answered_count": 2,
            "chat_turn_count": 0,
        }

        deleted = await client.delete("/api/records/11111111-1111-4111-8111-111111111111")
        assert deleted.status_code == 204
        after = (await client.get("/api/today/stats")).json()

    assert after == {
        "total_learning_ms": 600_000,
        "record_count": 1,
        "course_count": 1,
        "ai_summary_count": 1,
        "quiz_generated_count": 1,
        "quiz_answered_count": 1,
        "chat_turn_count": 0,
    }


@pytest.mark.anyio
async def test_stats_fall_back_after_course_soft_delete(tmp_path: Path) -> None:
    async with running_today_app(tmp_path / "KnowRealm") as (app, client):
        course_id = await create_course(client, "被删课程")
        kept_id = await create_course(client, "保留课程")
        await insert_stats_record(
            app,
            "11111111-1111-4111-8111-111111111111",
            course_id=course_id,
            capture_type="RECORDING",
            duration_ms=1_800_000,
        )
        await insert_stats_summary(
            app,
            "22222222-2222-4222-8222-222222222222",
            "11111111-1111-4111-8111-111111111111",
            version_no=1,
        )
        await insert_stats_quiz(
            app,
            "33333333-3333-4333-8333-333333333333",
            "11111111-1111-4111-8111-111111111111",
            answered=True,
        )
        await insert_stats_record(
            app,
            "44444444-4444-4444-8444-444444444444",
            course_id=kept_id,
            capture_type="RECORDING",
            duration_ms=600_000,
        )
        before = (await client.get("/api/today/stats")).json()
        assert before["course_count"] == 2
        assert before["record_count"] == 2
        assert before["ai_summary_count"] == 1

        deleted = await client.delete(f"/api/courses/{course_id}")
        assert deleted.status_code == 204
        after = (await client.get("/api/today/stats")).json()

    assert after == {
        "total_learning_ms": 600_000,
        "record_count": 1,
        "course_count": 1,
        "ai_summary_count": 0,
        "quiz_generated_count": 0,
        "quiz_answered_count": 0,
        "chat_turn_count": 0,
    }


@pytest.mark.anyio
async def test_stats_counts_regenerated_summary_versions(tmp_path: Path) -> None:
    async with running_today_app(tmp_path / "KnowRealm") as (app, client):
        course_id = await create_course(client, "操作系统")
        await insert_stats_record(
            app,
            "11111111-1111-4111-8111-111111111111",
            course_id=course_id,
        )
        await insert_stats_summary(
            app,
            "22222222-2222-4222-8222-222222222222",
            "11111111-1111-4111-8111-111111111111",
            version_no=1,
        )
        first = (await client.get("/api/today/stats")).json()
        assert first["ai_summary_count"] == 1

        # 重新生成：旧版转 SUPERSEDED，新版落 GENERATED，行数 +1 即次数 +1。
        await insert_stats_summary(
            app,
            "33333333-3333-4333-8333-333333333333",
            "11111111-1111-4111-8111-111111111111",
            version_no=2,
        )
        second = (await client.get("/api/today/stats")).json()

    assert second["ai_summary_count"] == 2


@pytest.mark.anyio
async def test_stats_quiz_test_submission_does_not_count_as_answered(
    tmp_path: Path,
) -> None:
    async with running_today_app(tmp_path / "KnowRealm") as (app, client):
        course_id = await create_course(client, "操作系统")
        await insert_stats_record(
            app,
            "11111111-1111-4111-8111-111111111111",
            course_id=course_id,
        )
        await insert_stats_quiz(
            app,
            "22222222-2222-4222-8222-222222222222",
            "11111111-1111-4111-8111-111111111111",
        )
        # 模拟测试交卷：作答写在 quiz_test_items，不回写 quizzes.answered_at。
        await insert_stats_quiz_test_item(
            app,
            "33333333-3333-4333-8333-333333333333",
            "44444444-4444-4444-8444-444444444444",
            "22222222-2222-4222-8222-222222222222",
            course_id,
        )

        stats = await client.get("/api/today/stats")

    assert stats.status_code == 200
    assert stats.json()["quiz_answered_count"] == 0
    assert stats.json()["quiz_generated_count"] == 1


@pytest.mark.anyio
async def test_stats_trend_fills_missing_days_and_filters_deleted(
    tmp_path: Path,
) -> None:
    now = utcnow()
    async with running_today_app(tmp_path / "KnowRealm") as (app, client):
        course_id = await create_course(client, "操作系统")
        await insert_stats_record(
            app,
            "11111111-1111-4111-8111-111111111111",
            course_id=course_id,
            capture_type="RECORDING",
            duration_ms=1_000_000,
            created_at=now,
        )
        # 纯文档/粘贴记录时长贡献 0。
        await insert_stats_record(
            app,
            "22222222-2222-4222-8222-222222222222",
            course_id=course_id,
            capture_type="PASTE",
            created_at=now,
        )
        await insert_stats_record(
            app,
            "33333333-3333-4333-8333-333333333333",
            course_id=course_id,
            capture_type="RECORDING",
            duration_ms=500_000,
            created_at=now - timedelta(days=2),
        )
        await insert_stats_record(
            app,
            "44444444-4444-4444-8444-444444444444",
            course_id=course_id,
            capture_type="RECORDING",
            duration_ms=400_000,
            created_at=now - timedelta(days=3),
            deleted=True,
        )
        await insert_stats_record(
            app,
            "55555555-5555-4555-8555-555555555555",
            course_id=course_id,
            capture_type="RECORDING",
            duration_ms=900_000,
            created_at=now - timedelta(days=40),
        )

        week = await client.get("/api/today/stats/trend", params={"days": 7})
        month = await client.get("/api/today/stats/trend", params={"days": 30})

    assert week.status_code == 200
    week_points = week.json()
    today = now.date()
    assert [point["date"] for point in week_points] == [
        (today - timedelta(days=offset)).isoformat() for offset in range(6, -1, -1)
    ]
    assert [point["total_ms"] for point in week_points] == [
        0,
        0,
        0,
        0,
        500_000,
        0,
        1_000_000,
    ]

    assert month.status_code == 200
    month_points = month.json()
    assert len(month_points) == 30
    # 40 天前的记录落在窗口外。
    assert month_points[0]["total_ms"] == 0
    assert month_points[-1]["total_ms"] == 1_000_000
    assert sum(point["total_ms"] for point in month_points) == 1_500_000


@pytest.mark.anyio
async def test_stats_trend_rejects_days_outside_whitelist(tmp_path: Path) -> None:
    async with running_today_app(tmp_path / "KnowRealm") as (_app, client):
        for days in (14, 8, "abc"):
            response = await client.get("/api/today/stats/trend", params={"days": days})
            assert response.status_code == 422
        missing = await client.get("/api/today/stats/trend")
        assert missing.status_code == 422


@pytest.mark.anyio
async def test_stats_fall_back_after_chat_session_soft_delete(tmp_path: Path) -> None:
    async with running_today_app(tmp_path / "KnowRealm") as (app, client):
        first = (await client.post("/api/chat-sessions", json={})).json()
        second = (await client.post("/api/chat-sessions", json={})).json()
        await insert_stats_chat_message(
            app, "11111111-1111-4111-8111-111111111111", first["id"], "USER"
        )
        await insert_stats_chat_message(
            app, "22222222-2222-4222-8222-222222222222", first["id"], "USER"
        )
        await insert_stats_chat_message(
            app, "33333333-3333-4333-8333-333333333333", second["id"], "USER"
        )
        before = (await client.get("/api/today/stats")).json()
        assert before["chat_turn_count"] == 3

        deleted = await client.delete(f"/api/chat-sessions/{first['id']}")
        assert deleted.status_code == 204
        after = (await client.get("/api/today/stats")).json()

    assert after["chat_turn_count"] == 1
