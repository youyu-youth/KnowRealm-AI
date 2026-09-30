"""今日待学计划项端点与趋势双源（工单 04）。

list_due_plan_items：跨空间、排期日 ≤ 今天、仅 PENDING 的 ACTIVE 计划项；
趋势第二源＝DONE 计划项预估时长按完成日归日（不进学习证据链）。
"""

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
from app.modules.learning_plan.scheduling import local_today

TOKEN = "test-launch-token"

# 种子 id（前缀区分对象：1=目标 2=计划 3=项，次位区分场景）。
GOAL_A = "11111111-1111-4111-8111-111111111111"
PLAN_A = "21111111-1111-4111-8111-111111111111"
ITEM_A_OVERDUE = "31111111-1111-4111-8111-111111111111"
ITEM_A_LATE = "32111111-1111-4111-8111-111111111111"
ITEM_A_EARLY = "33111111-1111-4111-8111-111111111111"
ITEM_A_TOMORROW = "34111111-1111-4111-8111-111111111111"
ITEM_A_DONE = "35111111-1111-4111-8111-111111111111"
ITEM_A_SKIPPED = "36111111-1111-4111-8111-111111111111"
GOAL_B = "12111111-1111-4111-8111-111111111111"
PLAN_B = "22111111-1111-4111-8111-111111111111"
ITEM_B_TODAY = "31211111-1111-4111-8111-111111111111"
GOAL_ARCHIVED = "13111111-1111-4111-8111-111111111111"
PLAN_ARCHIVED_GOAL = "23111111-1111-4111-8111-111111111111"
ITEM_ARCHIVED_GOAL = "31311111-1111-4111-8111-111111111111"
GOAL_SUPERSEDED = "14111111-1111-4111-8111-111111111111"
PLAN_SUPERSEDED = "24111111-1111-4111-8111-111111111111"
ITEM_SUPERSEDED = "31411111-1111-4111-8111-111111111111"
GOAL_DELETED_COURSE = "15111111-1111-4111-8111-111111111111"
PLAN_DELETED_COURSE = "25111111-1111-4111-8111-111111111111"
ITEM_DELETED_COURSE = "31511111-1111-4111-8111-111111111111"


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


async def create_course(client: httpx.AsyncClient, name: str) -> str:
    course = await client.post(
        "/api/courses",
        json={"name": name, "learning_context": "SCHOOL", "education_stage": "UNDERGRADUATE"},
    )
    assert course.status_code == 201
    return str(course.json()["id"])


async def insert_goal(
    app: FastAPI, goal_id: str, course_id: str, *, title: str, status: str = "ACTIVE"
) -> None:
    now = _iso_ms(utcnow())
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO learning_goals "
                "(id, course_id, goal_type, title, target_date, daily_minutes, "
                "target_score, scope_source, scope_confirmed, status, created_at, updated_at) "
                "VALUES (:id, :course_id, 'SKILL', :title, NULL, 60, NULL, "
                "'USER_CONFIRMED', 1, :status, :now, :now)"
            ),
            {"id": goal_id, "course_id": course_id, "title": title, "status": status, "now": now},
        )


async def insert_plan(app: FastAPI, plan_id: str, goal_id: str, *, status: str = "ACTIVE") -> None:
    now = _iso_ms(utcnow())
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO learning_plans "
                "(id, goal_id, plan_version, status, effective_from, effective_to, "
                "created_at, updated_at) "
                "VALUES (:id, :goal_id, 1, :status, :from, NULL, :now, :now)"
            ),
            {"id": plan_id, "goal_id": goal_id, "status": status, "from": now[:10], "now": now},
        )


async def insert_plan_item(
    app: FastAPI,
    item_id: str,
    plan_id: str,
    *,
    scheduled_date: str,
    status: str = "PENDING",
    estimated_minutes: int | None = 30,
    priority: int = 1,
    completed_at: datetime | None = None,
) -> None:
    now = _iso_ms(utcnow())
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO learning_plan_items "
                "(id, plan_id, action_type, content, record_id, concept_id, phase_title, "
                "priority, estimated_minutes, scheduled_date, status, user_locked, "
                "completed_at, reason_json, created_at, updated_at) "
                "VALUES (:id, :plan_id, 'STUDY_RECORD', :content, NULL, NULL, '起步', "
                ":priority, :minutes, :scheduled, :status, 0, :completed, NULL, :now, :now)"
            ),
            {
                "id": item_id,
                "plan_id": plan_id,
                "content": f"学习-{item_id[:4]}",
                "priority": priority,
                "minutes": estimated_minutes,
                "scheduled": scheduled_date,
                "status": status,
                "completed": _iso_ms(completed_at) if completed_at else None,
                "now": now,
            },
        )


@pytest.mark.anyio
async def test_today_plan_items_lists_due_pending_only(tmp_path: Path) -> None:
    today = local_today().isoformat()
    yesterday = (local_today() - timedelta(days=1)).isoformat()
    tomorrow = (local_today() + timedelta(days=1)).isoformat()
    async with running_today_app(tmp_path / "KnowRealm") as (app, client):
        course_a = await create_course(client, "A空间")
        course_b = await create_course(client, "B空间")
        course_c = await create_course(client, "C空间")

        await insert_goal(app, GOAL_A, course_a, title="学会A")
        await insert_plan(app, PLAN_A, GOAL_A)
        # 逾期项排最前；同日按空间名、再按项序。
        await insert_plan_item(app, ITEM_A_OVERDUE, PLAN_A, scheduled_date=yesterday, priority=1)
        await insert_plan_item(app, ITEM_A_LATE, PLAN_A, scheduled_date=today, priority=2)
        await insert_plan_item(app, ITEM_A_EARLY, PLAN_A, scheduled_date=today, priority=1)
        # 明日 / 已完成 / 已跳过：都不是待学。
        await insert_plan_item(app, ITEM_A_TOMORROW, PLAN_A, scheduled_date=tomorrow)
        await insert_plan_item(
            app,
            ITEM_A_DONE,
            PLAN_A,
            scheduled_date=today,
            status="DONE",
            completed_at=utcnow(),
        )
        await insert_plan_item(app, ITEM_A_SKIPPED, PLAN_A, scheduled_date=today, status="SKIPPED")

        # 第二个空间：跨空间并列。
        await insert_goal(app, GOAL_B, course_b, title="学会B")
        await insert_plan(app, PLAN_B, GOAL_B)
        await insert_plan_item(app, ITEM_B_TODAY, PLAN_B, scheduled_date=today)

        # 归档目标、历史版本、软删课程三种不可见。
        await insert_goal(app, GOAL_ARCHIVED, course_a, title="旧目标", status="ARCHIVED")
        await insert_plan(app, PLAN_ARCHIVED_GOAL, GOAL_ARCHIVED)
        await insert_plan_item(app, ITEM_ARCHIVED_GOAL, PLAN_ARCHIVED_GOAL, scheduled_date=today)
        # ACTIVE 目标挂历史版本计划：换独立空间（单空间单 ACTIVE 目标唯一索引）。
        course_d = await create_course(client, "D空间")
        await insert_goal(app, GOAL_SUPERSEDED, course_d, title="换代目标")
        await insert_plan(app, PLAN_SUPERSEDED, GOAL_SUPERSEDED, status="SUPERSEDED")
        await insert_plan_item(app, ITEM_SUPERSEDED, PLAN_SUPERSEDED, scheduled_date=today)
        await insert_goal(app, GOAL_DELETED_COURSE, course_c, title="已删空间目标")
        await insert_plan(app, PLAN_DELETED_COURSE, GOAL_DELETED_COURSE)
        await insert_plan_item(app, ITEM_DELETED_COURSE, PLAN_DELETED_COURSE, scheduled_date=today)
        deleted = await client.delete(f"/api/courses/{course_c}")
        assert deleted.status_code == 204

        response = await client.get("/api/today/plan-items")

    assert response.status_code == 200
    items = response.json()
    # 顺序：昨日（A空间）→ 今日 A空间 priority 1 → 2 → 今日 B空间。
    assert [item["item_id"] for item in items] == [
        ITEM_A_OVERDUE,
        ITEM_A_EARLY,
        ITEM_A_LATE,
        ITEM_B_TODAY,
    ]
    assert items[0] == {
        "item_id": ITEM_A_OVERDUE,
        "plan_id": PLAN_A,
        "course_id": course_a,
        "course_name": "A空间",
        "goal_id": GOAL_A,
        "goal_title": "学会A",
        "action_type": "STUDY_RECORD",
        "content": "学习-3111",
        "estimated_minutes": 30,
        "scheduled_date": yesterday,
        "user_locked": False,
    }


@pytest.mark.anyio
async def test_stats_trend_adds_completed_plan_item_minutes(tmp_path: Path) -> None:
    now = utcnow()
    async with running_today_app(tmp_path / "KnowRealm") as (app, client):
        course_id = await create_course(client, "操作系统")
        deleted_id = await create_course(client, "已删空间")
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO records "
                    "(id, course_id, capture_type, title, status, duration_ms, "
                    "summary_confirmed_at, created_at, updated_at, deleted_at) "
                    "VALUES ('11111111-1111-4111-8111-111111111111', :course_id, "
                    "'RECORDING', '今日录音', 'COMPLETED', 1000000, NULL, :now, :now, NULL)"
                ),
                {"course_id": course_id, "now": _iso_ms(now)},
            )

        await insert_goal(app, GOAL_B, course_id, title="学会操作系统")
        await insert_plan(app, PLAN_B, GOAL_B)
        # 今日完成 30 分钟 → 今日 +1_800_000。
        await insert_plan_item(
            app,
            ITEM_B_TODAY,
            PLAN_B,
            scheduled_date=now.date().isoformat(),
            status="DONE",
            completed_at=now,
            estimated_minutes=30,
        )
        # 两天前完成 20 分钟 → 该日 +1_200_000。
        await insert_plan_item(
            app,
            ITEM_A_LATE,
            PLAN_B,
            scheduled_date=(now - timedelta(days=2)).date().isoformat(),
            status="DONE",
            completed_at=now - timedelta(days=2),
            estimated_minutes=20,
        )
        # 跳过项无 completed_at、未完成项：都不贡献时长。
        await insert_plan_item(
            app,
            ITEM_A_SKIPPED,
            PLAN_B,
            scheduled_date=now.date().isoformat(),
            status="SKIPPED",
            estimated_minutes=45,
        )
        await insert_plan_item(
            app,
            ITEM_A_TOMORROW,
            PLAN_B,
            scheduled_date=now.date().isoformat(),
            estimated_minutes=15,
        )
        # DONE 但时长为空：贡献 0。
        await insert_plan_item(
            app,
            ITEM_A_DONE,
            PLAN_B,
            scheduled_date=now.date().isoformat(),
            status="DONE",
            completed_at=now,
            estimated_minutes=None,
        )
        # 软删课程名下的完成项：回落不计。
        await insert_goal(app, GOAL_DELETED_COURSE, deleted_id, title="已删目标")
        await insert_plan(app, PLAN_DELETED_COURSE, GOAL_DELETED_COURSE)
        await insert_plan_item(
            app,
            ITEM_DELETED_COURSE,
            PLAN_DELETED_COURSE,
            scheduled_date=now.date().isoformat(),
            status="DONE",
            completed_at=now,
            estimated_minutes=60,
        )
        deleted = await client.delete(f"/api/courses/{deleted_id}")
        assert deleted.status_code == 204

        trend = await client.get("/api/today/stats/trend", params={"days": 7})

    assert trend.status_code == 200
    points = trend.json()
    assert [point["date"] for point in points][-1] == now.date().isoformat()
    assert points[-1]["total_ms"] == 1_000_000 + 30 * 60_000
    assert points[-3]["total_ms"] == 20 * 60_000
    assert sum(point["total_ms"] for point in points) == 1_000_000 + 50 * 60_000
