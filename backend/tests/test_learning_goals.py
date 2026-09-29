"""学习目标（通用 Agent 第三阶段工单 01）：迁移结构、领域 Service 单 ACTIVE 与
scope 确认语义、课程嵌套路由集成、Agent 工具确认卡与授权行为。"""

import json
import sqlite3
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any, cast

import aiosqlite
import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import create_database
from app.db.migrations import run_migrations, supported_user_version
from app.modules.agent.runs.schemas import AuthMode
from app.modules.agent.runtime import (
    AgentRuntimeContext,
    ToolCallBudget,
    bind_agent_runtime_context,
    reset_agent_runtime_context,
)
from app.modules.agent.tools.create_goal import create_goal
from app.modules.agent.tools.get_goal import get_goal
from app.modules.agent.tools.list_goals import list_goals
from app.modules.agent.tools.update_goal import update_goal
from app.modules.course.service import CourseService
from app.modules.learning_plan.schemas import (
    GoalCreateCore,
    GoalScopeSource,
    GoalStatus,
    GoalUpdate,
)
from app.modules.learning_plan.service import GoalService
from app.modules.library.proposals import ProposalService
from app.shared.errors import CodedHTTPException

TOKEN = "test-launch-token"
NOW = "2026-09-29T08:00:00.000000Z"
COURSE_ID = "c0000000-0000-4000-8000-000000000001"
COURSE_OTHER = "c0000000-0000-4000-8000-000000000002"
UNKNOWN_ID = "c0000000-0000-4000-8000-00000000dead"
GOAL_ID = "90000000-0000-4000-8000-000000000001"


# ---------------------------------------------------------------------------
# 夹具：裸库（Service / 工具级）与 TestClient（路由集成）。


@asynccontextmanager
async def bare_db(tmp_path: Path) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    _engine, session_factory = create_database(db_path)
    try:
        yield session_factory
    finally:
        await _engine.dispose()


@asynccontextmanager
async def goal_client(tmp_path: Path) -> AsyncGenerator[httpx.AsyncClient]:
    from app.main import create_app

    data_dir = tmp_path / "KnowRealm"
    app = create_app(data_dir=data_dir, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        await app.state.course_tombstone_cleanup_task
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield client


async def run_sql(
    sql: str,
    params: dict[str, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(text(sql), params)


async def seed_course(
    session_factory: async_sessionmaker[AsyncSession],
    course_id: str = COURSE_ID,
    *,
    name: str = "Agent 工程",
) -> None:
    await run_sql(
        "INSERT INTO courses (id, name, learning_context, depth, status, created_at, "
        "updated_at) VALUES (:id, :name, 'INTEREST', 'INTERMEDIATE', 'ACTIVE', :now, :now)",
        {"id": course_id, "name": name, "now": NOW},
        session_factory,
    )


async def seed_goal(
    session_factory: async_sessionmaker[AsyncSession],
    goal_id: str = GOAL_ID,
    *,
    course_id: str = COURSE_ID,
    status: str = "ACTIVE",
) -> None:
    await run_sql(
        "INSERT INTO learning_goals (id, course_id, goal_type, title, target_date, "
        "daily_minutes, scope_source, scope_confirmed, status, created_at, updated_at) "
        "VALUES (:id, :course_id, 'SKILL', '四周内学会 Agent 工程', '2026-10-27', 60, "
        "'AI_INFERRED', 1, :status, :now, :now)",
        {"id": goal_id, "course_id": course_id, "status": status, "now": NOW},
        session_factory,
    )


async def goal_row(
    session_factory: async_sessionmaker[AsyncSession], goal_id: str
) -> dict[str, Any]:
    async with session_factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT course_id, goal_type, title, target_date, daily_minutes, "
                    "scope_source, scope_confirmed, status FROM learning_goals WHERE id = :id"
                ),
                {"id": goal_id},
            )
        ).one()
    return {
        "course_id": row[0],
        "goal_type": row[1],
        "title": row[2],
        "target_date": row[3],
        "daily_minutes": row[4],
        "scope_source": row[5],
        "scope_confirmed": bool(row[6]),
        "status": row[7],
    }


async def invoke_tool(
    tool: Any,
    session_factory: async_sessionmaker[AsyncSession],
    args: dict[str, Any],
    *,
    auth_mode: AuthMode = AuthMode.REQUEST_APPROVAL,
) -> dict[str, Any]:
    token = bind_agent_runtime_context(
        AgentRuntimeContext(
            session_factory=session_factory,
            session_id="sess-goals",
            auth_mode=auth_mode,
            budget=ToolCallBudget(),
        )
    )
    try:
        raw = await tool.ainvoke(args)
        return dict(json.loads(raw))
    finally:
        reset_agent_runtime_context(token)


async def proposal_ids(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[tuple[str, str, str | None]]:
    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT id, proposal_type, status FROM agent_proposals"
                    " WHERE session_id = 'sess-goals'"
                )
            )
        ).all()
    return [(cast(str, row[0]), cast(str, row[1]), row[2]) for row in rows]


def core_payload(**overrides: Any) -> GoalCreateCore:
    values: dict[str, Any] = {
        "goal_type": "SKILL",
        "title": "四周内学会 Agent 工程",
        "target_date": date(2026, 10, 27),
        "daily_minutes": 60,
    }
    values.update(overrides)
    return GoalCreateCore(**values)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# 迁移结构（0034）。


@pytest.mark.anyio
async def test_migration_0034_creates_learning_goals(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)

    async with aiosqlite.connect(db_path) as connection:
        version = await (await connection.execute("PRAGMA user_version")).fetchone()
        columns = {
            cast(str, row[1])
            for row in await (
                await connection.execute("PRAGMA table_info(learning_goals)")
            ).fetchall()
        }
        indexes = {
            cast(str, row[1])
            for row in await (
                await connection.execute("PRAGMA index_list(learning_goals)")
            ).fetchall()
        }
        partial = await (
            await connection.execute(
                "SELECT sql FROM sqlite_master WHERE name = 'idx_learning_goals_one_active'"
            )
        ).fetchone()
        assert partial is not None
        assert "WHERE status = 'ACTIVE'" in cast(str, partial[0])

    assert version == (supported_user_version(),)
    assert columns == {
        "id",
        "course_id",
        "goal_type",
        "title",
        "target_date",
        "daily_minutes",
        "target_score",
        "scope_source",
        "scope_confirmed",
        "status",
        "created_at",
        "updated_at",
    }
    assert "idx_learning_goals_course" in indexes
    assert "idx_learning_goals_one_active" in indexes


@pytest.mark.anyio
async def test_partial_unique_index_allows_active_plus_terminal(tmp_path: Path) -> None:
    """单空间单 ACTIVE 由部分唯一索引在存储层保证；终态目标不占名额（跨空间不受限）。"""
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)

    def insert(goal_id: str, course_id: str, status: str) -> str:
        return (
            "INSERT INTO learning_goals (id, course_id, goal_type, title, scope_source, "
            "scope_confirmed, status, created_at, updated_at) VALUES ("
            f"'{goal_id}', '{course_id}', 'SKILL', '目标', 'USER_CONFIRMED', 1, "
            f"'{status}', '{NOW}', '{NOW}')"
        )

    async with aiosqlite.connect(db_path) as connection:
        await connection.execute(
            f"INSERT INTO courses (id, name, learning_context, depth, status, created_at, "
            f"updated_at) VALUES ('{COURSE_ID}', 'A', 'INTEREST', 'BEGINNER', 'ACTIVE', "
            f"'{NOW}', '{NOW}')"
        )
        await connection.execute(insert("g-1", COURSE_ID, "ACTIVE"))
        await connection.execute(insert("g-2", COURSE_ID, "COMPLETED"))
        await connection.execute(insert("g-3", COURSE_ID, "ARCHIVED"))
        await connection.commit()
        with pytest.raises(sqlite3.IntegrityError):
            await connection.execute(insert("g-4", COURSE_ID, "ACTIVE"))
        # 跨空间不受限：另一门课程各自持有 ACTIVE。
        await connection.execute(
            f"INSERT INTO courses (id, name, learning_context, depth, status, created_at, "
            f"updated_at) VALUES ('{COURSE_OTHER}', 'B', 'INTEREST', 'BEGINNER', 'ACTIVE', "
            f"'{NOW}', '{NOW}')"
        )
        await connection.execute(insert("g-5", COURSE_OTHER, "ACTIVE"))
        await connection.commit()


# ---------------------------------------------------------------------------
# 领域 Service 语义。


@pytest.mark.anyio
async def test_create_rejects_unconfirmed_ai_inferred_scope(tmp_path: Path) -> None:
    """AI_INFERRED 未确认不能生效（spec 用户故事 6）：领域核心入口即拒绝。"""
    with pytest.raises(ValidationError):
        core_payload(
            scope_source=GoalScopeSource.AI_INFERRED,
            scope_confirmed=False,
        )


@pytest.mark.anyio
async def test_create_single_active_per_course(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        async with session_factory() as session, session.begin():
            course = await CourseService.get(session, COURSE_ID)
            assert course is not None
            goal = await GoalService.create_core(session, course, core_payload())
            assert goal.status == GoalStatus.ACTIVE.value

        async with session_factory() as session, session.begin():
            course = await CourseService.get(session, COURSE_ID)
            assert course is not None
            with pytest.raises(CodedHTTPException) as exc_info:
                await GoalService.create_core(session, course, core_payload(title="第二个目标"))
        assert exc_info.value.code == "GOAL_ACTIVE_EXISTS"

        # 换新 ACTIVE 前先归档旧目标：归档后可再创建（用户故事 3 的正向路径）。
        async with session_factory() as session, session.begin():
            goal = await GoalService.get(session, goal.id)
            assert goal is not None
            await GoalService.set_status_core(session, goal, GoalStatus.ARCHIVED)
        async with session_factory() as session, session.begin():
            course = await CourseService.get(session, COURSE_ID)
            assert course is not None
            replacement = await GoalService.create_core(
                session, course, core_payload(title="新目标")
            )
        assert replacement.status == GoalStatus.ACTIVE.value


@pytest.mark.anyio
async def test_cross_course_active_goals_not_limited(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory, COURSE_ID, name="A")
        await seed_course(session_factory, COURSE_OTHER, name="B")
        async with session_factory() as session, session.begin():
            for course_id in (COURSE_ID, COURSE_OTHER):
                course = await CourseService.get(session, course_id)
                assert course is not None
                await GoalService.create_core(session, course, core_payload())


@pytest.mark.anyio
async def test_edit_and_status_only_for_active_goals(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        async with session_factory() as session, session.begin():
            course = await CourseService.get(session, COURSE_ID)
            assert course is not None
            goal = await GoalService.create_core(session, course, core_payload())

            await GoalService.update_core(
                session, goal, GoalUpdate(daily_minutes=90, target_date=date(2026, 11, 30))
            )
            assert goal.daily_minutes == 90
            assert goal.target_date == "2026-11-30"

            await GoalService.set_status_core(session, goal, GoalStatus.COMPLETED)
            assert goal.status == GoalStatus.COMPLETED.value

            with pytest.raises(CodedHTTPException) as edit_exc:
                await GoalService.update_core(session, goal, GoalUpdate(daily_minutes=30))
            assert edit_exc.value.code == "GOAL_NOT_ACTIVE"
            with pytest.raises(CodedHTTPException) as archive_exc:
                await GoalService.set_status_core(session, goal, GoalStatus.ARCHIVED)
            assert archive_exc.value.code == "GOAL_NOT_ACTIVE"


@pytest.mark.anyio
async def test_course_soft_delete_hides_goals_and_restore_recovers(tmp_path: Path) -> None:
    """课程软删后目标查询不可见（查询期过滤）、恢复即恢复——与 Record 同模式。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        async with session_factory() as session, session.begin():
            course = await CourseService.get(session, COURSE_ID)
            assert course is not None
            goal = await GoalService.create_core(session, course, core_payload())

        async with session_factory() as session:
            assert await GoalService.get(session, goal.id) is not None

        async with session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE courses SET deleted_at = :now, updated_at = :now WHERE id = :id"),
                {"now": NOW, "id": COURSE_ID},
            )

        async with session_factory() as session:
            assert await GoalService.get(session, goal.id) is None
            assert await GoalService.list_for_course(session, COURSE_ID) is None

        async with session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE courses SET deleted_at = NULL WHERE id = :id"),
                {"id": COURSE_ID},
            )
        async with session_factory() as session:
            recovered = await GoalService.get(session, goal.id)
            assert recovered is not None
            assert recovered.status == GoalStatus.ACTIVE.value


# ---------------------------------------------------------------------------
# 课程嵌套路由集成。


@pytest.mark.anyio
async def test_goal_routes_crud_and_status_flow(tmp_path: Path) -> None:
    async with goal_client(tmp_path) as client:
        created = await client.post(
            "/api/courses",
            json={"name": "Agent 工程", "learning_context": "INTEREST", "depth": "INTERMEDIATE"},
        )
        assert created.status_code == 201
        course_id = created.json()["id"]

        # 页面创建恒为用户确认范围。
        goal = await client.post(
            f"/api/courses/{course_id}/goals",
            json={
                "goal_type": "SKILL",
                "title": "  四周内学会 Agent 工程  ",
                "target_date": "2026-10-27",
                "daily_minutes": 60,
            },
        )
        assert goal.status_code == 201
        goal_body = goal.json()
        goal_id = goal_body["id"]
        assert goal_body["title"] == "四周内学会 Agent 工程"
        assert goal_body["scope_source"] == "USER_CONFIRMED"
        assert goal_body["scope_confirmed"] is True
        assert goal_body["status"] == "ACTIVE"

        # 单空间单 ACTIVE：第二个 ACTIVE 创建被稳定错误码拒绝。
        conflict = await client.post(
            f"/api/courses/{course_id}/goals",
            json={"goal_type": "EXAM", "title": "备考"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "GOAL_ACTIVE_EXISTS"

        # 编辑期限与投入；显式 null 清空可空字段。
        patched = await client.patch(
            f"/api/courses/{course_id}/goals/{goal_id}",
            json={"daily_minutes": 90, "target_date": None},
        )
        assert patched.status_code == 200
        assert patched.json()["daily_minutes"] == 90
        assert patched.json()["target_date"] is None

        # 完成后终态：再次完成 / 编辑 / 归档均 409 GOAL_NOT_ACTIVE。
        completed = await client.post(f"/api/courses/{course_id}/goals/{goal_id}/complete")
        assert completed.status_code == 200
        assert completed.json()["status"] == "COMPLETED"
        again = await client.post(f"/api/courses/{course_id}/goals/{goal_id}/complete")
        assert again.status_code == 409
        assert again.json()["code"] == "GOAL_NOT_ACTIVE"
        stale_edit = await client.patch(
            f"/api/courses/{course_id}/goals/{goal_id}",
            json={"daily_minutes": 30},
        )
        assert stale_edit.status_code == 409

        # 终态目标不占 ACTIVE 名额：可再建新目标。
        replacement = await client.post(
            f"/api/courses/{course_id}/goals",
            json={"goal_type": "CUSTOM", "title": "新目标"},
        )
        assert replacement.status_code == 201

        # 列表：ACTIVE 在前。
        listed = await client.get(f"/api/courses/{course_id}/goals")
        assert listed.status_code == 200
        statuses = [row["status"] for row in listed.json()]
        assert statuses == ["ACTIVE", "COMPLETED"]


@pytest.mark.anyio
async def test_goal_routes_not_found_and_course_soft_delete(tmp_path: Path) -> None:
    async with goal_client(tmp_path) as client:
        created = await client.post(
            "/api/courses",
            json={"name": "机器学习", "learning_context": "INTEREST", "depth": "BEGINNER"},
        )
        course_id = created.json()["id"]
        goal = await client.post(
            f"/api/courses/{course_id}/goals",
            json={"goal_type": "READING", "title": "读完三篇论文"},
        )
        assert goal.status_code == 201

        missing_course = await client.get(f"/api/courses/{UNKNOWN_ID}/goals")
        assert missing_course.status_code == 404
        assert missing_course.json()["code"] == "COURSE_NOT_FOUND"

        missing_goal = await client.patch(
            f"/api/courses/{course_id}/goals/{UNKNOWN_ID}",
            json={"daily_minutes": 30},
        )
        assert missing_goal.status_code == 404
        assert missing_goal.json()["code"] == "GOAL_NOT_FOUND"

        # 嵌套路径归属校验：A 课路径不能改动 B 课的目标（错配按不可见处理）。
        other = await client.post(
            "/api/courses",
            json={"name": "另一门课", "learning_context": "INTEREST", "depth": "BEGINNER"},
        )
        other_id = other.json()["id"]
        mismatched = await client.patch(
            f"/api/courses/{other_id}/goals/{goal.json()['id']}",
            json={"daily_minutes": 30},
        )
        assert mismatched.status_code == 404
        assert mismatched.json()["code"] == "GOAL_NOT_FOUND"
        mismatched_complete = await client.post(
            f"/api/courses/{other_id}/goals/{goal.json()['id']}/complete"
        )
        assert mismatched_complete.status_code == 404
        # 目标事实未被错配路径触碰。
        untouched = await client.get(f"/api/courses/{course_id}/goals")
        assert [row["status"] for row in untouched.json()] == ["ACTIVE"]

        # 课程软删 → 目标查询不可见（404，与课程缺失同码）；恢复即恢复。
        soft_deleted = await client.delete(f"/api/courses/{course_id}")
        assert soft_deleted.status_code in (200, 204)
        hidden = await client.get(f"/api/courses/{course_id}/goals")
        assert hidden.status_code == 404
        assert hidden.json()["code"] == "COURSE_NOT_FOUND"


# ---------------------------------------------------------------------------
# Agent 工具：确认卡（默认档）、直执行（自动档）、结构化拒绝与只读查询。


@pytest.mark.anyio
async def test_create_goal_proposal_confirm_applies_ai_inferred_scope(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)

        result = await invoke_tool(
            create_goal,
            session_factory,
            {
                "course_id": COURSE_ID,
                "goal_type": "SKILL",
                "title": "四周内学会 Agent 工程",
                "target_date": "2026-10-27",
                "daily_minutes": 60,
            },
        )
        assert result["ok"] is True
        proposal = result["proposals"][0]
        assert proposal["action"] == "create_goal"
        assert proposal["status"] == "PENDING"

        # 确认前零目标事实。
        assert await goal_row_count(session_factory) == 0

        async with session_factory() as session:
            confirmed = await ProposalService.confirm(session, proposal["proposal_id"])
        assert confirmed.status.value == "APPLIED"
        assert confirmed.result is not None
        assert set(confirmed.result.keys()) == {"goal_id", "course_id"}

        goal_id = cast(str, confirmed.result["goal_id"])
        row = await goal_row(session_factory, goal_id)
        assert row["scope_source"] == "AI_INFERRED"  # 确认卡即用户确认
        assert row["scope_confirmed"] is True
        assert row["status"] == "ACTIVE"

        # 确认路径回接写 operation 行（执行事实，ADR-0026）。
        assert await operation_action_of(session_factory, goal_id) == "create_goal"


@pytest.mark.anyio
async def test_create_goal_single_active_rejected_at_submit(tmp_path: Path) -> None:
    """提交时快照读取器拒绝（零提案，模型即时转述「先完成或归档」）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)

        result = await invoke_tool(
            create_goal,
            session_factory,
            {"course_id": COURSE_ID, "goal_type": "EXAM", "title": "备考"},
        )
        assert result == {"ok": False, "error": "GOAL_ACTIVE_EXISTS", "proposals": []}
        assert await proposal_ids(session_factory) == []


@pytest.mark.anyio
async def test_create_goal_missing_fields_reported_for_followup(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        result = await invoke_tool(create_goal, session_factory, {"course_id": COURSE_ID})
        assert result["ok"] is False
        assert "goal_type" in result["missing"]
        assert "title" in result["missing"]


@pytest.mark.anyio
async def test_create_goal_course_missing_rejected_at_submit(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        result = await invoke_tool(
            create_goal,
            session_factory,
            {"course_id": UNKNOWN_ID, "goal_type": "SKILL", "title": "目标"},
        )
        assert result == {"ok": False, "error": "COURSE_NOT_FOUND", "proposals": []}


@pytest.mark.anyio
async def test_create_goal_auto_mode_executes_directly(tmp_path: Path) -> None:
    """AUTO_APPROVE × L1 → 直执行：目标直接落库 + SUCCEEDED operation 行。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)

        result = await invoke_tool(
            create_goal,
            session_factory,
            {
                "course_id": COURSE_ID,
                "goal_type": "SKILL",
                "title": "四周内学会 Agent 工程",
                "daily_minutes": 60,
            },
            auth_mode=AuthMode.AUTO_APPROVE,
        )
        assert result["ok"] is True
        executed = result["executed"]
        assert executed["action"] == "create_goal"
        assert executed["level"] == "L1"

        goal_id = cast(str, executed["result"]["goal_id"])
        row = await goal_row(session_factory, goal_id)
        assert row["scope_source"] == "AI_INFERRED"
        assert row["scope_confirmed"] is True
        assert await operation_action_of(session_factory, goal_id) == "create_goal"


@pytest.mark.anyio
async def test_update_goal_confirm_applies_fields_and_status(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)

        result = await invoke_tool(
            update_goal,
            session_factory,
            {"goal_id": GOAL_ID, "daily_minutes": 90, "target_date": "2026-11-30"},
        )
        assert result["ok"] is True
        proposal_id = result["proposals"][0]["proposal_id"]

        async with session_factory() as session:
            confirmed = await ProposalService.confirm(session, proposal_id)
        assert confirmed.status.value == "APPLIED"
        assert confirmed.result is not None
        assert confirmed.result["before"] == {"target_date": "2026-10-27", "daily_minutes": 60}
        assert confirmed.result["after"] == {"target_date": "2026-11-30", "daily_minutes": 90}

        # 状态流转走同一动作：完成。
        done = await invoke_tool(
            update_goal, session_factory, {"goal_id": GOAL_ID, "status": "COMPLETED"}
        )
        async with session_factory() as session:
            confirmed_done = await ProposalService.confirm(
                session, done["proposals"][0]["proposal_id"]
            )
        assert confirmed_done.result is not None
        assert confirmed_done.result["after_status"] == "COMPLETED"

        # 终态后再改 → 确认失败留稳定错误码（可重试语义：先恢复 ACTIVE 不存在，
        # 如实 FAILED）。
        stale = await invoke_tool(
            update_goal, session_factory, {"goal_id": GOAL_ID, "daily_minutes": 30}
        )
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc_info:
                await ProposalService.confirm(session, stale["proposals"][0]["proposal_id"])
        assert exc_info.value.code == "PROPOSAL_APPLY_FAILED"
        assert exc_info.value.params == {"errorCode": "GOAL_NOT_ACTIVE"}
        status, error_code, _ = await proposal_row_of(
            session_factory, stale["proposals"][0]["proposal_id"]
        )
        assert (status, error_code) == ("FAILED", "GOAL_NOT_ACTIVE")


@pytest.mark.anyio
async def test_update_goal_snapshot_stale_when_edited_before_confirm(tmp_path: Path) -> None:
    """提交后用户手动改过目标 → 确认时快照比对失效（OPERATION_SNAPSHOT_STALE）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)

        result = await invoke_tool(
            update_goal, session_factory, {"goal_id": GOAL_ID, "daily_minutes": 90}
        )
        proposal_id = result["proposals"][0]["proposal_id"]

        await run_sql(
            "UPDATE learning_goals SET daily_minutes = 45, updated_at = :now WHERE id = :id",
            {"now": "2026-09-29T09:00:00.000000Z", "id": GOAL_ID},
            session_factory,
        )

        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc_info:
                await ProposalService.confirm(session, proposal_id)
        assert exc_info.value.code == "PROPOSAL_APPLY_FAILED"
        assert exc_info.value.params == {"errorCode": "OPERATION_SNAPSHOT_STALE"}
        status, error_code, _ = await proposal_row_of(session_factory, proposal_id)
        assert (status, error_code) == ("FAILED", "OPERATION_SNAPSHOT_STALE")


@pytest.mark.anyio
async def test_list_goals_returns_active_first_and_not_found_guides_back(
    tmp_path: Path,
) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)  # ACTIVE
        await seed_goal(session_factory, "90000000-0000-4000-8000-000000000002", status="COMPLETED")

        result = await invoke_tool(list_goals, session_factory, {"course_id": COURSE_ID})
        assert result["ok"] is True
        assert [row["status"] for row in result["goals"]] == ["ACTIVE", "COMPLETED"]
        assert result["goals"][0]["id"] == GOAL_ID
        assert result["total"] == 2

        missing = await invoke_tool(list_goals, session_factory, {"course_id": UNKNOWN_ID})
        assert missing["ok"] is False
        assert "search_courses" in missing["message"]


@pytest.mark.anyio
async def test_get_goal_returns_full_fields_and_not_found_guides_back(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)

        result = await invoke_tool(get_goal, session_factory, {"goal_id": GOAL_ID})
        assert result["ok"] is True
        goal = result["goal"]
        assert goal["title"] == "四周内学会 Agent 工程"
        assert goal["scope_source"] == "AI_INFERRED"
        assert goal["scope_confirmed"] is True

        missing = await invoke_tool(
            get_goal, session_factory, {"goal_id": "90000000-0000-4000-8000-00000000dead"}
        )
        assert missing["ok"] is False
        assert "list_goals" in missing["message"]


async def goal_row_count(session_factory: async_sessionmaker[AsyncSession]) -> int:
    async with session_factory() as session:
        return cast(
            int,
            (await session.execute(text("SELECT count(*) FROM learning_goals"))).scalar_one(),
        )


async def proposal_row_of(
    session_factory: async_sessionmaker[AsyncSession], proposal_id: str
) -> tuple[str, str | None, str | None]:
    async with session_factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT status, error_code, snapshot_json FROM agent_proposals WHERE id = :id"
                ),
                {"id": proposal_id},
            )
        ).one()
    return (cast(str, row[0]), row[1], row[2])


async def operation_action_of(
    session_factory: async_sessionmaker[AsyncSession], goal_id: str
) -> str | None:
    """按 result.goal_id 找 operation 行的 action（确认与直执行两路径通用）。"""
    async with session_factory() as session:
        rows = (
            await session.execute(text("SELECT action, result_json FROM agent_operations"))
        ).all()
    for action, result_json in rows:
        if result_json and cast(str, result_json).find(f'"{goal_id}"') >= 0:
            return cast(str, action)
    return None
