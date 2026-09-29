"""学习计划（通用 Agent 第三阶段工单 02）：迁移结构、确定性排期黄金样本、
生成服务草案语义（零落库）、确认落库（ACTIVE 唯一 / 版本递增）、Agent 工具
确认行为（L2 档位 / 提交时结构化拒绝）与提案确认路由集成。"""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any, cast

import aiosqlite
import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError as SqlaIntegrityError
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
from app.modules.agent.tools.confirm_plan import confirm_plan
from app.modules.agent.tools.generate_learning_plan import generate_learning_plan
from app.modules.agent.tools.get_plan import get_plan
from app.modules.learning_plan.generation import (
    MaterialDigest,
    PlanGenerationOutcome,
    PlanGenerationService,
    constraints_for,
)
from app.modules.learning_plan.models import LearningGoal
from app.modules.learning_plan.scheduling import (
    DEFAULT_DAILY_MINUTES,
    ScheduleConstraints,
    ScheduleInfeasible,
    pack_schedule,
)
from app.modules.learning_plan.schemas import (
    PlanConfirmCore,
    PlanDraft,
    PlanDraftItem,
    PlanDraftPhase,
    PlanItemType,
    PlanMaterialGap,
    PlanStatus,
    PlanSuggestedContent,
    PlanSuggestions,
)
from app.modules.learning_plan.service import GoalService, PlanService
from app.modules.library.proposals import ProposalService
from app.modules.llm.service import StructuredModelResult
from app.modules.settings.config import LlmProviderConfig
from app.shared.errors import CodedHTTPException

TOKEN = "test-launch-token"
NOW = "2026-09-29T08:00:00.000000Z"
COURSE_ID = "c0000000-0000-4000-8000-000000000001"
GOAL_ID = "90000000-0000-4000-8000-000000000001"
RECORD_ID = "a0000000-0000-4000-8000-000000000001"
RECORD_OTHER_COURSE = "a0000000-0000-4000-8000-000000000002"
UNKNOWN_ID = "90000000-0000-4000-8000-00000000dead"
# 测试专用供应商（generate 工具的 LLM 结构化生成；真实调用在 service 测试以
# Fake 模型注入，工具级测试 monkeypatch generate，恒零真实外呼）。
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
    """路由集成夹具：应用 + 其会话工厂（种子与提案创建共用同一数据库）。"""
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
    status: str = "ACTIVE",
    target_date: str = "2026-10-27",
    daily_minutes: int = 60,
) -> None:
    await run_sql(
        "INSERT INTO learning_goals (id, course_id, goal_type, title, target_date, "
        "daily_minutes, scope_source, scope_confirmed, status, created_at, updated_at) "
        "VALUES (:id, :course_id, 'SKILL', '四周内学会 Agent 工程', :target_date, "
        ":daily_minutes, 'AI_INFERRED', 1, :status, :now, :now)",
        {
            "id": GOAL_ID,
            "course_id": COURSE_ID,
            "status": status,
            "target_date": target_date,
            "daily_minutes": daily_minutes,
            "now": NOW,
        },
        session_factory,
    )


async def seed_record(
    session_factory: async_sessionmaker[AsyncSession],
    record_id: str = RECORD_ID,
    *,
    course_id: str = COURSE_ID,
    title: str = "第 1 讲 Agent 概论",
    deleted: bool = False,
) -> None:
    await run_sql(
        "INSERT INTO records (id, course_id, capture_type, title, status, duration_ms, "
        "created_at, updated_at, deleted_at) VALUES (:id, :course_id, 'DOCUMENT_IMPORT', :title, "
        "'SUMMARY_READY', 0, :now, :now, :deleted)",
        {
            "id": record_id,
            "course_id": course_id,
            "title": title,
            "deleted": None if not deleted else NOW,
            "now": NOW,
        },
        session_factory,
    )


async def seed_confirmed_summary(
    session_factory: async_sessionmaker[AsyncSession],
    record_id: str = RECORD_ID,
) -> None:
    await run_sql(
        "INSERT INTO ai_summaries (id, record_id, version_no, transcript_source_version, "
        "topic, abstract, summary_json, status, model, prompt_version, token_usage_json, "
        "latency_ms, confirmed_at, created_at, updated_at) VALUES "
        "('f0000000-0000-4000-8000-00000000000f', :record_id, 1, 1, 'Agent 基础', "
        "'覆盖 Agent 骨架与工具调用。', '{}', 'CONFIRMED', 'test-model', 'v1', '{}', 10, "
        ":now, :now, :now)",
        {"record_id": record_id, "now": NOW},
        session_factory,
    )


async def seed_active_plan(
    session_factory: async_sessionmaker[AsyncSession],
    plan_id: str = "70000000-0000-4000-8000-000000000001",
    *,
    status: str = "ACTIVE",
    plan_version: int = 1,
) -> None:
    await run_sql(
        "INSERT INTO learning_plans (id, goal_id, plan_version, status, effective_from, "
        "created_at, updated_at) VALUES (:id, :goal_id, :plan_version, :status, "
        "'2026-09-20', :now, :now)",
        {
            "id": plan_id,
            "goal_id": GOAL_ID,
            "plan_version": plan_version,
            "status": status,
            "now": NOW,
        },
        session_factory,
    )


async def plan_row_count(session_factory: async_sessionmaker[AsyncSession]) -> int:
    async with session_factory() as session:
        return cast(
            int,
            await session.scalar(text("SELECT COUNT(*) FROM learning_plans")),
        )


async def plan_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[dict[str, Any]]:
    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT id, goal_id, plan_version, status, effective_from "
                    "FROM learning_plans ORDER BY plan_version"
                )
            )
        ).all()
    return [
        {
            "id": row[0],
            "goal_id": row[1],
            "plan_version": row[2],
            "status": row[3],
            "effective_from": row[4],
        }
        for row in rows
    ]


async def item_rows(
    session_factory: async_sessionmaker[AsyncSession],
    plan_id: str,
) -> list[dict[str, Any]]:
    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT action_type, content, record_id, phase_title, priority, "
                    "estimated_minutes, scheduled_date, status, user_locked, reason_json "
                    "FROM learning_plan_items WHERE plan_id = :plan_id ORDER BY priority"
                ),
                {"plan_id": plan_id},
            )
        ).all()
    return [
        {
            "action_type": row[0],
            "content": row[1],
            "record_id": row[2],
            "phase_title": row[3],
            "priority": row[4],
            "estimated_minutes": row[5],
            "scheduled_date": row[6],
            "status": row[7],
            "user_locked": bool(row[8]),
            "reason_json": row[9],
        }
        for row in rows
    ]


async def goal_of(session_factory: async_sessionmaker[AsyncSession]) -> LearningGoal:
    async with session_factory() as session:
        goal = await GoalService.get(session, GOAL_ID)
    assert goal is not None
    return goal


async def invoke_plan_tool(
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
            session_id="sess-plans",
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


def packed_payload(
    *,
    start: str = "2026-09-29",
    minutes: tuple[int, ...] = (60, 30, 45),
    record_ids: tuple[str | None, ...] = (RECORD_ID, None, None),
    goal_id: str = GOAL_ID,
) -> dict[str, Any]:
    """黄金样本载荷：按 60 分钟 / 日预算手算铺排（60→D1；30→D2；45→D3）。
    锚点默认 = 目标 updated_at 同日（排期起点不得早于目标定版日）。"""
    dates = pack_schedule(
        list(minutes),
        ScheduleConstraints(
            start_date=date.fromisoformat(start),
            deadline=date(2026, 10, 27),
            daily_minutes=60,
        ),
    )
    items = [
        {
            "action_type": "STUDY_RECORD" if rid is not None else "CUSTOM",
            "content": f"任务 {index + 1}",
            "estimated_minutes": value,
            "reason": f"理由 {index + 1}",
            "record_id": rid,
            "concept_id": None,
            "scheduled_date": value_date.isoformat(),
        }
        for index, (value, rid, value_date) in enumerate(
            zip(minutes, record_ids, dates, strict=True)
        )
    ]
    return {
        "goal_id": goal_id,
        "phases": [{"title": "第一阶段", "items": items}],
    }


class FakeDraftModel:
    """LLM 替身：返回预置草案（StructuredModel 协议，零外呼）。"""

    def __init__(self, draft: PlanDraft) -> None:
        self._draft = draft

    async def generate(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
    ) -> StructuredModelResult:
        return StructuredModelResult(output=self._draft.model_dump(mode="json"), token_usage={})


class FakeSuggestionsModel:
    def __init__(self, suggestions: PlanSuggestions) -> None:
        self._suggestions = suggestions

    async def generate(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
    ) -> StructuredModelResult:
        return StructuredModelResult(
            output=self._suggestions.model_dump(mode="json"), token_usage={}
        )


def sample_draft(minutes: tuple[int, ...] = (60, 30, 45)) -> PlanDraft:
    return PlanDraft(
        phases=[
            PlanDraftPhase(
                title="第一阶段",
                items=[
                    PlanDraftItem(
                        action_type=PlanItemType.CUSTOM,
                        content=f"任务 {index + 1}",
                        estimated_minutes=value,
                        reason=f"理由 {index + 1}",
                    )
                    for index, value in enumerate(minutes)
                ],
            )
        ]
    )


def sample_suggestions() -> PlanSuggestions:
    return PlanSuggestions(
        suggested_contents=[PlanSuggestedContent(title="Agent 入门综述", why="建立全局图景")],
        material_gaps=[PlanMaterialGap(what="入门教程文档", why="系统学习需要主线材料")],
    )


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# 迁移结构（0035）。


@pytest.mark.anyio
async def test_migration_0035_creates_learning_plans(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)

    async with aiosqlite.connect(db_path) as connection:
        version = await (await connection.execute("PRAGMA user_version")).fetchone()
        assert version is not None
        assert version[0] == supported_user_version()

        plan_columns = {
            cast(str, row[1])
            for row in await (
                await connection.execute("PRAGMA table_info(learning_plans)")
            ).fetchall()
        }
        assert {
            "id",
            "goal_id",
            "plan_version",
            "status",
            "effective_from",
            "effective_to",
        } <= plan_columns
        item_columns = {
            cast(str, row[1])
            for row in await (
                await connection.execute("PRAGMA table_info(learning_plan_items)")
            ).fetchall()
        }
        assert {
            "plan_id",
            "action_type",
            "content",
            "record_id",
            "concept_id",
            "phase_title",
            "priority",
            "estimated_minutes",
            "scheduled_date",
            "status",
            "user_locked",
            "reason_json",
        } <= item_columns

        indexes = {
            cast(str, row[1])
            for row in await (
                await connection.execute("PRAGMA index_list(learning_plans)")
            ).fetchall()
        }
        assert "idx_learning_plans_one_active" in indexes

    # (goal_id, plan_version) 唯一在存储层验证（见下一条行为测试）。


@pytest.mark.anyio
async def test_plan_unique_constraints_enforced(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)

        await seed_active_plan(session_factory)
        # 同 (goal_id, plan_version) 重复 → 唯一约束拒绝。
        with pytest.raises(SqlaIntegrityError):
            await run_sql(
                "INSERT INTO learning_plans (id, goal_id, plan_version, status, "
                "effective_from, created_at, updated_at) VALUES "
                "('70000000-0000-4000-8000-000000000002', :goal_id, 1, 'SUPERSEDED', "
                "'2026-09-20', :now, :now)",
                {"goal_id": GOAL_ID, "now": NOW},
                session_factory,
            )
        # 第二条 ACTIVE → 部分唯一索引拒绝；终态（SUPERSEDED）可并存。
        with pytest.raises(SqlaIntegrityError):
            await seed_active_plan(
                session_factory,
                "70000000-0000-4000-8000-000000000003",
                status="ACTIVE",
                plan_version=2,
            )
        await seed_active_plan(
            session_factory,
            "70000000-0000-4000-8000-000000000004",
            status="SUPERSEDED",
            plan_version=2,
        )
        assert len(await plan_rows(session_factory)) == 2


# ---------------------------------------------------------------------------
# 确定性排期黄金样本（纯函数手算）。


def test_pack_schedule_golden_samples() -> None:
    start = date(2026, 1, 5)

    # 样本一：预算 60，[60, 30, 45] → 60 装满 D1；30 上 D2；45 超 30 余量上 D3。
    dates = pack_schedule([60, 30, 45], ScheduleConstraints(start_date=start, daily_minutes=60))
    assert [d.day - start.day for d in dates] == [0, 1, 2]

    # 样本二：同日装满：[30, 30] 预算 60 → 同一天。
    dates = pack_schedule([30, 30], ScheduleConstraints(start_date=start, daily_minutes=60))
    assert dates == [start, start]

    # 样本三：单项超每日预算 → 不可行（计划项不跨日拆分，无法与每日总量相容）。
    with pytest.raises(ScheduleInfeasible) as excinfo:
        pack_schedule([90, 30], ScheduleConstraints(start_date=start, daily_minutes=60))
    assert "单项时长 90 分钟超过每日预算 60 分钟" in str(excinfo.value)

    # 样本四：跨日累计：[30, 30, 30] 预算 60 → 前两项 D1，第三项 D2。
    dates = pack_schedule([30, 30, 30], ScheduleConstraints(start_date=start, daily_minutes=60))
    assert [d.day - start.day for d in dates] == [0, 0, 1]


def test_pack_schedule_item_over_daily_budget_infeasible() -> None:
    """回归：单项超预算曾按「独占一天」豁免放行（每日总量相容被击穿）。"""
    # 期限当天 + 单项 600 分钟：日期不超期限，但当日总量 600 与预算 30 不相容。
    with pytest.raises(ScheduleInfeasible) as excinfo:
        pack_schedule(
            [600],
            ScheduleConstraints(
                start_date=date(2026, 9, 29), deadline=date(2026, 9, 29), daily_minutes=30
            ),
        )
    assert excinfo.value.required_minutes == 600
    assert excinfo.value.capacity_minutes == 30

    # 宽松期限变体：容量 900 足够，仍须拒绝（每日总量相容与期限容量无关）。
    with pytest.raises(ScheduleInfeasible):
        pack_schedule(
            [600, 30],
            ScheduleConstraints(
                start_date=date(2026, 9, 29), deadline=date(2026, 10, 28), daily_minutes=30
            ),
        )


def test_pack_schedule_deadline_infeasible() -> None:
    start = date(2026, 10, 26)
    constraints = ScheduleConstraints(
        start_date=start, deadline=date(2026, 10, 27), daily_minutes=60
    )
    # 容量 = 2 天 × 60 = 120；总量 180 → 铺不开。
    with pytest.raises(ScheduleInfeasible) as excinfo:
        pack_schedule([60, 60, 60], constraints)
    assert excinfo.value.required_minutes == 180
    assert excinfo.value.capacity_minutes == 120

    # 恰好装满（120）→ 通过，末日 = 期限。
    dates = pack_schedule([60, 60], constraints)
    assert dates[-1] == date(2026, 10, 27)


def test_constraints_for_goal_defaults() -> None:
    goal = LearningGoal(
        id=GOAL_ID,
        course_id=COURSE_ID,
        goal_type="SKILL",
        title="目标",
        scope_source="AI_INFERRED",
        scope_confirmed=True,
    )
    constraints = constraints_for(goal, date(2026, 9, 29))
    assert constraints.deadline is None
    assert constraints.daily_minutes == DEFAULT_DAILY_MINUTES

    goal.target_date = "2026-10-27"
    goal.daily_minutes = 45
    constraints = constraints_for(goal, date(2026, 9, 29))
    assert constraints.deadline == date(2026, 10, 27)
    assert constraints.daily_minutes == 45


# ---------------------------------------------------------------------------
# 生成服务：资料聚合、草案（零落库）、无资料建议、不可行。


@pytest.mark.anyio
async def test_gather_materials_with_summary_and_soft_delete(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)
        await seed_record(session_factory, RECORD_ID, title="第 1 讲 Agent 概论")
        await seed_record(session_factory, RECORD_OTHER_COURSE, title="旧记录", deleted=True)
        await seed_confirmed_summary(session_factory)

        async with session_factory() as session:
            materials = await PlanGenerationService.gather_materials(session, COURSE_ID)
            evidence = await PlanGenerationService.retrieve_evidence(
                session, COURSE_ID, "四周内学会 Agent 工程"
            )
        # 软删记录不进资料面；已确认总结进摘要（topic：abstract 形态）。
        assert [material.record_id for material in materials] == [RECORD_ID]
        assert materials[0].title == "第 1 讲 Agent 概论"
        assert materials[0].summary_excerpt.startswith("Agent 基础：")
        # 空语料检索零命中不炸（复用既有检索，逐字引文面可为空）。
        assert evidence == []


@pytest.mark.anyio
async def test_gather_materials_empty_for_course_without_records(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        async with session_factory() as session:
            assert await PlanGenerationService.gather_materials(session, COURSE_ID) == []


@pytest.mark.anyio
async def test_generate_draft_packs_dates_and_writes_nothing(tmp_path: Path) -> None:
    """草案语义：日期由排期器铺排；生成全程零 learning_plans 落库。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)
        goal = await goal_of(session_factory)

        outcome = await PlanGenerationService.generate(
            session_factory=session_factory,
            goal=goal,
            provider=TEST_PROVIDER,
            today=date(2026, 1, 5),
            materials=[
                MaterialDigest(
                    record_id=RECORD_ID,
                    title="第 1 讲",
                    capture_type="DOCUMENT",
                    summary_excerpt="",
                )
            ],
            evidence=[],
            draft_model=FakeDraftModel(sample_draft((60, 30, 45))),  # type: ignore[arg-type]
        )
        assert outcome.kind == "DRAFT"
        assert outcome.plan is not None
        items = [item for phase in outcome.plan.phases for item in phase.items]
        assert [item.scheduled_date for item in items] == [
            date(2026, 1, 5),
            date(2026, 1, 6),
            date(2026, 1, 7),
        ]
        assert outcome.total_minutes == 135
        assert outcome.materials_used == 1
        # 草案零落库（spec 用户故事 11）。
        assert await plan_row_count(session_factory) == 0


@pytest.mark.anyio
async def test_generate_suggestions_when_no_materials(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)
        goal = await goal_of(session_factory)

        outcome = await PlanGenerationService.generate(
            session_factory=session_factory,
            goal=goal,
            provider=TEST_PROVIDER,
            today=date(2026, 1, 5),
            materials=[],
            evidence=[],
            suggestions_model=FakeSuggestionsModel(sample_suggestions()),  # type: ignore[arg-type]
        )
        assert outcome.kind == "SUGGESTIONS"
        assert outcome.suggestions is not None
        assert outcome.suggestions.suggested_contents[0].title == "Agent 入门综述"
        assert await plan_row_count(session_factory) == 0


@pytest.mark.anyio
async def test_generate_infeasible_raises_schedule_error(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        # 期限只剩两天：容量 2 × 60 = 120 < 180。
        await seed_goal(session_factory, target_date="2026-01-06")
        goal = await goal_of(session_factory)

        with pytest.raises(ScheduleInfeasible):
            await PlanGenerationService.generate(
                session_factory=session_factory,
                goal=goal,
                provider=TEST_PROVIDER,
                today=date(2026, 1, 5),
                materials=[
                    MaterialDigest(
                        record_id=RECORD_ID,
                        title="第 1 讲",
                        capture_type="DOCUMENT",
                        summary_excerpt="",
                    )
                ],
                evidence=[],
                draft_model=FakeDraftModel(sample_draft((60, 60, 60))),  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# 确认落库语义（PlanService.confirm_core）。


@pytest.mark.anyio
async def test_confirm_core_creates_active_plan_and_items(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)
        await seed_record(session_factory)
        goal = await goal_of(session_factory)
        payload = PlanConfirmCore.model_validate(packed_payload())

        async with session_factory() as session, session.begin():
            plan = await PlanService.confirm_core(session, goal, payload)

        assert plan.plan_version == 1
        assert plan.status == PlanStatus.ACTIVE.value
        rows = await item_rows(session_factory, plan.id)
        assert [row["priority"] for row in rows] == [0, 1, 2]
        assert [row["scheduled_date"] for row in rows] == [
            "2026-09-29",
            "2026-09-30",
            "2026-10-01",
        ]
        assert rows[0]["record_id"] == RECORD_ID
        assert rows[0]["action_type"] == "STUDY_RECORD"
        assert rows[1]["action_type"] == "CUSTOM"
        assert all(row["phase_title"] == "第一阶段" for row in rows)
        assert all(row["status"] == "PENDING" for row in rows)
        assert all(row["user_locked"] is False for row in rows)
        assert json.loads(cast(str, rows[0]["reason_json"])) == {"reason": "理由 1"}

        # 投影：reason 解析回字段。
        async with session_factory() as session:
            projection = PlanService.plan_out(
                plan, await PlanService.list_items(session, plan.id), course_id=COURSE_ID
            )
        assert projection.items[0].reason == "理由 1"
        assert projection.effective_from == date.fromisoformat(plan.effective_from)


@pytest.mark.anyio
async def test_confirm_core_version_increments_after_terminal(tmp_path: Path) -> None:
    """旧版本进终态后新确认递增版本（重生成链路随工单 03，此处验证版本语义）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)
        await seed_record(session_factory)
        await seed_active_plan(session_factory, status="SUPERSEDED", plan_version=1)
        goal = await goal_of(session_factory)

        async with session_factory() as session, session.begin():
            plan = await PlanService.confirm_core(
                session, goal, PlanConfirmCore.model_validate(packed_payload())
            )
        assert plan.plan_version == 2
        assert plan.status == PlanStatus.ACTIVE.value


@pytest.mark.anyio
async def test_confirm_core_single_active_rejected(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)
        await seed_active_plan(session_factory)
        goal = await goal_of(session_factory)

        with pytest.raises(CodedHTTPException) as excinfo:
            async with session_factory() as session, session.begin():
                await PlanService.confirm_core(
                    session, goal, PlanConfirmCore.model_validate(packed_payload())
                )
        assert excinfo.value.code == "PLAN_ACTIVE_EXISTS"


# ---------------------------------------------------------------------------
# Agent 工具：confirm_plan（L2 档位 + 提交时结构化拒绝）。


@pytest.mark.anyio
async def test_confirm_plan_proposal_confirm_applies(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)
        await seed_record(session_factory)

        result = await invoke_plan_tool(confirm_plan, session_factory, packed_payload())
        assert result["ok"] is True
        proposal = result["proposals"][0]
        assert proposal["action"] == "confirm_plan"
        assert proposal["status"] == "PENDING"

        # 提案前快照已同事务固化（目标身份 + 排期约束字段 + 课程名）。
        async with session_factory() as session:
            snapshot_json = cast(
                str,
                await session.scalar(
                    text("SELECT snapshot_json FROM agent_proposals WHERE id = :id"),
                    {"id": proposal["proposal_id"]},
                ),
            )
        snapshot = json.loads(snapshot_json)
        assert snapshot["title"] == "四周内学会 Agent 工程"
        assert snapshot["course_name"] == "Agent 工程"
        assert snapshot["daily_minutes"] == 60

        # 确认前零计划事实（草案不持久化）。
        assert await plan_row_count(session_factory) == 0

        async with session_factory() as session:
            confirmed = await ProposalService.confirm(session, proposal["proposal_id"])
        assert confirmed.status.value == "APPLIED"
        assert confirmed.result is not None
        assert set(confirmed.result.keys()) == {
            "plan_id",
            "goal_id",
            "course_id",
            "plan_version",
            "item_count",
            "first_date",
            "last_date",
        }
        assert confirmed.result["item_count"] == 3
        assert confirmed.result["first_date"] == "2026-09-29"
        assert confirmed.result["last_date"] == "2026-10-01"

        plans = await plan_rows(session_factory)
        assert len(plans) == 1 and plans[0]["status"] == "ACTIVE"


@pytest.mark.anyio
async def test_confirm_plan_snapshot_stale_when_goal_edited(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)
        await seed_record(session_factory)

        result = await invoke_plan_tool(confirm_plan, session_factory, packed_payload())
        proposal_id = result["proposals"][0]["proposal_id"]
        # 确认前目标被编辑（期限变化 → 快照失真）。
        await run_sql(
            "UPDATE learning_goals SET target_date = '2026-12-31', updated_at = :now "
            "WHERE id = :id",
            {"id": GOAL_ID, "now": NOW},
            session_factory,
        )
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as excinfo:
                await ProposalService.confirm(session, proposal_id)
        assert excinfo.value.code == "PROPOSAL_APPLY_FAILED"
        assert excinfo.value.params == {"errorCode": "OPERATION_SNAPSHOT_STALE"}
        assert await plan_row_count(session_factory) == 0


@pytest.mark.anyio
async def test_confirm_plan_submit_rejections(tmp_path: Path) -> None:
    """提交时结构化拒绝（零提案）：目标不可达 / 非进行中 / 已有计划 /
    记录引用越界 / 排期漂移 / 总量超期限。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_record(session_factory)

        # 目标不存在。
        result = await invoke_plan_tool(
            confirm_plan, session_factory, packed_payload(goal_id=UNKNOWN_ID)
        )
        assert result["ok"] is False and result["error"] == "GOAL_NOT_FOUND"
        assert result["proposals"] == []

        await seed_goal(session_factory, status="ARCHIVED")
        result = await invoke_plan_tool(confirm_plan, session_factory, packed_payload())
        assert result["ok"] is False and result["error"] == "GOAL_NOT_ACTIVE"
        assert result["proposals"] == []

        await run_sql(
            "UPDATE learning_goals SET status = 'ACTIVE' WHERE id = :id",
            {"id": GOAL_ID},
            session_factory,
        )
        await seed_active_plan(session_factory)
        result = await invoke_plan_tool(confirm_plan, session_factory, packed_payload())
        assert result["ok"] is False and result["error"] == "PLAN_ACTIVE_EXISTS"
        assert result["proposals"] == []

        await run_sql("DELETE FROM learning_plans", {}, session_factory)
        # 记录引用越界：载荷 record_id 指向他课记录。
        await run_sql(
            "INSERT INTO records (id, course_id, capture_type, title, status, "
            "duration_ms, created_at, updated_at) VALUES (:id, NULL, 'DOCUMENT_IMPORT', "
            "'未归类记录', 'SUMMARY_READY', 0, :now, :now)",
            {"id": RECORD_OTHER_COURSE, "now": NOW},
            session_factory,
        )
        payload = packed_payload(record_ids=(RECORD_OTHER_COURSE, None, None))
        result = await invoke_plan_tool(confirm_plan, session_factory, payload)
        assert result["ok"] is False
        assert result["error"] == "PLAN_DRAFT_INVALID"

        # 排期漂移：中间项日期与确定性铺排不一致（detail 附期望日期供模型自纠）。
        payload = packed_payload()
        payload["phases"][0]["items"][1]["scheduled_date"] = "2026-01-05"
        result = await invoke_plan_tool(confirm_plan, session_factory, payload)
        assert result["ok"] is False
        assert result["error"] == "PLAN_SCHEDULE_INVALID"
        assert "2026-09-30" in result["detail"]

        # 排期起点早于目标定版日（updated_at）→ 拒绝（回挪起点虚增期限容量）。
        payload = packed_payload(start="2026-01-05")
        result = await invoke_plan_tool(confirm_plan, session_factory, payload)
        assert result["ok"] is False
        assert result["error"] == "PLAN_SCHEDULE_INVALID"
        assert "早于目标当前版本" in result["detail"]

        # 总量超期限：手写越界排期（锚定末日 + 三项 60 分钟，重算铺不开）。
        payload = {
            "goal_id": GOAL_ID,
            "phases": [
                {
                    "title": "第一阶段",
                    "items": [
                        {
                            "action_type": "CUSTOM",
                            "content": f"任务 {index + 1}",
                            "estimated_minutes": 60,
                            "reason": f"理由 {index + 1}",
                            "record_id": None,
                            "concept_id": None,
                            "scheduled_date": day,
                        }
                        for index, day in enumerate(("2026-10-26", "2026-10-27", "2026-10-28"))
                    ],
                }
            ],
        }
        result = await invoke_plan_tool(confirm_plan, session_factory, payload)
        assert result["ok"] is False
        assert result["error"] == "PLAN_SCHEDULE_INFEASIBLE"
        assert result["proposals"] == []

        assert await plan_row_count(session_factory) == 0


@pytest.mark.anyio
async def test_confirm_plan_auth_modes_l2_semantics(tmp_path: Path) -> None:
    """L2：AUTO_APPROVE 仍落确认卡（草案卡即确认闸门）；FULL_ACCESS 直执行。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)
        await seed_record(session_factory)

        result = await invoke_plan_tool(
            confirm_plan,
            session_factory,
            packed_payload(),
            auth_mode=AuthMode.AUTO_APPROVE,
        )
        assert result["ok"] is True
        assert result["proposals"][0]["status"] == "PENDING"
        assert await plan_row_count(session_factory) == 0
        await run_sql("DELETE FROM agent_proposals", {}, session_factory)

        result = await invoke_plan_tool(
            confirm_plan,
            session_factory,
            packed_payload(),
            auth_mode=AuthMode.FULL_ACCESS,
        )
        assert result["ok"] is True
        executed = result["executed"]
        assert executed["action"] == "confirm_plan"
        assert executed["level"] == "L2"
        assert executed["result"]["item_count"] == 3
        assert await plan_row_count(session_factory) == 1


# ---------------------------------------------------------------------------
# Agent 工具：generate_learning_plan 与 get_plan。


@pytest.mark.anyio
async def test_generate_tool_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)

        # 目标不存在 → 结构化指引。
        result = await invoke_plan_tool(
            generate_learning_plan, session_factory, {"goal_id": UNKNOWN_ID}
        )
        assert result["ok"] is False and result["error"] == "GOAL_NOT_FOUND"

        # 无 LLM 供应商 → 配置缺失。
        await seed_goal(session_factory)
        result = await invoke_plan_tool(
            generate_learning_plan,
            session_factory,
            {"goal_id": GOAL_ID},
            llm_provider=None,
        )
        assert result["ok"] is False
        assert result["error"] == "LLM_PROVIDER_UNCONFIGURED"

        # 无资料 → 建议与缺口（monkeypatch generate，零真实外呼）。
        async def fake_generate(**kwargs: Any) -> PlanGenerationOutcome:
            return PlanGenerationOutcome(kind="SUGGESTIONS", suggestions=sample_suggestions())

        monkeypatch.setattr(PlanGenerationService, "generate", staticmethod(fake_generate))
        result = await invoke_plan_tool(
            generate_learning_plan, session_factory, {"goal_id": GOAL_ID}
        )
        assert result["ok"] is True
        assert result["suggestions"]["suggested_contents"][0]["title"] == "Agent 入门综述"
        assert "补充资料" in result["message"]

        # 有资料 → 草案载荷（含日期与确认指引）。
        outcome = PlanGenerationOutcome(
            kind="DRAFT",
            plan=PlanConfirmCore.model_validate(packed_payload()),
            total_minutes=135,
            constraints=ScheduleConstraints(start_date=date(2026, 1, 5), daily_minutes=60),
            materials_used=1,
        )

        async def fake_generate_draft(**kwargs: Any) -> PlanGenerationOutcome:
            return outcome

        monkeypatch.setattr(PlanGenerationService, "generate", staticmethod(fake_generate_draft))
        result = await invoke_plan_tool(
            generate_learning_plan, session_factory, {"goal_id": GOAL_ID}
        )
        assert result["ok"] is True
        assert result["plan"]["phases"][0]["items"][0]["scheduled_date"] == "2026-09-29"
        assert result["total_estimated_minutes"] == 135
        assert "confirm_plan" in result["message"]

        # 已有进行中计划 → 提交时拒绝语义（require_no_active 经工具透出）。
        await seed_active_plan(session_factory)
        result = await invoke_plan_tool(
            generate_learning_plan, session_factory, {"goal_id": GOAL_ID}
        )
        assert result["ok"] is False and result["error"] == "PLAN_ACTIVE_EXISTS"


@pytest.mark.anyio
async def test_get_plan_none_then_after_confirm(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_goal(session_factory)
        await seed_record(session_factory)

        result = await invoke_plan_tool(get_plan, session_factory, {"goal_id": GOAL_ID})
        assert result["ok"] is True
        assert result["plan"] is None
        assert "generate_learning_plan" in result["message"]

        result = await invoke_plan_tool(
            confirm_plan,
            session_factory,
            packed_payload(),
            auth_mode=AuthMode.FULL_ACCESS,
        )
        plan_id = result["executed"]["result"]["plan_id"]

        result = await invoke_plan_tool(get_plan, session_factory, {"goal_id": GOAL_ID})
        assert result["ok"] is True
        plan = result["plan"]
        assert plan["id"] == plan_id
        assert plan["plan_version"] == 1
        assert [item["content"] for item in plan["items"]] == ["任务 1", "任务 2", "任务 3"]
        assert plan["items"][0]["reason"] == "理由 1"


# ---------------------------------------------------------------------------
# 提案确认 / 拒绝路由集成（既有端点 × 新载荷类型）。


@pytest.mark.anyio
async def test_proposal_routes_confirm_and_reject_plan(tmp_path: Path) -> None:
    async with plan_app(tmp_path) as (client, session_factory):
        await seed_course(session_factory)
        await seed_goal(session_factory)
        await seed_record(session_factory)

        # 经操作提交路径建提案（与生产同链路）。
        result = await invoke_plan_tool(confirm_plan, session_factory, packed_payload())
        proposal_id = result["proposals"][0]["proposal_id"]

        confirmed = await client.post(f"/api/proposals/{proposal_id}/confirm")
        assert confirmed.status_code == 200
        body = confirmed.json()
        assert body["status"] == "APPLIED"
        assert body["result"]["plan_version"] == 1
        assert await plan_row_count(session_factory) == 1

        # 拒绝路径：旧版进终态后新提案，拒绝零业务事实。
        await run_sql(
            "UPDATE learning_plans SET status = 'SUPERSEDED' WHERE goal_id = :gid",
            {"gid": GOAL_ID},
            session_factory,
        )
        result = await invoke_plan_tool(confirm_plan, session_factory, packed_payload())
        assert result["ok"] is True
        proposal_id = result["proposals"][0]["proposal_id"]
        before = await plan_row_count(session_factory)
        rejected = await client.post(f"/api/proposals/{proposal_id}/reject")
        assert rejected.status_code == 200
        assert rejected.json()["status"] == "REJECTED"
        assert await plan_row_count(session_factory) == before
