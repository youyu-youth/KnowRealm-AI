"""计划编辑、完成与重生成（通用 Agent 第三阶段工单 03）：迁移 0036、锁定容量
感知排期、项级编辑 / 完成 / 跳过（user_locked、completed_at、USER_MANUAL 审计、
learning_events 与 user_concept_mastery 零写入）、重生成版本链（SUPERSEDED 只读、
user_locked 原样带入）、历史版本只读查询、确认卡编辑落库与校验、Agent 工具
确认与授权行为。"""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import aiosqlite
import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import create_database
from app.db.migrations import run_migrations, supported_user_version
from app.modules.agent.runs.retry import retry_standalone_operation
from app.modules.agent.runs.schemas import AuthMode
from app.modules.agent.runtime import (
    AgentRuntimeContext,
    ToolCallBudget,
    bind_agent_runtime_context,
    reset_agent_runtime_context,
)
from app.modules.agent.tools.complete_plan_item import complete_plan_item
from app.modules.agent.tools.confirm_plan import confirm_plan
from app.modules.agent.tools.regenerate_plan import regenerate_plan
from app.modules.agent.tools.update_plan_item import update_plan_item
from app.modules.learning_plan.generation import (
    PlanGenerationOutcome,
    PlanGenerationService,
)
from app.modules.learning_plan.scheduling import (
    ScheduleConstraints,
    local_today,
    pack_schedule,
    pack_schedule_with_fixed,
)
from app.modules.learning_plan.schemas import (
    GoalUpdate,
    PlanConfirmCore,
    PlanItemType,
    PlanItemUpdate,
    PlanRegenerateCore,
    PlanRegenerateItem,
    PlanRegeneratePhase,
)
from app.modules.learning_plan.service import (
    GoalService,
    PlanItemService,
    PlanService,
)
from app.modules.library.proposals import ProposalService
from app.modules.settings.config import LlmProviderConfig
from app.shared.errors import CodedHTTPException

TOKEN = "test-launch-token"
# 时间锚与产品排期重算同源（local_today，提交日锚）：UTC 日期在本地凌晨
# 会比本地早一天，锚点错位使「起点回挪」防线误拒全部提交（08 收口实锤）。
# LANDED 是另一锚：版本头 effective_from/to 的落库日（产品定稿 UTC，
# service._next_version），两者凌晨 0~8 点差一天、断言各锚各的源。
TODAY = local_today()
LANDED = datetime.now(UTC).date().isoformat()
NOW = TODAY.isoformat() + "T08:00:00.000000Z"
COURSE_ID = "c0000000-0000-4000-8000-000000000001"
GOAL_ID = "90000000-0000-4000-8000-000000000001"
RECORD_ID = "a0000000-0000-4000-8000-000000000001"
RECORD_OTHER_COURSE = "a0000000-0000-4000-8000-000000000002"
UNKNOWN_ID = "90000000-0000-4000-8000-00000000dead"
PLAN_ID = "70000000-0000-4000-8000-000000000001"
ITEM_ID = "d0000000-0000-4000-8000-000000000001"
ITEM_ID_2 = "d0000000-0000-4000-8000-000000000002"
TEST_PROVIDER = LlmProviderConfig(
    base_url="http://127.0.0.1:1/v1",
    api_key="test-key",
    model="test-model",
)


# ---------------------------------------------------------------------------
# 夹具与种子。


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
async def plan_app(
    tmp_path: Path,
) -> AsyncGenerator[tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession]]]:
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
            yield client, app.state.session_factory


async def run_sql(
    sql: str,
    params: dict[str, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(text(sql), params)


async def seed_course(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await run_sql(
        "INSERT INTO courses (id, name, learning_context, depth, status, created_at, "
        "updated_at) VALUES (:id, 'Agent 工程', 'INTEREST', 'INTERMEDIATE', 'ACTIVE', "
        ":now, :now)",
        {"id": COURSE_ID, "now": NOW},
        session_factory,
    )


async def seed_goal(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    daily_minutes: int = 60,
    target_date: str | None = None,
) -> None:
    await run_sql(
        "INSERT INTO learning_goals (id, course_id, goal_type, title, target_date, "
        "daily_minutes, scope_source, scope_confirmed, status, created_at, updated_at) "
        "VALUES (:id, :course_id, 'SKILL', '四周内学会 Agent 工程', :target_date, "
        ":daily_minutes, 'AI_INFERRED', 1, 'ACTIVE', :now, :now)",
        {
            "id": GOAL_ID,
            "course_id": COURSE_ID,
            "target_date": target_date or (TODAY + timedelta(days=28)).isoformat(),
            "daily_minutes": daily_minutes,
            "now": NOW,
        },
        session_factory,
    )


async def seed_record(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await run_sql(
        "INSERT INTO records (id, course_id, capture_type, title, status, duration_ms, "
        "created_at, updated_at) VALUES (:id, :course_id, 'DOCUMENT_IMPORT', "
        "'第 1 讲 Agent 概论', 'SUMMARY_READY', 0, :now, :now)",
        {"id": RECORD_ID, "course_id": COURSE_ID, "now": NOW},
        session_factory,
    )


async def seed_plan(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    plan_id: str = PLAN_ID,
    status: str = "ACTIVE",
    plan_version: int = 1,
) -> None:
    await run_sql(
        "INSERT INTO learning_plans (id, goal_id, plan_version, status, effective_from, "
        "effective_to, created_at, updated_at) VALUES (:id, :goal_id, :plan_version, "
        ":status, :from, NULL, :now, :now)",
        {
            "id": plan_id,
            "goal_id": GOAL_ID,
            "plan_version": plan_version,
            "status": status,
            "from": TODAY.isoformat(),
            "now": NOW,
        },
        session_factory,
    )


async def seed_item(
    session_factory: async_sessionmaker[AsyncSession],
    item_id: str,
    *,
    plan_id: str = PLAN_ID,
    content: str = "学习第 1 讲",
    scheduled_date: str | None = None,
    minutes: int = 45,
    status: str = "PENDING",
    user_locked: bool = False,
    completed_at: str | None = None,
    priority: int = 0,
    phase_title: str = "第一阶段",
    record_id: str | None = None,
) -> None:
    await run_sql(
        "INSERT INTO learning_plan_items (id, plan_id, action_type, content, record_id, "
        "concept_id, phase_title, priority, estimated_minutes, scheduled_date, status, "
        "user_locked, completed_at, reason_json, created_at, updated_at) VALUES "
        "(:id, :plan_id, 'STUDY_RECORD', :content, :record_id, NULL, :phase_title, "
        ":priority, :minutes, :scheduled_date, :status, :user_locked, :completed_at, "
        '\'{"reason": "打好基础"}\', :now, :now)',
        {
            "id": item_id,
            "plan_id": plan_id,
            "content": content,
            "record_id": record_id,
            "phase_title": phase_title,
            "priority": priority,
            "minutes": minutes,
            "scheduled_date": scheduled_date or TODAY.isoformat(),
            "status": status,
            "user_locked": 1 if user_locked else 0,
            "completed_at": completed_at,
            "now": NOW,
        },
        session_factory,
    )


async def scalar(
    session_factory: async_sessionmaker[AsyncSession], sql: str, params: dict[str, object]
) -> Any:
    async with session_factory() as session:
        return await session.scalar(text(sql), params)


async def table_count(session_factory: async_sessionmaker[AsyncSession], table: str) -> int:
    return cast(int, await scalar(session_factory, f"SELECT COUNT(*) FROM {table}", {}))


async def load_item(
    session_factory: async_sessionmaker[AsyncSession], item_id: str
) -> dict[str, Any]:
    async with session_factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT content, scheduled_date, estimated_minutes, status, "
                    "user_locked, completed_at FROM learning_plan_items WHERE id = :id"
                ),
                {"id": item_id},
            )
        ).one()
    return {
        "content": row[0],
        "scheduled_date": row[1],
        "estimated_minutes": row[2],
        "status": row[3],
        "user_locked": row[4],
        "completed_at": row[5],
    }


async def load_plan(
    session_factory: async_sessionmaker[AsyncSession], plan_id: str
) -> dict[str, Any]:
    async with session_factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT plan_version, status, effective_to FROM learning_plans WHERE id = :id"
                ),
                {"id": plan_id},
            )
        ).one()
    return {"plan_version": row[0], "status": row[1], "effective_to": row[2]}


async def confirm_plan_via_tool(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    minutes: tuple[int, ...] = (60, 30, 45),
) -> str:
    """经 confirm_plan 工具确认一份草案，返回落库计划 id（夹具捷径）。"""
    dates = pack_schedule(
        list(minutes),
        ScheduleConstraints(start_date=TODAY, daily_minutes=60),
    )
    payload = {
        "goal_id": GOAL_ID,
        "phases": [
            {
                "title": "第一阶段",
                "items": [
                    {
                        "action_type": "CUSTOM",
                        "content": f"任务 {index + 1}",
                        "estimated_minutes": value,
                        "reason": f"理由 {index + 1}",
                        "record_id": None,
                        "concept_id": None,
                        "scheduled_date": value_date.isoformat(),
                    }
                    for index, (value, value_date) in enumerate(zip(minutes, dates, strict=True))
                ],
            }
        ],
    }
    result = await invoke_tool(confirm_plan, session_factory, payload)
    assert result["ok"] is True, result
    proposal_id = result["proposals"][0]["proposal_id"]
    async with session_factory() as session:
        confirmed = await ProposalService.confirm(session, proposal_id)
    assert confirmed.result is not None
    return cast(str, confirmed.result["plan_id"])


async def invoke_tool(
    tool: Any,
    session_factory: async_sessionmaker[AsyncSession],
    args: dict[str, Any],
    *,
    auth_mode: AuthMode = AuthMode.REQUEST_APPROVAL,
    llm_provider: LlmProviderConfig | None = TEST_PROVIDER,
) -> dict[str, Any]:
    token = bind_agent_runtime_context(
        AgentRuntimeContext(
            session_factory=session_factory,
            session_id="sess-plan-editing",
            auth_mode=auth_mode,
            llm_provider=llm_provider,
            budget=ToolCallBudget(),
        )
    )
    try:
        raw = await tool.ainvoke(args)
        return dict(json.loads(raw))
    finally:
        reset_agent_runtime_context(token)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# 迁移 0036 与排期器扩展。


@pytest.mark.anyio
async def test_migration_0036_adds_completed_at(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    async with aiosqlite.connect(db_path) as db:
        columns = {
            row[1] for row in await db.execute_fetchall("PRAGMA table_info(learning_plan_items)")
        }
    assert "completed_at" in columns
    # user_version 断言随迁移发现自动跟随（C2 先例）。
    version_rows: list[Any] = []
    async with aiosqlite.connect(db_path) as db:
        version_rows = list(await db.execute_fetchall("PRAGMA user_version"))
    assert cast(int, version_rows[0][0]) == supported_user_version() == 40


def test_pack_schedule_with_fixed_golden_samples() -> None:
    """锁定容量感知铺排黄金样本（手算）：60/日预算，锁定项占 D1 40 分钟。"""
    start = date(2026, 10, 26)
    constraints = ScheduleConstraints(start_date=start, daily_minutes=60)
    fixed = [(start, 40)]
    # D1 剩余 20 < 30 → 首个草案项翻日；D2 已用 30 剩 30 < 60 → 次项再翻日。
    assert pack_schedule_with_fixed([30, 60], fixed, constraints) == [
        start + timedelta(days=1),
        start + timedelta(days=2),
    ]
    # 剩余容量恰好装下（20 ≤ 20）不翻日；锁定项自身不受期限约束。
    assert pack_schedule_with_fixed([20], fixed, constraints) == [start]
    # 草案项翻过期限即不可行（D2 装下 30 后剩 30 < 40 → D3 越界）。
    tight = ScheduleConstraints(
        start_date=start, deadline=start + timedelta(days=1), daily_minutes=60
    )
    assert pack_schedule_with_fixed([30], fixed, tight) == [start + timedelta(days=1)]
    with pytest.raises(Exception) as excinfo:
        pack_schedule_with_fixed([30, 40], fixed, tight)
    assert "容量" in str(excinfo.value)
    # 无锁定占用时与 pack_schedule 逐位一致（等价回归）。
    assert pack_schedule_with_fixed([60, 30], [], constraints) == pack_schedule(
        [60, 30], constraints
    )


# ---------------------------------------------------------------------------
# 项级 Service：编辑置 user_locked、完成时间戳、跳过清空、完成零学习证据。


@pytest.mark.anyio
async def test_item_update_core_sets_user_locked(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)
        await seed_plan(session_factory)
        await seed_item(session_factory, ITEM_ID)

        async with session_factory() as session, session.begin():
            item = await PlanItemService.get_for_plan(session, PLAN_ID, ITEM_ID)
            assert item is not None
            await PlanItemService.update_core(
                session,
                item,
                PlanItemUpdate(
                    scheduled_date=TODAY + timedelta(days=3),
                    estimated_minutes=90,
                    content="精读第 1 讲并做笔记",
                ),
            )

        row = await load_item(session_factory, ITEM_ID)
        assert row["scheduled_date"] == (TODAY + timedelta(days=3)).isoformat()
        assert row["estimated_minutes"] == 90
        assert row["content"] == "精读第 1 讲并做笔记"
        assert row["user_locked"] == 1


@pytest.mark.anyio
async def test_item_complete_and_skip_semantics(tmp_path: Path) -> None:
    """完成 = DONE + completed_at；跳过清空时间戳；两表零写入（spec 用户故事 17）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)
        await seed_plan(session_factory)
        await seed_item(session_factory, ITEM_ID)

        async with session_factory() as session, session.begin():
            item = await PlanItemService.get_for_plan(session, PLAN_ID, ITEM_ID)
            assert item is not None
            await PlanItemService.complete_core(session, item)
        row = await load_item(session_factory, ITEM_ID)
        assert row["status"] == "DONE" and row["completed_at"] is not None
        # 完成语义边界：不产 learning_event、不动 user_concept_mastery。
        assert await table_count(session_factory, "learning_events") == 0
        assert await table_count(session_factory, "user_concept_mastery") == 0

        async with session_factory() as session, session.begin():
            item = await PlanItemService.get_for_plan(session, PLAN_ID, ITEM_ID)
            assert item is not None
            await PlanItemService.skip_core(session, item)
        row = await load_item(session_factory, ITEM_ID)
        assert row["status"] == "SKIPPED" and row["completed_at"] is None
        assert await table_count(session_factory, "learning_events") == 0
        assert await table_count(session_factory, "user_concept_mastery") == 0


@pytest.mark.anyio
async def test_item_mutation_rejected_for_superseded_version(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)
        await seed_plan(session_factory, status="SUPERSEDED")
        await seed_item(session_factory, ITEM_ID)

        async with session_factory() as session, session.begin():
            item = await PlanItemService.get_for_plan(session, PLAN_ID, ITEM_ID)
            assert item is not None
            with pytest.raises(CodedHTTPException) as excinfo:
                await PlanItemService.update_core(session, item, PlanItemUpdate(content="改内容"))
        assert excinfo.value.code == "PLAN_VERSION_NOT_ACTIVE"


# ---------------------------------------------------------------------------
# 重生成：版本链、SUPERSEDED 只读保留（含进度记录）、user_locked 原样带入。


def regenerate_payload() -> PlanRegenerateCore:
    return PlanRegenerateCore(
        goal_id=GOAL_ID,
        phases=[
            PlanRegeneratePhase(
                title="第一阶段",
                items=[
                    PlanRegenerateItem(
                        action_type=PlanItemType.STUDY_RECORD,
                        content="学习第 1 讲",
                        estimated_minutes=45,
                        reason="打好基础",
                        record_id=RECORD_ID,
                        scheduled_date=TODAY,
                        user_locked=True,
                    )
                ],
            ),
            PlanRegeneratePhase(
                title="新草案阶段",
                items=[
                    PlanRegenerateItem(
                        action_type=PlanItemType.CUSTOM,
                        content="新任务",
                        estimated_minutes=60,
                        reason="重排后的新安排",
                        scheduled_date=TODAY + timedelta(days=1),
                        user_locked=False,
                    )
                ],
            ),
        ],
    )


@pytest.mark.anyio
async def test_regenerate_core_version_chain_and_locked_carry(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)
        await seed_record(session_factory)
        await seed_plan(session_factory)
        # 项 1：锁定 + 已完成（进度事实应在旧版本保留，不结转新版本）。
        await seed_item(
            session_factory,
            ITEM_ID,
            user_locked=True,
            status="DONE",
            completed_at=NOW,
        )
        # 项 2：未锁定（重排后由新草案取代）。
        await seed_item(session_factory, ITEM_ID_2, priority=1, minutes=30)

        async with session_factory() as session, session.begin():
            goal = await GoalService.get(session, GOAL_ID)
            assert goal is not None
            new_plan = await PlanService.regenerate_core(session, goal, regenerate_payload())
            new_plan_id = new_plan.id

        old = await load_plan(session_factory, PLAN_ID)
        assert old["status"] == "SUPERSEDED"
        assert old["effective_to"] == LANDED
        # 旧版本只读保留进度记录（含 DONE 与 completed_at）。
        old_item = await load_item(session_factory, ITEM_ID)
        assert old_item["status"] == "DONE" and old_item["completed_at"] == NOW

        new = await load_plan(session_factory, new_plan_id)
        assert new["plan_version"] == 2 and new["status"] == "ACTIVE"
        # 锁定项原样带入新版本：同内容 / 日期 / 时长，user_locked 置位，
        # 状态归 PENDING（完成事实不结转，旧版本可查）。
        async with session_factory() as session:
            items = await PlanService.list_items(session, new_plan_id)
        locked = [item for item in items if item.user_locked]
        assert len(locked) == 1
        assert locked[0].content == "学习第 1 讲"
        assert locked[0].scheduled_date == TODAY.isoformat()
        assert locked[0].estimated_minutes == 45
        assert locked[0].status == "PENDING"
        assert locked[0].completed_at is None
        assert [item.content for item in items if not item.user_locked] == ["新任务"]


# ---------------------------------------------------------------------------
# HTTP 路由：历史版本只读查询 + 项级页面直改（USER_MANUAL 审计）。


async def seed_full_plan(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await seed_course(session_factory)
    await seed_goal(session_factory)
    await seed_record(session_factory)
    await seed_plan(session_factory)
    await seed_item(session_factory, ITEM_ID)
    await seed_item(session_factory, ITEM_ID_2, priority=1, minutes=30, content="做习题")


@pytest.mark.anyio
async def test_routes_plan_history_and_item_mutation(tmp_path: Path) -> None:
    async with plan_app(tmp_path) as (client, session_factory):
        await seed_full_plan(session_factory)

        # 版本列表（新版本在前）。
        response = await client.get(f"/api/courses/{COURSE_ID}/plans", params={"goal_id": GOAL_ID})
        assert response.status_code == 200
        versions = response.json()
        assert [v["plan_version"] for v in versions] == [1]
        assert versions[0]["item_count"] == 2

        # 版本详情（含项与状态）。
        detail = await client.get(f"/api/courses/{COURSE_ID}/plans/{PLAN_ID}")
        assert detail.status_code == 200
        assert detail.json()["items"][0]["completed_at"] is None

        # 就地编辑：即时生效 + user_locked + USER_MANUAL 审计行。
        patched = await client.patch(
            f"/api/courses/{COURSE_ID}/plans/{PLAN_ID}/items/{ITEM_ID}",
            json={
                "scheduled_date": (TODAY + timedelta(days=2)).isoformat(),
                "estimated_minutes": 90,
            },
        )
        assert patched.status_code == 200
        body = patched.json()
        assert body["user_locked"] is True and body["estimated_minutes"] == 90
        row = await load_item(session_factory, ITEM_ID)
        assert row["scheduled_date"] == (TODAY + timedelta(days=2)).isoformat()
        assert row["user_locked"] == 1

        # 完成：DONE + completed_at + 审计；零学习证据写入。
        completed = await client.post(
            f"/api/courses/{COURSE_ID}/plans/{PLAN_ID}/items/{ITEM_ID}/complete"
        )
        assert completed.status_code == 200
        assert completed.json()["status"] == "DONE"
        assert completed.json()["completed_at"] is not None
        assert await table_count(session_factory, "learning_events") == 0
        assert await table_count(session_factory, "user_concept_mastery") == 0

        # 跳过：清空时间戳 + 审计。
        skipped = await client.post(
            f"/api/courses/{COURSE_ID}/plans/{PLAN_ID}/items/{ITEM_ID_2}/skip"
        )
        assert skipped.status_code == 200
        assert skipped.json()["status"] == "SKIPPED"
        assert skipped.json()["completed_at"] is None

        # 显式 null 字段被忽略（三字段均非空语义，不撞 NOT NULL 列炸 500）。
        nullish = await client.patch(
            f"/api/courses/{COURSE_ID}/plans/{PLAN_ID}/items/{ITEM_ID_2}",
            json={"content": "改写后的任务", "estimated_minutes": None},
        )
        assert nullish.status_code == 200
        assert nullish.json()["estimated_minutes"] == 30

        # 全 null 载荷＝零修改语义 → 422 拒绝：不得 200＋数据未变＋
        # SUCCEEDED 审计的虚假改动事实（spec 用户故事 14 成对语义；下方
        # 审计行断言不含本次尝试＝零审计）。
        all_null = await client.patch(
            f"/api/courses/{COURSE_ID}/plans/{PLAN_ID}/items/{ITEM_ID_2}",
            json={"estimated_minutes": None},
        )
        assert all_null.status_code == 422

        # 每次改动各落一条 USER_MANUAL operation（action 与授权触发器如实）。
        async with session_factory() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT action, level, target_type, authorization_json, status "
                        "FROM agent_operations ORDER BY created_at"
                    )
                )
            ).all()
        assert [r[0] for r in rows] == [
            "update_plan_item",
            "complete_plan_item",
            "skip_plan_item",
            "update_plan_item",
        ]
        for row in rows:
            assert row[1] == "L1" and row[2] == "plan_item"
            assert json.loads(row[3])["trigger"] == "USER_MANUAL"
            assert row[4] == "SUCCEEDED"

        # 项不存在 / 计划不存在 → 404 稳定错误码。
        missing = await client.patch(
            f"/api/courses/{COURSE_ID}/plans/{PLAN_ID}/items/{UNKNOWN_ID}",
            json={"content": "改内容"},
        )
        assert missing.status_code == 404
        assert missing.json()["code"] == "PLAN_ITEM_NOT_FOUND"
        no_plan = await client.get(f"/api/courses/{COURSE_ID}/plans/{UNKNOWN_ID}")
        assert no_plan.status_code == 404
        assert no_plan.json()["code"] == "PLAN_NOT_FOUND"


@pytest.mark.anyio
async def test_routes_reject_mutation_on_history_version(tmp_path: Path) -> None:
    async with plan_app(tmp_path) as (client, session_factory):
        await seed_full_plan(session_factory)
        await run_sql(
            "UPDATE learning_plans SET status = 'SUPERSEDED', effective_to = :to WHERE id = :id",
            {"id": PLAN_ID, "to": TODAY.isoformat()},
            session_factory,
        )
        response = await client.post(
            f"/api/courses/{COURSE_ID}/plans/{PLAN_ID}/items/{ITEM_ID}/complete"
        )
        assert response.status_code == 409
        assert response.json()["code"] == "PLAN_VERSION_NOT_ACTIVE"
        # 历史版本详情仍只读可查（含进度记录）。
        detail = await client.get(f"/api/courses/{COURSE_ID}/plans/{PLAN_ID}")
        assert detail.status_code == 200


# ---------------------------------------------------------------------------
# Agent 工具：确认卡 + 授权 + 审计；重生成端到端（L2 卡 → 新版本）。


@pytest.mark.anyio
async def test_update_and_complete_plan_item_tools(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_full_plan(session_factory)

        # 默认档：L1 落提案（确认卡）。
        result = await invoke_tool(
            update_plan_item,
            session_factory,
            {"item_id": ITEM_ID, "estimated_minutes": 120},
        )
        assert result["ok"] is True
        proposal = result["proposals"][0]
        assert proposal["action"] == "update_plan_item"

        async with session_factory() as session:
            confirmed = await ProposalService.confirm(session, proposal["proposal_id"])
        assert confirmed.status.value == "APPLIED"
        assert confirmed.result is not None
        assert confirmed.result["after"] == {"estimated_minutes": 120}
        assert confirmed.result["user_locked"] is True
        row = await load_item(session_factory, ITEM_ID)
        assert row["estimated_minutes"] == 120 and row["user_locked"] == 1
        # Agent 路径同样零学习证据写入。
        assert await table_count(session_factory, "learning_events") == 0
        assert await table_count(session_factory, "user_concept_mastery") == 0

        # 确认路径回写 operation 行（审计）。
        async with session_factory() as session:
            ops = (
                await session.execute(
                    text("SELECT action, status FROM agent_operations WHERE proposal_id = :pid"),
                    {"pid": proposal["proposal_id"]},
                )
            ).all()
        assert ops == [("update_plan_item", "SUCCEEDED")]

        # 项不存在 / 缺字段 → 结构化拒绝（零提案）。
        result = await invoke_tool(
            update_plan_item, session_factory, {"item_id": UNKNOWN_ID, "content": "改"}
        )
        assert result["ok"] is False and result["error"] == "PLAN_ITEM_NOT_FOUND"
        result = await invoke_tool(complete_plan_item, session_factory, {"item_id": UNKNOWN_ID})
        assert result["ok"] is False and result["error"] == "PLAN_ITEM_NOT_FOUND"


@pytest.mark.anyio
async def test_plan_item_tools_auto_approve_direct_execution(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_full_plan(session_factory)

        result = await invoke_tool(
            complete_plan_item,
            session_factory,
            {"item_id": ITEM_ID},
            auth_mode=AuthMode.AUTO_APPROVE,
        )
        assert result["ok"] is True
        executed = result["executed"]
        assert executed["action"] == "complete_plan_item"
        assert executed["result"]["status"] == "DONE"
        assert executed["result"]["completed_at"] is not None
        row = await load_item(session_factory, ITEM_ID)
        assert row["status"] == "DONE"
        assert await table_count(session_factory, "learning_events") == 0
        assert await table_count(session_factory, "user_concept_mastery") == 0


@pytest.mark.anyio
async def test_regenerate_tool_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)
        await seed_record(session_factory)
        await seed_plan(session_factory)
        # 锁定项占 D1 45 分钟（60/日预算 → D1 剩余 15，草案 60 分钟项落 D2）。
        await seed_item(session_factory, ITEM_ID, user_locked=True, minutes=45, content="锁定任务")

        # 无生效计划 → 结构化指引（首次生成走 generate_learning_plan）。
        async def fake_generate(**kwargs: Any) -> PlanGenerationOutcome:
            raise AssertionError("不应触达 LLM")

        await run_sql("DELETE FROM learning_plans", {}, session_factory)
        await run_sql("DELETE FROM learning_plan_items", {}, session_factory)
        monkeypatch.setattr(PlanGenerationService, "generate", staticmethod(fake_generate))
        result = await invoke_tool(regenerate_plan, session_factory, {"goal_id": GOAL_ID})
        assert result["ok"] is False and result["error"] == "PLAN_NOT_FOUND"

        # 重建生效计划（含锁定项）→ 重生成（L2 卡 → 确认 → 新版本）。
        await seed_plan(session_factory)
        await seed_item(session_factory, ITEM_ID, user_locked=True, minutes=45, content="锁定任务")
        draft = PlanConfirmCore.model_validate(
            {
                "goal_id": GOAL_ID,
                "phases": [
                    {
                        "title": "新草案阶段",
                        "items": [
                            {
                                "action_type": "CUSTOM",
                                "content": "新任务",
                                "estimated_minutes": 60,
                                "reason": "重排安排",
                                "record_id": None,
                                "concept_id": None,
                                "scheduled_date": TODAY.isoformat(),
                            }
                        ],
                    }
                ],
            }
        )

        async def fake_generate_draft(**kwargs: Any) -> PlanGenerationOutcome:
            return PlanGenerationOutcome(
                kind="DRAFT", plan=draft, total_minutes=60, materials_used=1
            )

        monkeypatch.setattr(PlanGenerationService, "generate", staticmethod(fake_generate_draft))
        result = await invoke_tool(regenerate_plan, session_factory, {"goal_id": GOAL_ID})
        assert result["ok"] is True, result
        proposal = result["proposals"][0]
        assert proposal["action"] == "regenerate_plan"
        # 载荷：锁定项在前（原样）+ 新草案项（锁定容量感知铺排 → D2）。
        items = [item for phase in proposal["payload"]["phases"] for item in phase["items"]]
        assert items[0]["user_locked"] is True and items[0]["content"] == "锁定任务"
        assert items[0]["scheduled_date"] == TODAY.isoformat()
        assert items[1]["user_locked"] is False
        assert items[1]["scheduled_date"] == (TODAY + timedelta(days=1)).isoformat()

        async with session_factory() as session:
            confirmed = await ProposalService.confirm(session, proposal["proposal_id"])
        assert confirmed.status.value == "APPLIED"
        assert confirmed.result is not None
        assert confirmed.result["superseded_version"] == 1
        assert confirmed.result["plan_version"] == 2
        assert confirmed.result["locked_count"] == 1

        old = await load_plan(session_factory, PLAN_ID)
        assert old["status"] == "SUPERSEDED" and old["effective_to"] == LANDED
        # 新版本：锁定项原样保留。
        async with session_factory() as session:
            new_id = await PlanService.get_active_for_goal(session, GOAL_ID)
            assert new_id is not None
            items_rows = await PlanService.list_items(session, new_id.id)
        locked = [row for row in items_rows if row.user_locked]
        assert len(locked) == 1
        assert locked[0].content == "锁定任务"
        assert locked[0].scheduled_date == TODAY.isoformat()
        assert locked[0].status == "PENDING"


def llm_window_draft() -> PlanConfirmCore:
    """LLM 窗口竞态测试共用的草案替身（与 end_to_end 同形状）。"""
    return PlanConfirmCore.model_validate(
        {
            "goal_id": GOAL_ID,
            "phases": [
                {
                    "title": "新草案阶段",
                    "items": [
                        {
                            "action_type": "CUSTOM",
                            "content": "新任务",
                            "estimated_minutes": 60,
                            "reason": "重排安排",
                            "record_id": None,
                            "concept_id": None,
                            "scheduled_date": TODAY.isoformat(),
                        }
                    ],
                }
            ],
        }
    )


@pytest.mark.anyio
async def test_regenerate_tool_rejects_llm_window_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LLM 窗口竞态：生成期间用户就地编辑一项（update_core 置 user_locked，
    项级写入不触计划头身份字段）→ 派生基线偏离当前态 → 拒绝落提案，
    旧载荷不得绑定新快照丢失窗口内的锁定编辑（spec 用户故事 15）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)
        await seed_record(session_factory)
        await seed_plan(session_factory)
        await seed_item(session_factory, ITEM_ID, user_locked=True, minutes=45, content="锁定任务")
        await seed_item(session_factory, ITEM_ID_2, priority=1, minutes=30)
        draft = llm_window_draft()

        async def fake_generate_with_mutation(**kwargs: Any) -> PlanGenerationOutcome:
            async with session_factory() as session, session.begin():
                item = await PlanItemService.get_for_plan(session, PLAN_ID, ITEM_ID_2)
                assert item is not None
                await PlanItemService.update_core(
                    session, item, PlanItemUpdate(estimated_minutes=40)
                )
            return PlanGenerationOutcome(
                kind="DRAFT", plan=draft, total_minutes=60, materials_used=1
            )

        monkeypatch.setattr(
            PlanGenerationService, "generate", staticmethod(fake_generate_with_mutation)
        )
        result = await invoke_tool(regenerate_plan, session_factory, {"goal_id": GOAL_ID})
        assert result["ok"] is False
        assert result["error"] == "OPERATION_SNAPSHOT_STALE"
        assert result["proposals"] == []
        # 竞态被拦截而非静默丢锁：零提案、零新版本。
        assert await table_count(session_factory, "agent_proposals") == 0
        assert await table_count(session_factory, "learning_plans") == 1


@pytest.mark.anyio
async def test_regenerate_confirm_stale_after_locked_item_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """提交后确认前编辑锁定项 → 锁定项版本戳使快照比对失效：确认拒绝、
    原版本不被旧载荷换代覆盖（spec 用户故事 15「锁定项原样保留」）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)
        await seed_record(session_factory)
        await seed_plan(session_factory)
        await seed_item(session_factory, ITEM_ID, user_locked=True, minutes=45, content="锁定任务")

        async def fake_generate_draft(**kwargs: Any) -> PlanGenerationOutcome:
            return PlanGenerationOutcome(
                kind="DRAFT", plan=llm_window_draft(), total_minutes=60, materials_used=1
            )

        monkeypatch.setattr(PlanGenerationService, "generate", staticmethod(fake_generate_draft))
        result = await invoke_tool(regenerate_plan, session_factory, {"goal_id": GOAL_ID})
        assert result["ok"] is True, result
        proposal = result["proposals"][0]

        # 确认前用户编辑了锁定项（item.updated_at 变化 → 版本戳失效）。
        async with session_factory() as session, session.begin():
            item = await PlanItemService.get_for_plan(session, PLAN_ID, ITEM_ID)
            assert item is not None
            await PlanItemService.update_core(session, item, PlanItemUpdate(estimated_minutes=50))

        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as excinfo:
                await ProposalService.confirm(session, proposal["proposal_id"])
        assert excinfo.value.code == "PROPOSAL_APPLY_FAILED"
        assert excinfo.value.params == {"errorCode": "OPERATION_SNAPSHOT_STALE"}
        assert (await load_plan(session_factory, PLAN_ID))["status"] == "ACTIVE"
        assert await table_count(session_factory, "learning_plans") == 1


@pytest.mark.anyio
async def test_regenerate_direct_execution_stale_basis_blocks_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FULL_ACCESS 直执行同样执法派生基线：LLM 窗口目标约束被改 → FAILED＋
    失败快照存基线 → 手动重试重验（当前态 vs 基线）恒失效，不重放旧载荷。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)
        await seed_record(session_factory)
        await seed_plan(session_factory)
        await seed_item(session_factory, ITEM_ID, user_locked=True, minutes=45, content="锁定任务")

        async def fake_generate_with_goal_change(**kwargs: Any) -> PlanGenerationOutcome:
            async with session_factory() as session, session.begin():
                goal = await GoalService.get(session, GOAL_ID)
                assert goal is not None
                await GoalService.update_core(session, goal, GoalUpdate(daily_minutes=120))
            return PlanGenerationOutcome(
                kind="DRAFT", plan=llm_window_draft(), total_minutes=60, materials_used=1
            )

        monkeypatch.setattr(
            PlanGenerationService, "generate", staticmethod(fake_generate_with_goal_change)
        )
        result = await invoke_tool(
            regenerate_plan,
            session_factory,
            {"goal_id": GOAL_ID},
            auth_mode=AuthMode.FULL_ACCESS,
        )
        assert result["ok"] is False
        assert result["error"] == "OPERATION_SNAPSHOT_STALE"

        async with session_factory() as session:
            retried = await retry_standalone_operation(session, result["operation_id"])
        assert retried["error_code"] == "OPERATION_SNAPSHOT_STALE"
        assert await table_count(session_factory, "learning_plans") == 1


@pytest.mark.anyio
async def test_regenerate_multi_phase_locked_plan_over_schema_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """多阶段锁定计划重生成不被载荷阶段上限误杀：5 锁定阶段 + 5 草案阶段
    = 10 阶段（> 单侧草案上限 8）→ 端到端成功，锁定组在前原样保留。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)
        await seed_record(session_factory)
        await seed_plan(session_factory)
        # 5 个锁定项分散在 5 个阶段（锁定项可分布在原计划每个阶段），
        # 各占 D1~D5 每天 45 分钟（60/日预算 → 草案 60 分钟项落 D6~D10）。
        for index in range(5):
            await seed_item(
                session_factory,
                f"d0000000-0000-4000-8000-00000000010{index}",
                phase_title=f"锁定阶段 {index + 1}",
                priority=index,
                minutes=45,
                scheduled_date=(TODAY + timedelta(days=index)).isoformat(),
                user_locked=True,
                content=f"锁定任务 {index + 1}",
            )

        draft = PlanConfirmCore.model_validate(
            {
                "goal_id": GOAL_ID,
                "phases": [
                    {
                        "title": f"新阶段 {index + 1}",
                        "items": [
                            {
                                "action_type": "CUSTOM",
                                "content": f"新任务 {index + 1}",
                                "estimated_minutes": 60,
                                "reason": "重排安排",
                                "record_id": None,
                                "concept_id": None,
                                "scheduled_date": TODAY.isoformat(),
                            }
                        ],
                    }
                    for index in range(5)
                ],
            }
        )

        async def fake_generate_draft(**kwargs: Any) -> PlanGenerationOutcome:
            return PlanGenerationOutcome(
                kind="DRAFT", plan=draft, total_minutes=300, materials_used=1
            )

        monkeypatch.setattr(PlanGenerationService, "generate", staticmethod(fake_generate_draft))
        result = await invoke_tool(regenerate_plan, session_factory, {"goal_id": GOAL_ID})
        assert result["ok"] is True, result
        proposal = result["proposals"][0]

        # 载荷 10 阶段：前 5 锁定组（原样）+ 后 5 草案阶段。
        phases = proposal["payload"]["phases"]
        assert len(phases) == 10
        assert [phase["title"] for phase in phases[:5]] == [
            f"锁定阶段 {index + 1}" for index in range(5)
        ]
        assert all(item["user_locked"] is True for phase in phases[:5] for item in phase["items"])
        assert [phase["title"] for phase in phases[5:]] == [
            f"新阶段 {index + 1}" for index in range(5)
        ]
        assert all(item["user_locked"] is False for phase in phases[5:] for item in phase["items"])

        async with session_factory() as session:
            confirmed = await ProposalService.confirm(session, proposal["proposal_id"])
        assert confirmed.status.value == "APPLIED"
        assert confirmed.result is not None
        assert confirmed.result["plan_version"] == 2
        assert confirmed.result["item_count"] == 10
        assert confirmed.result["locked_count"] == 5
        assert (await load_plan(session_factory, PLAN_ID))["status"] == "SUPERSEDED"


# ---------------------------------------------------------------------------
# 确认卡可编辑：edited_payload 落库、编辑校验拒绝（提案保持 PENDING）、
# 不支持编辑的类型拒绝。


def edit_payload(base: dict[str, Any]) -> dict[str, Any]:
    """模拟用户在确认卡上的编辑：改日期 / 改时长 / 删末项 / 前两项换序。"""
    items = base["phases"][0]["items"]
    edited = json.loads(json.dumps(base))
    first, second = edited["phases"][0]["items"][0], edited["phases"][0]["items"][1]
    first["scheduled_date"] = (
        date.fromisoformat(second["scheduled_date"]) + timedelta(days=1)
    ).isoformat()
    second["estimated_minutes"] = 25
    edited["phases"][0]["items"] = [second, first] + items[2:-1]
    return edited


@pytest.mark.anyio
async def test_confirm_plan_with_edited_payload_applies(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)
        await seed_record(session_factory)

        base = {
            "goal_id": GOAL_ID,
            "phases": [
                {
                    "title": "第一阶段",
                    "items": [
                        {
                            "action_type": "CUSTOM",
                            "content": f"任务 {index + 1}",
                            "estimated_minutes": value,
                            "reason": f"理由 {index + 1}",
                            "record_id": None,
                            "concept_id": None,
                            "scheduled_date": (TODAY + timedelta(days=index)).isoformat(),
                        }
                        for index, value in enumerate((60, 30, 45))
                    ],
                }
            ],
        }
        result = await invoke_tool(confirm_plan, session_factory, base)
        proposal_id = result["proposals"][0]["proposal_id"]

        async with session_factory() as session:
            confirmed = await ProposalService.confirm(session, proposal_id, edit_payload(base))
        assert confirmed.status.value == "APPLIED"
        assert confirmed.result is not None
        assert confirmed.result["item_count"] == 2

        async with session_factory() as session:
            plan = await PlanService.get_active_for_goal(session, GOAL_ID)
            assert plan is not None
            items = await PlanService.list_items(session, plan.id)
        # 落库所写 = 编辑结果（删末项、改时长、换序 → priority 跟随新顺序）。
        assert [item.content for item in items] == ["任务 2", "任务 1"]
        assert items[0].estimated_minutes == 25
        # 任务 1 的编辑后日期 = 原任务 2 日期 + 1 天（edit_payload 的手算值）。
        assert items[1].scheduled_date == (TODAY + timedelta(days=2)).isoformat()


@pytest.mark.anyio
async def test_confirm_plan_edit_validation_rejects_out_of_bounds(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)
        await seed_record(session_factory)

        payload = {
            "goal_id": GOAL_ID,
            "phases": [
                {
                    "title": "第一阶段",
                    "items": [
                        {
                            "action_type": "CUSTOM",
                            "content": "任务 1",
                            "estimated_minutes": 60,
                            "reason": "理由 1",
                            "record_id": None,
                            "concept_id": None,
                            "scheduled_date": TODAY.isoformat(),
                        }
                    ],
                }
            ],
        }
        result = await invoke_tool(confirm_plan, session_factory, payload)
        proposal_id = result["proposals"][0]["proposal_id"]

        # 编辑日期早于今天 → 422 且提案保持 PENDING（可修正后再确认）。
        past = json.loads(json.dumps(payload))
        past["phases"][0]["items"][0]["scheduled_date"] = (TODAY - timedelta(days=1)).isoformat()
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as excinfo:
                await ProposalService.confirm(session, proposal_id, past)
        assert excinfo.value.code == "PLAN_DRAFT_INVALID"
        status = await scalar(
            session_factory,
            "SELECT status FROM agent_proposals WHERE id = :id",
            {"id": proposal_id},
        )
        assert status == "PENDING"

        # 编辑日期晚于目标期限 → 同样拒绝。
        future = json.loads(json.dumps(payload))
        future["phases"][0]["items"][0]["scheduled_date"] = (TODAY + timedelta(days=29)).isoformat()
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as excinfo:
                await ProposalService.confirm(session, proposal_id, future)
        assert excinfo.value.code == "PLAN_DRAFT_INVALID"
        assert await table_count(session_factory, "learning_plans") == 0

        # 原载荷确认不受影响（未编辑路径回归）。
        async with session_factory() as session:
            confirmed = await ProposalService.confirm(session, proposal_id)
        assert confirmed.status.value == "APPLIED"


@pytest.mark.anyio
async def test_confirm_plan_edit_rejects_goal_swap_and_stays_pending(
    tmp_path: Path,
) -> None:
    """确认卡编辑换目标（goal_id 篡改为另一目标）→ 编辑校验器拒绝
    （PLAN_DRAFT_INVALID）且提案保持 PENDING；不锁死时可见性 / 期限会按
    新目标误校验、审计 target 与实际写入目标失真，且唯一兜底的快照比对
    会把提案污染成 FAILED＋误导性 STALE（spec 用户故事 9 编辑范围不含
    换目标）。校验先于目标装载 → 目标不可达也以「不能变更目标」拒绝。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)
        await seed_record(session_factory)

        payload = {
            "goal_id": GOAL_ID,
            "phases": [
                {
                    "title": "第一阶段",
                    "items": [
                        {
                            "action_type": "CUSTOM",
                            "content": "任务 1",
                            "estimated_minutes": 60,
                            "reason": "理由 1",
                            "record_id": None,
                            "concept_id": None,
                            "scheduled_date": TODAY.isoformat(),
                        }
                    ],
                }
            ],
        }
        result = await invoke_tool(confirm_plan, session_factory, payload)
        proposal_id = result["proposals"][0]["proposal_id"]

        swapped = json.loads(json.dumps(payload))
        swapped["goal_id"] = UNKNOWN_ID
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as excinfo:
                await ProposalService.confirm(session, proposal_id, swapped)
        assert excinfo.value.code == "PLAN_DRAFT_INVALID"
        assert "不能变更学习目标" in excinfo.value.detail
        status = await scalar(
            session_factory,
            "SELECT status FROM agent_proposals WHERE id = :id",
            {"id": proposal_id},
        )
        assert status == "PENDING"
        assert await table_count(session_factory, "learning_plans") == 0

        # 原载荷确认不受影响（PENDING 可恢复）。
        async with session_factory() as session:
            confirmed = await ProposalService.confirm(session, proposal_id)
        assert confirmed.status.value == "APPLIED"
        assert confirmed.result is not None and confirmed.result["goal_id"] == GOAL_ID


@pytest.mark.anyio
async def test_confirm_edit_rejected_for_non_editable_type(tmp_path: Path) -> None:
    """非计划类提案携带编辑载荷确认 → PROPOSAL_EDIT_NOT_SUPPORTED（零业务写）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)

        from app.modules.agent.tools.create_goal import create_goal

        result = await invoke_tool(
            create_goal,
            session_factory,
            {"course_id": COURSE_ID, "goal_type": "SKILL", "title": "学会 X"},
        )
        proposal_id = result["proposals"][0]["proposal_id"]
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as excinfo:
                await ProposalService.confirm(session, proposal_id, {"goal_type": "EXAM"})
        assert excinfo.value.code == "PROPOSAL_EDIT_NOT_SUPPORTED"
        status = await scalar(
            session_factory,
            "SELECT status FROM agent_proposals WHERE id = :id",
            {"id": proposal_id},
        )
        assert status == "PENDING"


@pytest.mark.anyio
async def test_confirm_plan_edit_rejects_invisible_record_and_stays_pending(
    tmp_path: Path,
) -> None:
    """编辑载荷改坏 record_id（直调 API 构造）→ 编辑校验拦截，提案保持
    PENDING（不落 FAILED），业务表零写入（工单 03 review 修复回归）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)
        await seed_record(session_factory)

        payload = {
            "goal_id": GOAL_ID,
            "phases": [
                {
                    "title": "第一阶段",
                    "items": [
                        {
                            "action_type": "STUDY_RECORD",
                            "content": "任务 1",
                            "estimated_minutes": 60,
                            "reason": "理由 1",
                            "record_id": RECORD_ID,
                            "concept_id": None,
                            "scheduled_date": TODAY.isoformat(),
                        }
                    ],
                }
            ],
        }
        result = await invoke_tool(confirm_plan, session_factory, payload)
        proposal_id = result["proposals"][0]["proposal_id"]

        edited = json.loads(json.dumps(payload))
        edited["phases"][0]["items"][0]["record_id"] = RECORD_OTHER_COURSE
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as excinfo:
                await ProposalService.confirm(session, proposal_id, edited)
        assert excinfo.value.code == "PLAN_DRAFT_INVALID"
        status = await scalar(
            session_factory,
            "SELECT status FROM agent_proposals WHERE id = :id",
            {"id": proposal_id},
        )
        assert status == "PENDING"
        assert await table_count(session_factory, "learning_plans") == 0
