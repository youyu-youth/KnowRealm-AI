import json
from datetime import UTC, date, datetime, timedelta, tzinfo
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.modules.agent.runtime import (
    AgentRuntimeContext,
    bind_agent_runtime_context,
    reset_agent_runtime_context,
)
from app.modules.agent.tools.get_today_progress import get_today_progress
from app.modules.today import service
from tests.test_today_plan_items import (
    create_course,
    insert_goal,
    insert_plan,
    insert_plan_item,
    running_today_app,
)

URL = "/api/today/progress"


@pytest.mark.anyio
async def test_progress_boundaries_history_filters_and_course_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    day = date(2026, 10, 15)
    monkeypatch.setattr(service, "local_today", lambda: day)
    start, end = service.local_day_bounds(day)
    async with running_today_app(tmp_path) as (app, client):
        course = await create_course(client, "当前课程")
        history = await create_course(client, "历史课程")
        goal, plan, old_goal, old_plan = (str(uuid4()) for _ in range(4))
        await insert_goal(app, goal, course, title="当前目标")
        await insert_plan(app, plan, goal)
        await insert_goal(app, old_goal, history, title="归档目标", status="ARCHIVED")
        await insert_plan(app, old_plan, old_goal, status="SUPERSEDED")
        for scheduled, minutes in [
            (day - timedelta(days=1), 30),
            (day, None),
            (day + timedelta(days=1), 50),
        ]:
            await insert_plan_item(
                app, str(uuid4()), plan, scheduled_date=str(scheduled), estimated_minutes=minutes
            )
        first, historical = str(uuid4()), str(uuid4())
        for item_id, plan_id, moment, status in [
            (first, plan, start, "DONE"),
            (historical, old_plan, end - timedelta(microseconds=1), "DONE"),
            (str(uuid4()), plan, start - timedelta(microseconds=1), "DONE"),
            (str(uuid4()), plan, end, "DONE"),
            (str(uuid4()), plan, None, "DONE"),
            (str(uuid4()), plan, start, "SKIPPED"),
        ]:
            await insert_plan_item(
                app,
                item_id,
                plan_id,
                scheduled_date=str(day + timedelta(days=5)),
                status=status,
                completed_at=moment,
            )
        await insert_plan_item(app, str(uuid4()), old_plan, scheduled_date=str(day))
        data = (await client.get(URL)).json()
        assert data["date"] == str(day)
        assert datetime.fromisoformat(data["day_start"].replace("Z", "+00:00")) == start
        assert datetime.fromisoformat(data["day_end"].replace("Z", "+00:00")) == end
        assert (data["completed_count"], data["pending_count"], data["overdue_count"]) == (2, 2, 1)
        assert data["remaining_estimated_minutes"] == 30 and data["unestimated_count"] == 1
        assert [item["item_id"] for item in data["completed_items"]] == [historical, first]
        assert data["completed_items"][0]["goal_title"] == "归档目标"
        scoped = (await client.get(URL, params={"course_id": history})).json()
        assert scoped["completed_count"] == 1 and scoped["pending_count"] == 0
        assert scoped["remaining_estimated_minutes"] == 0
        assert scoped["courses"] == data["courses"]
        assert (await client.delete(f"/api/courses/{history}")).status_code == 204
        hidden = (await client.get(URL)).json()
        assert hidden["completed_count"] == 1 and len(hidden["courses"]) == 1
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE courses SET deleted_at=NULL WHERE id=:id"), {"id": history}
            )
        assert (await client.get(URL)).json() == data


@pytest.mark.anyio
async def test_progress_completion_is_real_idempotent_and_not_learning_evidence(
    tmp_path: Path,
) -> None:
    async with running_today_app(tmp_path) as (app, client):
        course = await create_course(client, "课程")
        goal, plan, item = (str(uuid4()) for _ in range(3))
        await insert_goal(app, goal, course, title="学习目标")
        await insert_plan(app, plan, goal)
        await insert_plan_item(
            app, item, plan, scheduled_date=str(service.local_today()), estimated_minutes=None
        )
        before = (await client.get(URL)).json()
        assert before["pending_count"] == 1 and before["remaining_estimated_minutes"] is None
        path = f"/api/courses/{course}/plans/{plan}/items/{item}/complete"
        assert (await client.post(path)).status_code == 200
        after = (await client.get(URL)).json()
        assert after["pending_count"] == 0 and after["completed_count"] == 1
        assert (await client.post(path)).status_code == 200
        assert (await client.get(URL)).json() == after
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE learning_goals SET status='COMPLETED' WHERE id=:id"), {"id": goal}
            )
            await session.execute(
                text("UPDATE learning_plans SET status='COMPLETED' WHERE id=:id"), {"id": plan}
            )
            assert await session.scalar(text("SELECT COUNT(*) FROM learning_events")) == 0
        assert (await client.get(URL)).json() == after


@pytest.mark.anyio
async def test_progress_pagination_sort_validation_and_readonly_agent(tmp_path: Path) -> None:
    async with running_today_app(tmp_path) as (app, client):
        course = await create_course(client, "课程")
        goal, plan = str(uuid4()), str(uuid4())
        await insert_goal(app, goal, course, title="目标")
        await insert_plan(app, plan, goal)
        day = service.local_today()
        start, _ = service.local_day_bounds(day)
        for i in range(25):
            await insert_plan_item(
                app,
                str(uuid4()),
                plan,
                scheduled_date=str(day),
                status="DONE",
                completed_at=start + timedelta(minutes=i),
                estimated_minutes=i if i else None,
            )
        data = (await client.get(URL)).json()
        assert len(data["completed_items"]) == 20 and data["completed_count"] == 25
        page = (await client.get(URL, params={"offset": 20})).json()
        assert len(page["completed_items"]) == 5 and page["completed_count"] == 25
        assert not {item["item_id"] for item in data["completed_items"]} & {
            item["item_id"] for item in page["completed_items"]
        }
        duration = (await client.get(URL, params={"order": "duration", "limit": 100})).json()
        assert [item["estimated_minutes"] for item in duration["completed_items"]] == [
            *range(24, 0, -1),
            None,
        ]
        for params in [
            {"offset": -1},
            {"limit": 0},
            {"limit": 101},
            {"course_id": "bad"},
            {"order": "bad"},
        ]:
            assert (await client.get(URL, params=params)).status_code == 422
        assert (await client.get(URL, headers={"X-KnowRealm-Token": "bad"})).status_code == 403
        assert (await client.get(URL, params={"course_id": str(uuid4())})).json()[
            "completed_count"
        ] == 0
        async with app.state.session_factory() as session:
            before = (
                await session.execute(text("SELECT * FROM learning_plan_items ORDER BY id"))
            ).all()
        runtime = AgentRuntimeContext(
            session_factory=app.state.session_factory, session_id=str(uuid4())
        )
        token = bind_agent_runtime_context(runtime)
        try:
            with pytest.raises(ValidationError):
                await get_today_progress.ainvoke({"course_id": "not-a-uuid"})
            payload = json.loads(await get_today_progress.ainvoke({"limit": 1}))
            assert payload["ok"] and payload["total"] == 25 and payload["truncated"]
            assert len(payload["completed_items"]) == 1 and "仅列前 1" in payload["message"]
            assert payload["completed_items"][0] == data["completed_items"][0]
            assert not json.loads(await get_today_progress.ainvoke({"limit": 0}))["ok"]
            assert len(json.loads(await get_today_progress.ainvoke({}))["completed_items"]) == 25
            scoped = json.loads(await get_today_progress.ainvoke({"course_id": str(uuid4())}))
            assert scoped["completed_count"] == 0
            for _ in range(12):
                await get_today_progress.ainvoke({})
            assert "上限" in json.loads(await get_today_progress.ainvoke({}))["message"]
        finally:
            reset_agent_runtime_context(token)
        assert not json.loads(await get_today_progress.ainvoke({}))["ok"]
        async with app.state.session_factory() as session:
            assert (
                await session.execute(text("SELECT * FROM learning_plan_items ORDER BY id"))
            ).all() == before
        assert (await client.get(URL)).json() == data


@pytest.mark.anyio
async def test_empty_progress_and_query_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with running_today_app(tmp_path) as (app, client):
        empty = (await client.get(URL)).json()
        assert empty["completed_count"] == empty["pending_count"] == empty["overdue_count"] == 0
        assert empty["remaining_estimated_minutes"] == 0
        assert empty["courses"] == empty["completed_items"] == []

        async def unavailable(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("database unavailable")

        runtime = AgentRuntimeContext(
            session_factory=app.state.session_factory, session_id=str(uuid4())
        )
        token = bind_agent_runtime_context(runtime)
        try:
            with monkeypatch.context() as patch:
                patch.setattr(service.TodayService, "progress", unavailable)
                assert (await client.get(URL)).status_code == 500
                error = json.loads(await get_today_progress.ainvoke({}))
                assert not error["ok"] and "暂时无法查询" in error["message"]
        finally:
            reset_agent_runtime_context(token)
        assert (await client.get(URL)).json() == empty


@pytest.mark.parametrize("day,hours", [(date(2026, 3, 8), 23), (date(2026, 11, 1), 25)])
def test_local_bounds_convert_each_midnight_for_dst(
    day: date, hours: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    class LocalDateTime(datetime):
        def astimezone(self, tz: tzinfo | None = None) -> datetime:
            return (
                self.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(tz)
                if self.tzinfo is None
                else super().astimezone(tz)
            )

    monkeypatch.setattr(service, "datetime", LocalDateTime)
    start, end = service.local_day_bounds(day)
    assert start.tzinfo == UTC and end.tzinfo == UTC
    assert end - start == timedelta(hours=hours)
