"""资料学习闭环：真实 HTTP、迁移 SQLite；复用计划夹具，无模型替身。"""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.agent.graph import resolve_agent_config
from app.modules.agent.operations.registry import submit_operation
from app.modules.agent.runs.schemas import AuthMode
from app.modules.agent.runtime import (
    AgentRuntimeContext,
    bind_agent_runtime_context,
    reset_agent_runtime_context,
)
from app.modules.library.models import CourseSharedRef, LibraryItem, LibraryItemRecord
from tests.test_plan_editing import (
    COURSE_ID,
    ITEM_ID,
    NOW,
    PLAN_ID,
    RECORD_ID,
    plan_app,
    run_sql,
    seed_course,
    seed_goal,
    seed_item,
    seed_plan,
    seed_record,
    table_count,
)

BASE = f"/api/plan-items/{ITEM_ID}/study"
ITEM = f"/api/courses/{COURSE_ID}/plans/{PLAN_ID}/items/{ITEM_ID}"


async def seed_study(factory: async_sessionmaker[AsyncSession]) -> None:
    await seed_course(factory)
    await seed_goal(factory)
    await seed_plan(factory)
    await seed_record(factory)
    await seed_item(factory, ITEM_ID, record_id=RECORD_ID)


@pytest.mark.anyio
async def test_bind_start_resume_and_complete_without_mastery(tmp_path: Path) -> None:
    async with plan_app(tmp_path) as (client, factory):
        await seed_course(factory)
        await seed_goal(factory)
        await seed_plan(factory)
        await seed_record(factory)
        await seed_item(factory, ITEM_ID)
        current = await client.get(BASE)
        assert current.status_code == 200, current.text
        assert current.json()["source_status"] == "MISSING"
        assert current.json()["visit_id"] is None
        bound = await client.patch(ITEM, json={"record_id": RECORD_ID})
        assert bound.status_code == 200, bound.text
        assert (await client.get(BASE)).json()["visit_id"] is None
        assert (
            await client.put(
                "/api/today/continue-learning",
                json={
                    "kind": "RECORD",
                    "target_id": RECORD_ID,
                    "record_tab": "transcript",
                },
            )
        ).status_code == 204
        request_id = str(uuid4())
        started = await client.post(
            BASE + "/start", json={"request_id": request_id, "record_id": RECORD_ID}
        )
        assert started.status_code == 200, started.text
        assert started.json()["visit_id"] == request_id
        assert started.json()["tab"] == "transcript"
        first_started_at = started.json()["started_at"]
        saved = await client.put(
            BASE + "/tab",
            json={"visit_id": request_id, "record_id": RECORD_ID, "tab": "transcript"},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["tab"] == "transcript"
        # 全局访问元数据不得反填本计划项的页签或启动事实。
        response = await client.put(
            "/api/today/continue-learning",
            json={"kind": "RECORD", "target_id": RECORD_ID, "record_tab": "summary"},
        )
        assert response.status_code < 300, response.text
        current = (await client.get(BASE)).json()
        assert current["tab"] == "transcript" and current["started_at"] == first_started_at
        repeated = await client.post(
            BASE + "/start", json={"request_id": request_id, "record_id": RECORD_ID}
        )
        assert repeated.json()["started_at"] == first_started_at
        first = await client.post(ITEM + "/complete")
        second = await client.post(ITEM + "/complete")
        assert first.status_code == second.status_code == 200
        assert first.json()["completed_at"] == second.json()["completed_at"]
        progress = (await client.get("/api/today/progress")).json()
        assert progress["completed_count"] == 1
        assert len(progress["completed_items"]) == 1
        assert (await client.get(BASE)).json()["editable"] is True
        assert await table_count(factory, "learning_events") == 0
        assert await table_count(factory, "user_concept_mastery") == 0


@pytest.mark.anyio
async def test_visit_identity_rebinding_and_restart(tmp_path: Path) -> None:
    async with plan_app(tmp_path) as (client, factory):
        await seed_study(factory)
        first_id, second_id = str(uuid4()), str(uuid4())
        for request_id in (first_id, second_id):
            response = await client.post(
                BASE + "/start",
                json={
                    "request_id": request_id,
                    "record_id": RECORD_ID,
                },
            )
            assert response.status_code == 200, response.text
        stale = await client.put(
            BASE + "/tab",
            json={
                "visit_id": first_id,
                "record_id": RECORD_ID,
                "tab": "transcript",
            },
        )
        assert stale.status_code == 409
        assert stale.json()["code"] == "PLAN_STUDY_VISIT_STALE"
        saved = await client.put(
            BASE + "/tab",
            json={
                "visit_id": second_id,
                "record_id": RECORD_ID,
                "tab": "transcript",
            },
        )
        assert saved.status_code == 200
    # 应用完整退出/重启后，身份、时间及页签均来自 SQLite。
    async with plan_app(tmp_path) as (client, factory):
        state = (await client.get(BASE)).json()
        assert state["visit_id"] == second_id and state["tab"] == "transcript"
        await run_sql("DELETE FROM records WHERE id=:id", {"id": RECORD_ID}, factory)
        state = (await client.get(BASE)).json()
        assert state["source_status"] == "UNAVAILABLE" and state["source"] is None
        assert state["visit_id"] == second_id and state["item"]["record_id"] is None
        assert (
            await client.post(
                BASE + "/start",
                json={
                    "request_id": str(uuid4()),
                    "record_id": RECORD_ID,
                },
            )
        ).status_code == 409


@pytest.mark.anyio
@pytest.mark.parametrize("change", ["plan", "goal", "skipped", "deleted", "moved", "type"])
async def test_lifecycle_and_scope_are_enforced_at_http_writes(tmp_path: Path, change: str) -> None:
    async with plan_app(tmp_path) as (client, factory):
        await seed_study(factory)
        request_id = str(uuid4())
        assert (
            await client.post(
                BASE + "/start",
                json={
                    "request_id": request_id,
                    "record_id": RECORD_ID,
                },
            )
        ).status_code == 200
        changes = {
            "plan": "UPDATE learning_plans SET status='SUPERSEDED'",
            "goal": "UPDATE learning_goals SET status='COMPLETED'",
            "skipped": "UPDATE learning_plan_items SET status='SKIPPED'",
            "deleted": "UPDATE records SET deleted_at=:now",
            "moved": "UPDATE records SET course_id=NULL",
            "type": "UPDATE learning_plan_items SET action_type='CUSTOM'",
        }
        await run_sql(changes[change], {"now": NOW}, factory)
        assert (
            await client.post(
                BASE + "/start",
                json={
                    "request_id": str(uuid4()),
                    "record_id": RECORD_ID,
                },
            )
        ).status_code == 409
        assert (
            await client.put(
                BASE + "/tab",
                json={
                    "visit_id": request_id,
                    "record_id": RECORD_ID,
                    "tab": "transcript",
                },
            )
        ).status_code == 409
        if change in ("plan", "goal", "skipped"):
            assert (await client.patch(ITEM, json={"record_id": RECORD_ID})).status_code == 409
            assert (await client.post(ITEM + "/complete")).status_code == 409
            assert (await client.get(BASE)).json()["editable"] is False
        if change in ("deleted", "moved"):
            current = (await client.get(BASE)).json()
            assert current["source_status"] == "UNAVAILABLE" and current["source"] is None
            assert (await client.patch(ITEM, json={"record_id": RECORD_ID})).status_code == 409


@pytest.mark.anyio
async def test_shared_source_is_visible_read_only_and_loses_entry_after_unshare(
    tmp_path: Path,
) -> None:
    async with plan_app(tmp_path) as (client, factory):
        await seed_study(factory)
        await run_sql("UPDATE records SET course_id=NULL", {}, factory)
        assert (await client.patch(ITEM, json={"record_id": RECORD_ID})).status_code == 409
        async with factory() as session, session.begin():
            shared = LibraryItem(
                source_type="DOCUMENT", title="共享资料", content_hash="study-shared"
            )
            session.add(shared)
            await session.flush()
            shared_id = shared.id
            session.add(LibraryItemRecord(library_item_id=shared_id, record_id=RECORD_ID))
            session.add(CourseSharedRef(course_id=COURSE_ID, library_item_id=shared_id))
        current = (await client.get(BASE)).json()
        assert current["source"]["read_only"] is True
        guarded = await client.post(
            f"/api/records/{RECORD_ID}/summary-jobs?request_course_id={COURSE_ID}"
        )
        assert guarded.status_code == 409 and guarded.json()["code"] == "SHARED_REF_ASSET_READ_ONLY"
        assert (await client.patch(ITEM, json={"record_id": RECORD_ID})).status_code == 200
        assert (
            await client.post(
                BASE + "/start",
                json={
                    "request_id": str(uuid4()),
                    "record_id": RECORD_ID,
                },
            )
        ).status_code == 200
        response = await client.delete(f"/api/courses/{COURSE_ID}/shared-refs/{shared_id}")
        assert response.status_code < 300, response.text
        current = (await client.get(BASE)).json()
        assert current["source"] is None and current["sources"] == []


@pytest.mark.anyio
@pytest.mark.parametrize("auth_mode", list(AuthMode))
async def test_mounted_agent_only_binds_after_human_confirmation(
    tmp_path: Path, auth_mode: AuthMode
) -> None:
    async with plan_app(tmp_path) as (client, factory):
        await seed_study(factory)
        await run_sql("UPDATE learning_plan_items SET record_id=NULL", {}, factory)
        chat = (await client.post("/api/chat-sessions", json={})).json()["id"]
        tools = {
            tool.name: tool
            for tool in resolve_agent_config(retrieval=False, web_search_enabled=False).tools
        }
        token = bind_agent_runtime_context(
            AgentRuntimeContext(
                session_factory=factory,
                session_id=chat,
                auth_mode=auth_mode,
            )
        )
        try:
            queried = json.loads(await tools["get_plan_study"].ainvoke({"item_id": ITEM_ID}))
            assert queried["study"]["entry_path"] == f"/plan-items/{ITEM_ID}/study"
            assert queried["study"]["visit_id"] is None
            result = json.loads(
                await tools["update_plan_item"].ainvoke(
                    {
                        "item_id": ITEM_ID,
                        "record_id": RECORD_ID,
                    }
                )
            )
            assert result["ok"] is True and "executed" not in result, result
            assert (await client.get(BASE)).json()["source_status"] == "MISSING"
            confirmed = await client.post(
                f"/api/proposals/{result['proposals'][0]['proposal_id']}/confirm"
            )
            assert confirmed.status_code == 200, confirmed.text
            assert confirmed.json()["result"]["after"]["record_id"] == RECORD_ID
            assert (await client.get(BASE)).json()["source_status"] == "AVAILABLE"
        finally:
            reset_agent_runtime_context(token)


@pytest.mark.anyio
async def test_agent_stale_confirmation_and_direct_bypass_cannot_bind(tmp_path: Path) -> None:
    async with plan_app(tmp_path) as (client, factory):
        await seed_study(factory)
        await run_sql("UPDATE learning_plan_items SET record_id=NULL", {}, factory)
        chat = (await client.post("/api/chat-sessions", json={})).json()["id"]
        tools = {
            tool.name: tool
            for tool in resolve_agent_config(retrieval=False, web_search_enabled=False).tools
        }
        runtime = AgentRuntimeContext(
            session_factory=factory,
            session_id=chat,
            auth_mode=AuthMode.FULL_ACCESS,
        )
        token = bind_agent_runtime_context(runtime)
        try:
            result = json.loads(
                await tools["update_plan_item"].ainvoke(
                    {
                        "item_id": ITEM_ID,
                        "record_id": RECORD_ID,
                    }
                )
            )
            await run_sql("UPDATE records SET title='确认前已更换标题'", {}, factory)
            response = await client.post(
                f"/api/proposals/{result['proposals'][0]['proposal_id']}/confirm"
            )
            assert response.status_code == 422, response.text
            assert response.json()["params"]["errorCode"] == "OPERATION_SNAPSHOT_STALE"
            # 绕过强制确认的薄工具，直接走通用执行端仍不能把自动档当作业务确认。
            bypass = await submit_operation(
                runtime,
                "update_plan_item",
                {
                    "item_id": ITEM_ID,
                    "record_id": RECORD_ID,
                },
            )
            assert bypass["ok"] is False and bypass["error"] == "PLAN_STUDY_CONFIRMATION_REQUIRED"
            assert (await client.get(BASE)).json()["source_status"] == "MISSING"
        finally:
            reset_agent_runtime_context(token)
