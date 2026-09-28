"""通用 Agent 第二阶段工单 05：批量计划卡与 Run 推进。

- 工具层分流：请求批准档恒出计划卡（确认前零业务事实）；帮我批准档阈值内直建
  Run＋PLANNED operations＋AGENT_RUN 触发 job、超阈值仍出计划卡、拆调用不重置
  计数、同目标重复提交不新增；完全访问档不受阈值限制，但已批准计划的 Run
  目标超出已批准集合仍升回确认；
- 确认与应用层：确认事务内固化 Run（auth_mode / instruction_text / proposal_id）
  与逐项 operation（快照随行）；提交后目标变化 → 确认失效；重规划延展同一 Run
  （版本递增、依赖解析为 operation id）；
- 推进：逐项原子执行、部分失败独立继续、依赖失败后续跳过、冲突转等待（Q1 场景：
  重启接续、重新预览授权后继续、已成功项零重做）、取消停止且已提交保留、失败项
  重试（原身份 attempts 递增）＋依赖项恢复、重启重投不重做、领取守卫只认 RUNNING；
- 损坏计划（工单 05 review）：执行路径停止并落 AGENT_RUN_PLAN_INVALID（零业务
  事实、未执行项 SKIPPED）、取消不依赖计划仍收尾、写路径拒绝在坏计划上追加。
"""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import create_database
from app.db.migrations import run_migrations
from app.modules.agent.auth_mode import (
    clear_session_auth_override,
    record_session_switch_audit,
    set_session_auth_override,
)
from app.modules.agent.runs import plans
from app.modules.agent.runs.schemas import AuthMode
from app.modules.agent.runs.service import RunControlService, RunHistoryService
from app.modules.agent.runs.worker import advance_run, advance_step, agent_run_spec
from app.modules.agent.runtime import (
    AgentRuntimeContext,
    ToolCallBudget,
    bind_agent_runtime_context,
    reset_agent_runtime_context,
)
from app.modules.agent.tools.plan_batch_operations import plan_batch_operations
from app.modules.jobs.runner import CancelClaim, JobRunner
from app.modules.library.proposals import ProposalService
from app.modules.library.schemas import ProposalType
from app.shared.errors import CodedHTTPException
from app.shared.events import RecordInvalidationNotifier

NOW = "2026-09-26T08:00:00.000000Z"
LATER = "2026-09-26T09:00:00.000000Z"
COURSE_ID = "c0000000-0000-4000-8000-000000000001"
COURSE_OTHER = "c0000000-0000-4000-8000-000000000002"
COURSE_MISSING = "c0000000-0000-4000-8000-00000000dead"
SESSION_ID = "sess-batch"
RUN_ID = "b0000000-0000-4000-8000-000000000001"


def item_id(index: int) -> str:
    return f"a0000000-0000-4000-8000-{index:012d}"


@asynccontextmanager
async def bare_db(tmp_path: Path) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    _engine, session_factory = create_database(db_path)
    try:
        yield session_factory
    finally:
        await _engine.dispose()


async def run_sql(
    sql: str,
    params: dict[str, object],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(text(sql), params)


async def count_rows(session_factory: async_sessionmaker[AsyncSession], sql: str) -> int:
    async with session_factory() as session:
        return int(cast(int, (await session.execute(text(sql))).scalar_one()))


async def seed_course(
    session_factory: async_sessionmaker[AsyncSession], course_id: str = COURSE_ID
) -> None:
    await run_sql(
        "INSERT INTO courses (id, name, learning_context, depth, status, created_at,"
        " updated_at) VALUES (:id, '整理目标课程', 'INTEREST', 'INTERMEDIATE', 'ACTIVE',"
        " :now, :now)",
        {"id": course_id, "now": NOW},
        session_factory,
    )


async def seed_item(
    session_factory: async_sessionmaker[AsyncSession],
    index: int,
    *,
    status: str = "ACTIVE",
) -> None:
    await run_sql(
        "INSERT INTO library_items (id, course_id, source_type, title, content_hash,"
        " metadata_json, status, created_at, updated_at)"
        " VALUES (:id, NULL, 'TEXT', :title, :hash, '{}', :status, :now, :now)",
        {
            "id": item_id(index),
            "title": f"条目{index}",
            "hash": f"hash-{index}",
            "status": status,
            "now": NOW,
        },
        session_factory,
    )


async def seed_items(session_factory: async_sessionmaker[AsyncSession], count: int) -> None:
    for index in range(1, count + 1):
        await seed_item(session_factory, index)


async def item_row(
    session_factory: async_sessionmaker[AsyncSession], index: int
) -> tuple[str, str | None, str]:
    async with session_factory() as session:
        row = (
            await session.execute(
                text("SELECT title, course_id, status FROM library_items WHERE id = :id"),
                {"id": item_id(index)},
            )
        ).one()
    return (cast(str, row[0]), row[1], cast(str, row[2]))


async def invoke_plan(
    session_factory: async_sessionmaker[AsyncSession],
    entries: list[dict[str, Any]],
    *,
    auth_mode: AuthMode = AuthMode.REQUEST_APPROVAL,
    session_id: str = SESSION_ID,
) -> dict[str, Any]:
    """直调计划工具（绑定统一运行时上下文的工具层缝隙，先例：操作工具往返）。"""
    token = bind_agent_runtime_context(
        AgentRuntimeContext(
            session_factory=session_factory,
            session_id=session_id,
            auth_mode=auth_mode,
            instruction_excerpt="把这些条目归到整理目标课程",
            message_id="msg-1",
            budget=ToolCallBudget(),
        )
    )
    try:
        raw = await plan_batch_operations.ainvoke({"items": entries})
        return dict(json.loads(raw))
    finally:
        reset_agent_runtime_context(token)


def update_entry(index: int, **overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "action": "update_library_item",
        "item_id": item_id(index),
        "course_id": COURSE_ID,
    }
    entry.update(overrides)
    return entry


def archive_entry(index: int, **overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {"action": "archive_library_item", "item_id": item_id(index)}
    entry.update(overrides)
    return entry


async def confirm(session_factory: async_sessionmaker[AsyncSession], proposal_id: str) -> str:
    async with session_factory() as session:
        result = await ProposalService.confirm(session, proposal_id)
    applied: dict[str, Any] = result.result or {}
    return cast(str, applied["run_id"])


async def plan_proposal_id(result: dict[str, Any]) -> str:
    return cast(str, result["plan_proposal"]["proposal_id"])


async def advance(session_factory: async_sessionmaker[AsyncSession], run_id: str) -> str:
    return await advance_run(session_factory, run_id)


async def switch_session_mode(
    session_factory: async_sessionmaker[AsyncSession], *, from_mode: AuthMode, to_mode: AuthMode
) -> None:
    """会话切档（走真实编排：审计行落定后写运行时覆盖）——调用方负责
    clear_session_auth_override 清理进程级注册表。"""
    await run_sql(
        "INSERT OR IGNORE INTO chat_sessions (id, mode, scope, created_at, updated_at)"
        " VALUES (:id, 'ASK', 'FREE', :now, :now)",
        {"id": SESSION_ID, "now": NOW},
        session_factory,
    )
    async with session_factory() as session:
        await record_session_switch_audit(
            session,
            session_id=SESSION_ID,
            from_mode=from_mode.value,
            to_mode=to_mode.value,
        )


async def run_detail(
    session_factory: async_sessionmaker[AsyncSession], run_id: str
) -> dict[str, Any]:
    async with session_factory() as session:
        return await RunHistoryService.get_run_detail(session, run_id)


async def step_rows(
    session_factory: async_sessionmaker[AsyncSession], run_id: str
) -> list[tuple[str, str, str | None, int, str | None]]:
    """(action, status, error_code, attempts, result_json) 按计划顺序（顺序取
    run 详情的计划投影，行为从表行直读）。"""
    detail = await run_detail(session_factory, run_id)
    order = [item["id"] for item in cast(list[dict[str, Any]], detail["operations"])]
    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT id, action, status, error_code, attempts, result_json"
                    " FROM agent_operations WHERE run_id = :run_id"
                ),
                {"run_id": run_id},
            )
        ).all()
    by_id = {cast(str, row[0]): row for row in rows}
    return [
        (cast(str, row[1]), cast(str, row[2]), row[3], cast(int, row[4]), row[5])
        for row in (by_id[operation_id] for operation_id in order)
    ]


async def statuses(session_factory: async_sessionmaker[AsyncSession], run_id: str) -> list[str]:
    return [
        status
        for _action, status, _code, _attempts, _result in await step_rows(session_factory, run_id)
    ]


async def operation_payloads(
    session_factory: async_sessionmaker[AsyncSession], run_id: str
) -> list[dict[str, Any]]:
    """逐项操作载荷（append 顺序），按计划顺序取详情再映射表行。"""
    detail = await run_detail(session_factory, run_id)
    order = [item["id"] for item in cast(list[dict[str, Any]], detail["operations"])]
    async with session_factory() as session:
        rows = (
            await session.execute(
                text("SELECT id, payload_json FROM agent_operations WHERE run_id = :run_id"),
                {"run_id": run_id},
            )
        ).all()
    by_id = {cast(str, row[0]): cast(str, row[1]) for row in rows}
    return [cast(dict[str, Any], json.loads(by_id[operation_id])) for operation_id in order]


async def job_statuses(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[tuple[str, str]]:
    async with session_factory() as session:
        rows = (
            await session.execute(
                text("SELECT job_type, status FROM processing_jobs ORDER BY created_at, id")
            )
        ).all()
    return [(cast(str, row[0]), cast(str, row[1])) for row in rows]


async def project_stale(
    session_factory: async_sessionmaker[AsyncSession], index: int, *, title: str = "用户改过"
) -> None:
    """模拟用户在批准 / 推进之间改动了目标（快照重验失效）。"""
    await run_sql(
        "UPDATE library_items SET title = :title, updated_at = :now WHERE id = :id",
        {"id": item_id(index), "title": title, "now": LATER},
        session_factory,
    )


# ---------------------------------------------------------------------------
# 工具层分流（先例：操作工具往返测试）


@pytest.mark.anyio
async def test_request_approval_creates_plan_card_without_business_fact(
    tmp_path: Path,
) -> None:
    """默认档：计划卡＝提案，确认前无 Run / 无 operation / 条目未变。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 2)
        result = await invoke_plan(session_factory, [update_entry(1), archive_entry(2)])

        assert result["ok"] is True
        assert result["plan_proposal"]["plan_version"] == 1
        assert result["plan_proposal"]["item_count"] == 2
        async with session_factory() as session:
            proposal = await ProposalService._get(  # pyright: ignore[reportPrivateUsage]
                session, await plan_proposal_id(result)
            )
            assert proposal.proposal_type == ProposalType.OP_BATCH.value
            assert proposal.status == "PENDING"
            assert (
                cast(dict[str, Any], proposal.__dict__ and json.loads(proposal.payload_json))[
                    "plan_version"
                ]
                == 1
            )
        assert await count_rows(session_factory, "SELECT count(*) FROM agent_runs") == 0
        assert await count_rows(session_factory, "SELECT count(*) FROM agent_operations") == 0
        assert await count_rows(session_factory, "SELECT count(*) FROM processing_jobs") == 0
        assert await item_row(session_factory, 1) == ("条目1", None, "ACTIVE")


@pytest.mark.anyio
async def test_auto_approve_within_threshold_creates_run_directly(tmp_path: Path) -> None:
    """帮我批准档阈值内：直建 Run＋PLANNED operations＋AGENT_RUN 触发 job。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 3)
        result = await invoke_plan(
            session_factory,
            [update_entry(1), update_entry(2), archive_entry(3)],
            auth_mode=AuthMode.AUTO_APPROVE,
        )

        assert result["run"]["added_item_count"] == 3
        run_id = cast(str, result["run"]["run_id"])
        steps = await step_rows(session_factory, run_id)
        assert [(action, status) for action, status, _c, _a, _r in steps] == [
            ("update_library_item", "PLANNED"),
            ("update_library_item", "PLANNED"),
            ("archive_library_item", "PLANNED"),
        ]
        assert await count_rows(session_factory, "SELECT count(*) FROM agent_proposals") == 0
        assert await job_statuses(session_factory) == [("AGENT_RUN", "PENDING")]
        detail = await run_detail(session_factory, run_id)
        assert detail["auth_mode"] == "AUTO_APPROVE"
        assert detail["instruction_text"] == "把这些条目归到整理目标课程"
        assert cast(dict[str, Any], detail["operations"][0]["authorization"])["trigger"] == (
            "AUTO_EXECUTED"
        )
        # 推进前零业务事实（计划只是登记待执行项）。
        assert await item_row(session_factory, 1) == ("条目1", None, "ACTIVE")


@pytest.mark.anyio
async def test_auto_approve_over_threshold_still_plans(tmp_path: Path) -> None:
    """超阈值（同一任务直接业务目标数 >10）仍出计划卡。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 11)
        entries = [update_entry(index) for index in range(1, 12)]
        result = await invoke_plan(session_factory, entries, auth_mode=AuthMode.AUTO_APPROVE)

        assert "plan_proposal" in result
        assert await count_rows(session_factory, "SELECT count(*) FROM agent_runs") == 0
        assert await count_rows(session_factory, "SELECT count(*) FROM agent_operations") == 0


@pytest.mark.anyio
async def test_auto_approve_split_calls_accumulate_toward_threshold(tmp_path: Path) -> None:
    """拆工具调用不重置：累计目标数超阈值 → 第二次提交升回计划卡。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 12)
        entries = [update_entry(index) for index in range(1, 13)]
        first = await invoke_plan(session_factory, entries[:6], auth_mode=AuthMode.AUTO_APPROVE)
        assert "run" in first
        # 阈值内补齐（6 + 4 = 10）仍直执行。
        within = await invoke_plan(session_factory, entries[6:10], auth_mode=AuthMode.AUTO_APPROVE)
        assert within["run"]["added_item_count"] == 4
        # 再补 2 项累计 12 > 10 → 计划卡，且绑定同一活跃 Run（确认后延展）。
        over = await invoke_plan(session_factory, entries[10:], auth_mode=AuthMode.AUTO_APPROVE)
        assert "plan_proposal" in over
        async with session_factory() as session:
            proposal = await ProposalService._get(  # pyright: ignore[reportPrivateUsage]
                session, await plan_proposal_id(over)
            )
        assert proposal.target_type == plans.PLAN_TARGET_TYPE
        assert proposal.target_id == first["run"]["run_id"]
        assert await count_rows(session_factory, "SELECT count(*) FROM agent_operations") == 10


@pytest.mark.anyio
async def test_auto_approve_threshold_survives_completed_run(tmp_path: Path) -> None:
    """阈值会话累计不重置（工单 05 review）：首批 6 项完成（Run 落终态）后再提交
    6 项，累计 12 > 10 → 仍出计划卡、不新建第二个自动 Run（spec 决策 11：计入
    已完成项，拆调用 / 分段 / 重启不重置）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 12)
        entries = [update_entry(index) for index in range(1, 13)]
        first = await invoke_plan(session_factory, entries[:6], auth_mode=AuthMode.AUTO_APPROVE)
        assert first["run"]["added_item_count"] == 6
        assert await advance(session_factory, first["run"]["run_id"]) == "COMPLETED"

        second = await invoke_plan(session_factory, entries[6:], auth_mode=AuthMode.AUTO_APPROVE)
        assert second["plan_proposal"]["item_count"] == 6
        assert await count_rows(session_factory, "SELECT count(*) FROM agent_runs") == 1
        assert await count_rows(session_factory, "SELECT count(*) FROM agent_operations") == 6
        assert await item_row(session_factory, 1) == ("条目1", COURSE_ID, "ACTIVE")
        assert await item_row(session_factory, 7) == ("条目7", None, "ACTIVE")


@pytest.mark.anyio
async def test_auto_approve_threshold_accumulates_across_completed_runs(tmp_path: Path) -> None:
    """分段执行不重置（工单 05 review）：6 完成 → 4（累计 10）仍直执行 → 2（累计
    12）出计划卡——计数跨多个已结束 Run 累计，不是只看最近一个。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 12)
        entries = [update_entry(index) for index in range(1, 13)]
        first = await invoke_plan(session_factory, entries[:6], auth_mode=AuthMode.AUTO_APPROVE)
        assert await advance(session_factory, first["run"]["run_id"]) == "COMPLETED"

        second = await invoke_plan(session_factory, entries[6:10], auth_mode=AuthMode.AUTO_APPROVE)
        assert second["run"]["added_item_count"] == 4
        assert await advance(session_factory, second["run"]["run_id"]) == "COMPLETED"

        over = await invoke_plan(session_factory, entries[10:], auth_mode=AuthMode.AUTO_APPROVE)
        assert "plan_proposal" in over
        assert await count_rows(session_factory, "SELECT count(*) FROM agent_runs") == 2
        assert await count_rows(session_factory, "SELECT count(*) FROM agent_operations") == 10


@pytest.mark.anyio
async def test_auto_approve_threshold_counts_per_session(tmp_path: Path) -> None:
    """计数按会话（工单 05 review）：另一会话不背前一会话的已用额度——阈值锚点是
    本会话的任务链，不是全局计数。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 12)
        entries = [update_entry(index) for index in range(1, 13)]
        first = await invoke_plan(session_factory, entries[:6], auth_mode=AuthMode.AUTO_APPROVE)
        assert await advance(session_factory, first["run"]["run_id"]) == "COMPLETED"

        other = await invoke_plan(
            session_factory,
            entries[6:],
            auth_mode=AuthMode.AUTO_APPROVE,
            session_id="sess-batch-other",
        )
        assert other["run"]["added_item_count"] == 6


@pytest.mark.anyio
async def test_full_access_ignores_threshold_but_keeps_fixed_plan(tmp_path: Path) -> None:
    """完全访问档：不受阈值限制直建 Run；执行中新增目标超出固定计划集合 →
    升回确认（确认后延展同一 Run）；已覆盖目标重复提交不新增（幂等）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 15)
        entries = [archive_entry(index) for index in range(1, 16)]
        first = await invoke_plan(session_factory, entries[:12], auth_mode=AuthMode.FULL_ACCESS)
        assert first["run"]["added_item_count"] == 12
        run_id = cast(str, first["run"]["run_id"])

        over = await invoke_plan(session_factory, entries[12:], auth_mode=AuthMode.FULL_ACCESS)
        assert "plan_proposal" in over
        assert await confirm(session_factory, await plan_proposal_id(over)) == run_id
        assert await count_rows(session_factory, "SELECT count(*) FROM agent_operations") == 15

        again = await invoke_plan(session_factory, entries[:12], auth_mode=AuthMode.FULL_ACCESS)
        assert again["run"]["added_item_count"] == 0
        assert "已在执行计划中" in cast(str, again["run"]["detail"])
        assert await count_rows(session_factory, "SELECT count(*) FROM agent_operations") == 15


@pytest.mark.anyio
async def test_approved_plan_run_replan_requires_confirmation(tmp_path: Path) -> None:
    """已批准计划的 Run 目标超出已批准集合 → 升回确认（完全访问档亦然）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 3)
        planned = await invoke_plan(session_factory, [update_entry(1), update_entry(2)])
        run_id = await confirm(session_factory, await plan_proposal_id(planned))

        replan = await invoke_plan(
            session_factory, [update_entry(3)], auth_mode=AuthMode.FULL_ACCESS
        )
        assert "plan_proposal" in replan
        async with session_factory() as session:
            proposal = await ProposalService._get(  # pyright: ignore[reportPrivateUsage]
                session, await plan_proposal_id(replan)
            )
        assert (proposal.target_type, proposal.target_id) == (plans.PLAN_TARGET_TYPE, run_id)
        # 确认后延展同一 Run（版本递增、计划项追加），不新建第二个任务。
        assert await confirm(session_factory, await plan_proposal_id(replan)) == run_id
        detail = await run_detail(session_factory, run_id)
        assert detail["plan_version"] == 2
        assert len(cast(dict[str, Any], detail["plan"])["items"]) == 3
        assert len(await step_rows(session_factory, run_id)) == 3


@pytest.mark.anyio
async def test_plan_payload_violations_report_structurally(tmp_path: Path) -> None:
    """计划项校验失败：结构化返回（缺项 / 非法动作 / 未知键 / 目标不可达）零业务事实。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_item(session_factory, 1)
        missing = await invoke_plan(session_factory, [archive_entry(1, action=None)])
        assert missing["ok"] is False
        assert "items.0.action" in missing["missing"]
        unknown = await invoke_plan(session_factory, [archive_entry(1, favorite=True)])
        assert unknown["ok"] is False
        assert unknown["error"] == "PROPOSAL_PAYLOAD_INVALID"
        bad_action = await invoke_plan(
            session_factory, [{"action": "drop_table", "item_id": item_id(1)}]
        )
        assert bad_action["ok"] is False
        # 目标条目不可达（不存在）→ 提交即结构化拒绝，不落提案也不建 Run。
        unreachable = await invoke_plan(session_factory, [archive_entry(99)])
        assert unreachable["ok"] is False
        assert unreachable["error"] == "LIBRARY_ITEM_NOT_FOUND"
        assert await count_rows(session_factory, "SELECT count(*) FROM agent_runs") == 0
        assert await count_rows(session_factory, "SELECT count(*) FROM agent_proposals") == 0


# ---------------------------------------------------------------------------
# 确认与应用层（先例：library 提案测试）


@pytest.mark.anyio
async def test_confirm_plan_creates_run_with_snapshots_and_trigger(tmp_path: Path) -> None:
    """确认计划卡：Run 固化授权依据＋逐项快照随 operation，触发 job 投递。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 2)
        planned = await invoke_plan(session_factory, [update_entry(1), archive_entry(2)])
        proposal_id = await plan_proposal_id(planned)
        run_id = await confirm(session_factory, proposal_id)

        detail = await run_detail(session_factory, run_id)
        assert detail["status"] == "RUNNING"
        assert detail["auth_mode"] == "REQUEST_APPROVAL"
        assert detail["instruction_text"] == "把这些条目归到整理目标课程"
        assert detail["proposal_id"] == proposal_id
        assert [item["action"] for item in cast(dict[str, Any], detail["plan"])["items"]] == [
            "update_library_item",
            "archive_library_item",
        ]
        operations = cast(list[dict[str, Any]], detail["operations"])
        assert [operation["status"] for operation in operations] == ["PLANNED", "PLANNED"]
        assert [operation["proposal_id"] for operation in operations] == [proposal_id, proposal_id]
        assert [operation["target_id"] for operation in operations] == [item_id(1), item_id(2)]
        for operation, title in zip(operations, ("条目1", "条目2"), strict=True):
            snapshot = cast(dict[str, Any], operation["snapshot"])
            assert snapshot["title"] == title
            assert snapshot["status"] == "ACTIVE"
            assert "updated_at" in snapshot
            authorization = cast(dict[str, Any], operation["authorization"])
            assert authorization["trigger"] == "USER_CONFIRMED_PROPOSAL"
            assert authorization["instruction_excerpt"] == "把这些条目归到整理目标课程"
            assert authorization["session_id"] == SESSION_ID
        assert await job_statuses(session_factory) == [("AGENT_RUN", "PENDING")]


@pytest.mark.anyio
async def test_confirm_plan_after_target_changed_is_stale(tmp_path: Path) -> None:
    """预览后目标被改：确认失效（OPERATION_SNAPSHOT_STALE），不新建 Run。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_item(session_factory, 1)
        planned = await invoke_plan(session_factory, [archive_entry(1)])
        await project_stale(session_factory, 1)

        with pytest.raises(CodedHTTPException) as exc:
            await confirm(session_factory, await plan_proposal_id(planned))
        assert exc.value.code == "PROPOSAL_APPLY_FAILED"
        assert exc.value.params == {"errorCode": "OPERATION_SNAPSHOT_STALE"}
        assert await count_rows(session_factory, "SELECT count(*) FROM agent_runs") == 0
        assert await count_rows(session_factory, "SELECT count(*) FROM processing_jobs") == 0


@pytest.mark.anyio
async def test_confirm_plan_carries_dependencies_between_steps(tmp_path: Path) -> None:
    """依赖声明：同批内索引解析为 operation id（推进与重试的依赖判定口径）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 2)
        planned = await invoke_plan(
            session_factory, [update_entry(1), archive_entry(2, depends_on=[0])]
        )
        run_id = await confirm(session_factory, await plan_proposal_id(planned))
        detail = await run_detail(session_factory, run_id)
        items = cast(dict[str, Any], detail["plan"])["items"]
        operations = cast(list[dict[str, Any]], detail["operations"])
        assert items[0]["depends_on"] == []
        assert items[1]["depends_on"] == [operations[0]["id"]]


# ---------------------------------------------------------------------------
# Run 推进（先例：test_job_runner 的 WorkerSpec 缝隙）


@pytest.mark.anyio
async def test_advance_executes_all_steps_and_completes(tmp_path: Path) -> None:
    """逐项推进：条目真实变更、逐项结果回填、全部成功＝COMPLETED。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 2)
        direct = await invoke_plan(
            session_factory,
            [update_entry(1), archive_entry(2)],
            auth_mode=AuthMode.AUTO_APPROVE,
        )
        run_id = cast(str, direct["run"]["run_id"])

        assert await advance(session_factory, run_id) == "COMPLETED"
        steps = await step_rows(session_factory, run_id)
        assert [status for _action, status, _c, _a, _r in steps] == ["SUCCEEDED", "SUCCEEDED"]
        assert await item_row(session_factory, 1) == ("条目1", COURSE_ID, "ACTIVE")
        assert await item_row(session_factory, 2) == ("条目2", None, "ARCHIVED")
        updated = cast(dict[str, Any], json.loads(cast(str, steps[0][4])))
        assert cast(dict[str, Any], updated["after"])["course_id"] == COURSE_ID
        assert cast(dict[str, Any], json.loads(cast(str, steps[1][4]))) == {
            "item_id": item_id(2),
            "status": "ARCHIVED",
        }


@pytest.mark.anyio
async def test_advance_partial_failure_continues_independent_items(tmp_path: Path) -> None:
    """部分失败：单项领域拒绝不阻断独立项，终态 PARTIAL_COMPLETED。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 3)
        await seed_item(session_factory, 4, status="ARCHIVED")
        direct = await invoke_plan(
            session_factory,
            [archive_entry(1), archive_entry(4), archive_entry(2)],
            auth_mode=AuthMode.AUTO_APPROVE,
        )
        run_id = cast(str, direct["run"]["run_id"])

        assert await advance(session_factory, run_id) == "PARTIAL_COMPLETED"
        steps = await step_rows(session_factory, run_id)
        assert [status for _action, status, _c, _a, _r in steps] == [
            "SUCCEEDED",
            "FAILED",
            "SUCCEEDED",
        ]
        assert steps[1][2] == "LIBRARY_ITEM_ALREADY_ARCHIVED"
        assert steps[1][3] == 1
        assert await item_row(session_factory, 2) == ("条目2", None, "ARCHIVED")


@pytest.mark.anyio
async def test_advance_dependency_failure_skips_blocked_steps(tmp_path: Path) -> None:
    """依赖失败：后续步骤置 SKIPPED（依赖阻塞错误码），不执行领域写入。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 3)
        await seed_item(session_factory, 4, status="ARCHIVED")
        direct = await invoke_plan(
            session_factory,
            [archive_entry(4), update_entry(2, depends_on=[0])],
            auth_mode=AuthMode.AUTO_APPROVE,
        )
        run_id = cast(str, direct["run"]["run_id"])

        assert await advance(session_factory, run_id) == "PARTIAL_COMPLETED"
        steps = await step_rows(session_factory, run_id)
        assert [status for _action, status, _c, _a, _r in steps] == ["FAILED", "SKIPPED"]
        assert steps[1][2] == "OPERATION_DEPENDENCY_FAILED"
        assert await item_row(session_factory, 2) == ("条目2", None, "ACTIVE")


@pytest.mark.anyio
async def test_q1_conflict_wait_restart_resolve_and_continue(tmp_path: Path) -> None:
    """Q1 验收场景：三项任务后两项成功后一项冲突 → 等待 → 重启接续 → 重新预览
    授权后继续完成，已成功项零重做。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 3)
        planned = await invoke_plan(
            session_factory,
            [archive_entry(1), archive_entry(2), archive_entry(3)],
        )
        run_id = await confirm(session_factory, await plan_proposal_id(planned))

        # 第三项在推进前被用户改动 → 快照失效（冲突）。
        await project_stale(session_factory, 3)
        assert await advance(session_factory, run_id) == "WAITING_USER"
        detail = await run_detail(session_factory, run_id)
        assert detail["waiting_reason"] == "OPERATION_SNAPSHOT_STALE"
        assert await statuses(session_factory, run_id) == ["SUCCEEDED", "SUCCEEDED", "FAILED"]

        # 重启接续：等待态不自动推进（唤醒只由显式动作触发）。
        assert await advance(session_factory, run_id) == "WAITING_USER"
        assert await statuses(session_factory, run_id) == ["SUCCEEDED", "SUCCEEDED", "FAILED"]

        # 处理冲突：为该目标重新预览授权（计划卡，版本递增，延展同一 Run）。
        replan = await invoke_plan(session_factory, [archive_entry(3)])
        assert "plan_proposal" in replan
        assert await confirm(session_factory, await plan_proposal_id(replan)) == run_id
        detail = await run_detail(session_factory, run_id)
        assert detail["status"] == "RUNNING"
        assert detail["plan_version"] == 2

        # 继续完成剩余项：前三项不重做（attempts 恒 1），新增的授权步骤成功。
        assert await advance(session_factory, run_id) == "COMPLETED"
        steps = await step_rows(session_factory, run_id)
        assert [status for _action, status, _c, _a, _r in steps] == [
            "SUCCEEDED",
            "SUCCEEDED",
            "FAILED",
            "SUCCEEDED",
        ]
        assert [attempts for _action, _s, _c, attempts, _r in steps] == [1, 1, 1, 1]
        assert await item_row(session_factory, 3) == ("用户改过", None, "ARCHIVED")


@pytest.mark.anyio
async def test_advance_cancelled_keeps_committed_results(tmp_path: Path) -> None:
    """取消：推进中每步检查，不再新增动作、未执行项置 CANCELLED、已提交保留。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 3)
        direct = await invoke_plan(
            session_factory,
            [archive_entry(1), archive_entry(2), archive_entry(3)],
            auth_mode=AuthMode.AUTO_APPROVE,
        )
        run_id = cast(str, direct["run"]["run_id"])
        async with session_factory() as session:
            requested = await RunControlService.cancel_run(session, run_id)
        # 推进未在跑：状态待 worker 收尾（不谎报已取消）。
        assert requested["cancel_requested"] is True
        assert requested["status"] == "RUNNING"

        assert await advance(session_factory, run_id) == "CANCELLED"
        assert await statuses(session_factory, run_id) == [
            "CANCELLED",
            "CANCELLED",
            "CANCELLED",
        ]
        assert await item_row(session_factory, 1) == ("条目1", None, "ACTIVE")


@pytest.mark.anyio
async def test_cancel_waiting_run_settles_immediately(tmp_path: Path) -> None:
    """等待态取消：无 worker 在跑即刻落 CANCELLED，已成功项保留。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 2)
        planned = await invoke_plan(session_factory, [archive_entry(1), archive_entry(2)])
        run_id = await confirm(session_factory, await plan_proposal_id(planned))
        await project_stale(session_factory, 2)
        assert await advance(session_factory, run_id) == "WAITING_USER"

        async with session_factory() as session:
            cancelled = await RunControlService.cancel_run(session, run_id)
        assert cancelled["status"] == "CANCELLED"
        # 冲突项此前已落 FAILED（取消不改写已定结局），未执行项收编为 CANCELLED。
        assert await statuses(session_factory, run_id) == ["SUCCEEDED", "FAILED"]
        # 已结束的 Run 不能再取消。
        with pytest.raises(CodedHTTPException) as exc:
            async with session_factory() as session:
                await RunControlService.cancel_run(session, run_id)
        assert exc.value.code == "AGENT_RUN_ALREADY_FINISHED"


@pytest.mark.anyio
async def test_retry_failed_step_restores_blocked_steps_same_identity(tmp_path: Path) -> None:
    """失败项重试：沿用原 operation 身份（attempts 递增）并恢复依赖跳过项；
    快照冲突未重新预览时推进仍转等待（不覆盖用户后续修改）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 3)
        await seed_item(session_factory, 4, status="ARCHIVED")
        direct = await invoke_plan(
            session_factory,
            [archive_entry(4), update_entry(2, depends_on=[0])],
            auth_mode=AuthMode.AUTO_APPROVE,
        )
        run_id = cast(str, direct["run"]["run_id"])
        assert await advance(session_factory, run_id) == "PARTIAL_COMPLETED"
        detail = await run_detail(session_factory, run_id)
        operations = cast(list[dict[str, Any]], detail["operations"])

        # 用户修复领域前置条件（条目回到 ACTIVE）后重试失败项：部分完成的任务重开推进。
        await run_sql(
            "UPDATE library_items SET status = 'ACTIVE', updated_at = :now WHERE id = :id",
            {"id": item_id(4), "now": LATER},
            session_factory,
        )
        async with session_factory() as session:
            retried = await RunControlService.retry_operation(
                session, run_id=run_id, operation_id=operations[0]["id"]
            )
        assert retried["status"] == "RUNNING"
        steps = await step_rows(session_factory, run_id)
        assert [status for _action, status, _c, _a, _r in steps] == ["PLANNED", "PLANNED"]
        assert [attempts for _action, _s, _c, attempts, _r in steps] == [2, 1]
        assert await count_rows(session_factory, "SELECT count(*) FROM agent_operations") == 2
        # 目标自批准以来已变化（updated_at 前进）：重试沿用旧快照仍失效 → 转等待，
        # 需重新预览授权（旧批准作废，spec 决策 12）。等待即停止推进，依赖项仍待执行。
        assert await advance(session_factory, run_id) == "WAITING_USER"
        steps = await step_rows(session_factory, run_id)
        assert [status for _action, status, _c, _a, _r in steps] == ["FAILED", "PLANNED"]
        assert steps[0][2] == "OPERATION_SNAPSHOT_STALE"
        # 未失败项拒绝重试。
        with pytest.raises(CodedHTTPException) as exc:
            async with session_factory() as session:
                await RunControlService.retry_operation(
                    session, run_id=run_id, operation_id=operations[1]["id"]
                )
        assert exc.value.code == "AGENT_RUN_OPERATION_NOT_RETRYABLE"


@pytest.mark.anyio
async def test_resume_claims_atomically(tmp_path: Path) -> None:
    """继续指令：仅等待态可继续，原子抢占（并发继续只有一个成功），
    唤醒后推进剩余未执行项、冲突项保持既定结局。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 4)
        planned = await invoke_plan(
            session_factory,
            [archive_entry(1), archive_entry(2), archive_entry(3), archive_entry(4)],
        )
        run_id = await confirm(session_factory, await plan_proposal_id(planned))
        await project_stale(session_factory, 2)
        assert await advance(session_factory, run_id) == "WAITING_USER"
        assert await statuses(session_factory, run_id) == [
            "SUCCEEDED",
            "FAILED",
            "PLANNED",
            "PLANNED",
        ]

        async with session_factory() as session:
            resumed = await RunControlService.resume_run(session, run_id)
        assert resumed["status"] == "RUNNING"
        assert resumed["waiting_reason"] is None
        with pytest.raises(CodedHTTPException) as exc:
            async with session_factory() as session:
                await RunControlService.resume_run(session, run_id)
        assert exc.value.code == "AGENT_RUN_NOT_WAITING"
        # 唤醒已投递触发：剩余未执行项推进，冲突项保持 FAILED（不猜测自动重试）。
        assert await advance(session_factory, run_id) == "PARTIAL_COMPLETED"
        assert await statuses(session_factory, run_id) == [
            "SUCCEEDED",
            "FAILED",
            "SUCCEEDED",
            "SUCCEEDED",
        ]


@pytest.mark.anyio
async def test_recovery_requeues_running_run_without_active_trigger(tmp_path: Path) -> None:
    """重启恢复：RUNNING 且无活动触发 job 的 Run 重投触发；已成功项不重做。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 2)
        direct = await invoke_plan(
            session_factory, [archive_entry(1), archive_entry(2)], auth_mode=AuthMode.FULL_ACCESS
        )
        run_id = cast(str, direct["run"]["run_id"])
        # 模拟崩溃恢复：活动触发已被先例流程翻 FAILED。
        await run_sql(
            "UPDATE processing_jobs SET status = 'FAILED', finished_at = :now"
            " WHERE job_type = 'AGENT_RUN'",
            {"now": NOW},
            session_factory,
        )
        assert await job_statuses(session_factory) == [("AGENT_RUN", "FAILED")]

        spec = agent_run_spec(session_factory, RecordInvalidationNotifier())
        await spec.recover_interrupted()
        assert await job_statuses(session_factory) == [
            ("AGENT_RUN", "FAILED"),
            ("AGENT_RUN", "PENDING"),
        ]
        # 重复恢复不重复投递（同 Run 至多一个活动触发）。
        await spec.recover_interrupted()
        assert (
            await count_rows(
                session_factory,
                "SELECT count(*) FROM processing_jobs WHERE status = 'PENDING'",
            )
            == 1
        )
        assert await advance(session_factory, run_id) == "COMPLETED"
        assert await statuses(session_factory, run_id) == ["SUCCEEDED", "SUCCEEDED"]
        assert [
            attempts for _a, _s, _c, attempts, _r in await step_rows(session_factory, run_id)
        ] == [1, 1]


@pytest.mark.anyio
async def test_claim_guard_only_accepts_running_runs(tmp_path: Path) -> None:
    """领取守卫：等待 / 终态 Run 的残留触发被作废（推进只认 RUNNING）；同一 Run
    至多一个活动触发 job 由部分唯一索引在存储层保证。"""
    async with bare_db(tmp_path) as session_factory:
        await run_sql(
            "INSERT INTO agent_runs (id, session_id, auth_mode, status, plan_version,"
            " cancel_requested, created_at, updated_at)"
            " VALUES (:id, :session_id, 'REQUEST_APPROVAL', 'WAITING_USER', 1, 0, :now, :now)",
            {"id": RUN_ID, "session_id": SESSION_ID, "now": NOW},
            session_factory,
        )
        trigger_sql = (
            "INSERT INTO processing_jobs (id, job_type, status, progress, attempts,"
            " max_attempts, input_json, created_at, updated_at)"
            " VALUES (:id, 'AGENT_RUN', 'PENDING', 0, 0, 1, :input, :now, :now)"
        )
        await run_sql(
            trigger_sql,
            {"id": "job-1", "input": json.dumps({"run_id": RUN_ID}), "now": NOW},
            session_factory,
        )
        spec = agent_run_spec(session_factory, RecordInvalidationNotifier())
        async with session_factory() as session:
            job = await spec.find_candidate(session, datetime(2026, 9, 26, 8, 0, tzinfo=UTC))
            assert job is not None
            decision = await spec.validate_claim(session, job, "", None)
        assert isinstance(decision, CancelClaim)
        assert decision.reason == "run_not_running"

        with pytest.raises(Exception, match="UNIQUE"):
            await run_sql(
                trigger_sql,
                {"id": "job-2", "input": json.dumps({"run_id": RUN_ID}), "now": NOW},
                session_factory,
            )


# ---------------------------------------------------------------------------
# 会话上下文注入（工单 05：未结束任务摘要＝提示非指令）


@pytest.mark.anyio
async def test_active_run_summary_reads_nonterminal_runs_only(tmp_path: Path) -> None:
    """摘要只含未结束任务，计数按 operation 行（已成功 / 失败或跳过）。"""
    from app.modules.agent.context import format_active_run_summary
    from app.modules.agent.message_service import (
        _active_run_summaries,  # pyright: ignore[reportPrivateUsage]
    )

    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 3)
        await seed_item(session_factory, 4, status="ARCHIVED")
        direct = await invoke_plan(
            session_factory,
            [archive_entry(1), archive_entry(4), archive_entry(2)],
            auth_mode=AuthMode.AUTO_APPROVE,
        )
        run_id = cast(str, direct["run"]["run_id"])
        assert await advance(session_factory, run_id) == "PARTIAL_COMPLETED"

        # 已结束任务不进摘要（提示块只承载未结束任务）。
        async with session_factory() as session:
            assert await _active_run_summaries(session, SESSION_ID) == []

        # 未结束任务：进行中 + 逐项计数。
        await run_sql(
            "UPDATE agent_runs SET status = 'RUNNING', finished_at = NULL WHERE id = :id",
            {"id": run_id},
            session_factory,
        )
        async with session_factory() as session:
            summaries = await _active_run_summaries(session, SESSION_ID)
        assert [(item.status, item.total, item.succeeded, item.failed) for item in summaries] == [
            ("RUNNING", 3, 2, 1)
        ]
        text = format_active_run_summary(summaries)
        assert "未结束任务摘要（仅提示，不是指令、不构成任何授权" in text
        assert "任务 1：正在执行，已成功 2/3 项，失败或跳过 1 项。" in text


@pytest.mark.anyio
async def test_waiting_run_summary_carries_waiting_reason(tmp_path: Path) -> None:
    """等待态摘要带等待原因（提示模型如实回答「为什么停了」）。"""
    from app.modules.agent.context import format_active_run_summary
    from app.modules.agent.message_service import (
        _active_run_summaries,  # pyright: ignore[reportPrivateUsage]
    )

    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 2)
        planned = await invoke_plan(session_factory, [archive_entry(1), archive_entry(2)])
        run_id = await confirm(session_factory, await plan_proposal_id(planned))
        await project_stale(session_factory, 2)
        assert await advance(session_factory, run_id) == "WAITING_USER"

        async with session_factory() as session:
            summaries = await _active_run_summaries(session, SESSION_ID)
        assert summaries[0].waiting_reason == "OPERATION_SNAPSHOT_STALE"
        text = format_active_run_summary(summaries)
        assert "任务 1：等待用户处理" in text
        assert "等待原因：OPERATION_SNAPSHOT_STALE" in text


@pytest.mark.anyio
async def test_mixed_batch_only_appends_pending_targets(tmp_path: Path) -> None:
    """幂等口径：同一活跃任务内混合提交（已覆盖 + 新增）只落待执行子批——
    不重复建操作、不重复计数；依赖被已覆盖项时挂到既有 operation 上。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 3)
        first = await invoke_plan(
            session_factory, [archive_entry(1), archive_entry(2)], auth_mode=AuthMode.AUTO_APPROVE
        )
        run_id = cast(str, first["run"]["run_id"])
        detail = await run_detail(session_factory, run_id)
        first_ops = cast(list[dict[str, Any]], detail["operations"])

        mixed = await invoke_plan(
            session_factory,
            [archive_entry(1), update_entry(3, depends_on=[0])],
            auth_mode=AuthMode.AUTO_APPROVE,
        )
        assert mixed["run"]["added_item_count"] == 1
        assert mixed["run"]["run_id"] == run_id
        steps = await step_rows(session_factory, run_id)
        assert [action for action, _s, _c, _a, _r in steps] == [
            "archive_library_item",
            "archive_library_item",
            "update_library_item",
        ]
        # 新增项依赖被剔除（已在计划内）项：依赖解析为既有 operation id。
        detail = await run_detail(session_factory, run_id)
        plan_items = cast(dict[str, Any], detail["plan"])["items"]
        assert plan_items[2]["depends_on"] == [first_ops[0]["id"]]

        assert await advance(session_factory, run_id) == "COMPLETED"
        steps = await step_rows(session_factory, run_id)
        assert [status for _a, status, _c, _a2, _r in steps] == [
            "SUCCEEDED",
            "SUCCEEDED",
            "SUCCEEDED",
        ]
        assert await item_row(session_factory, 1) == ("条目1", None, "ARCHIVED")
        assert await item_row(session_factory, 3) == ("条目3", COURSE_ID, "ACTIVE")


@pytest.mark.anyio
async def test_waiting_run_append_requires_confirmation(tmp_path: Path) -> None:
    """等待态 Run 只接受显式唤醒：工具追加目标转计划卡，确认即继续执行。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 3)
        planned = await invoke_plan(session_factory, [archive_entry(1), archive_entry(2)])
        run_id = await confirm(session_factory, await plan_proposal_id(planned))
        await project_stale(session_factory, 2)
        assert await advance(session_factory, run_id) == "WAITING_USER"

        appended = await invoke_plan(
            session_factory, [archive_entry(3)], auth_mode=AuthMode.FULL_ACCESS
        )
        assert "plan_proposal" in appended
        assert await confirm(session_factory, await plan_proposal_id(appended)) == run_id
        detail = await run_detail(session_factory, run_id)
        assert detail["status"] == "RUNNING"


@pytest.mark.anyio
async def test_second_plan_card_confirmed_extends_first_run(tmp_path: Path) -> None:
    """两张计划卡先后确认：延展同一 Run、已覆盖项不重复建操作（以免重复执行）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 3)
        first = await invoke_plan(session_factory, [archive_entry(1), archive_entry(2)])
        second = await invoke_plan(session_factory, [archive_entry(2), archive_entry(3)])
        run_id = await confirm(session_factory, await plan_proposal_id(first))
        same_run = await confirm(session_factory, await plan_proposal_id(second))
        assert same_run == run_id
        detail = await run_detail(session_factory, run_id)
        # 条目一、条目二、条目三各一条操作（条目二不重复建）。
        assert len(cast(list[dict[str, Any]], detail["operations"])) == 3
        assert await count_rows(session_factory, "SELECT count(*) FROM agent_runs") == 1
        assert await advance(session_factory, run_id) == "COMPLETED"
        assert await statuses(session_factory, run_id) == [
            "SUCCEEDED",
            "SUCCEEDED",
            "SUCCEEDED",
        ]


@pytest.mark.anyio
async def test_cancel_rejects_finished_run(tmp_path: Path) -> None:
    """已收尾的任务拒绝取消（取消不冒充撤销；失败项重试另有端点会重开推进）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 2)
        await seed_item(session_factory, 3, status="ARCHIVED")
        direct = await invoke_plan(
            session_factory,
            [archive_entry(1), archive_entry(3)],
            auth_mode=AuthMode.AUTO_APPROVE,
        )
        run_id = cast(str, direct["run"]["run_id"])
        assert await advance(session_factory, run_id) == "PARTIAL_COMPLETED"
        with pytest.raises(CodedHTTPException) as exc:
            async with session_factory() as session:
                await RunControlService.cancel_run(session, run_id)
        assert exc.value.code == "AGENT_RUN_ALREADY_FINISHED"


# ---------------------------------------------------------------------------
# 损坏计划（工单 05 review）：执行停止落稳定错误、取消不依赖计划、写路径拒绝追加


async def corrupt_plan(session_factory: async_sessionmaker[AsyncSession], run_id: str) -> None:
    """模拟 run.plan_json 结构损坏（形状不符 BatchPlanOut）：计划投影不再可信。"""
    await run_sql(
        "UPDATE agent_runs SET plan_json = :bad WHERE id = :id",
        {"bad": '{"plan_version": 1, "items": [{"broken": true}]}', "id": run_id},
        session_factory,
    )


async def job_error_codes(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[tuple[str, str, str | None]]:
    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT job_type, status, error_code FROM processing_jobs"
                    " ORDER BY created_at, id"
                )
            )
        ).all()
    return [(cast(str, row[0]), cast(str, row[1]), row[2]) for row in rows]


@pytest.mark.anyio
async def test_corrupt_plan_stops_run_with_stable_error(tmp_path: Path) -> None:
    """计划损坏：推进停止、零业务事实、Run FAILED、未执行项 SKIPPED、job 记
    AGENT_RUN_PLAN_INVALID（不得降级为空计划继续执行——依赖判定会静默失效）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 2)
        direct = await invoke_plan(
            session_factory,
            [archive_entry(1), archive_entry(2)],
            auth_mode=AuthMode.AUTO_APPROVE,
        )
        run_id = cast(str, direct["run"]["run_id"])
        await corrupt_plan(session_factory, run_id)

        runner = JobRunner(
            agent_run_spec(session_factory, RecordInvalidationNotifier()),
            session_factory,
            RecordInvalidationNotifier(),
        )
        assert await runner.process_one() is True

        # 一条操作都没执行：业务事实零变化。
        assert await item_row(session_factory, 1) == ("条目1", None, "ACTIVE")
        assert await item_row(session_factory, 2) == ("条目2", None, "ACTIVE")
        detail = await run_detail(session_factory, run_id)
        assert detail["status"] == "FAILED"
        assert await statuses(session_factory, run_id) == ["SKIPPED", "SKIPPED"]
        assert await job_error_codes(session_factory) == [
            ("AGENT_RUN", "FAILED", "AGENT_RUN_PLAN_INVALID")
        ]


@pytest.mark.anyio
async def test_cancel_on_corrupt_plan_still_cancels(tmp_path: Path) -> None:
    """取消不依赖计划：计划损坏时用户取消仍按用户动作收尾（CANCELLED），
    不误报任务失败。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 2)
        direct = await invoke_plan(
            session_factory,
            [archive_entry(1), archive_entry(2)],
            auth_mode=AuthMode.AUTO_APPROVE,
        )
        run_id = cast(str, direct["run"]["run_id"])
        await corrupt_plan(session_factory, run_id)
        async with session_factory() as session:
            await RunControlService.cancel_run(session, run_id)

        assert await advance(session_factory, run_id) == "CANCELLED"
        assert await statuses(session_factory, run_id) == ["CANCELLED", "CANCELLED"]
        assert await item_row(session_factory, 1) == ("条目1", None, "ACTIVE")


@pytest.mark.anyio
async def test_corrupt_plan_rejects_plan_append(tmp_path: Path) -> None:
    """写路径拒绝在损坏计划上追加：工具结构化拒绝且零写入（不新建 Run、
    不增操作、不改状态）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 3)
        direct = await invoke_plan(
            session_factory,
            [archive_entry(1), archive_entry(2)],
            auth_mode=AuthMode.AUTO_APPROVE,
        )
        run_id = cast(str, direct["run"]["run_id"])
        await corrupt_plan(session_factory, run_id)

        rejected = await invoke_plan(
            session_factory, [archive_entry(3)], auth_mode=AuthMode.AUTO_APPROVE
        )
        assert rejected["ok"] is False
        assert rejected["error"] == "AGENT_RUN_PLAN_INVALID"
        assert await count_rows(session_factory, "SELECT count(*) FROM agent_runs") == 1
        assert await count_rows(session_factory, "SELECT count(*) FROM agent_operations") == 2
        detail = await run_detail(session_factory, run_id)
        assert detail["status"] == "RUNNING"
        assert detail["plan_version"] == 1


@pytest.mark.anyio
async def test_corrupt_plan_confirmation_fails_and_keeps_run_unchanged(tmp_path: Path) -> None:
    """计划卡确认：目标 Run 计划损坏 → 应用器拒绝 → 提案 FAILED（稳定错误码），
    确认事务整体回滚（版本不递增、不唤醒、不新增操作）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 3)
        first = await invoke_plan(session_factory, [archive_entry(1), archive_entry(2)])
        run_id = await confirm(session_factory, await plan_proposal_id(first))
        second = await invoke_plan(session_factory, [archive_entry(3)])
        second_id = await plan_proposal_id(second)
        await corrupt_plan(session_factory, run_id)

        with pytest.raises(CodedHTTPException) as exc:
            await confirm(session_factory, second_id)
        assert exc.value.code == "PROPOSAL_APPLY_FAILED"
        assert exc.value.params == {"errorCode": "AGENT_RUN_PLAN_INVALID"}

        async with session_factory() as session:
            proposal = (
                await session.execute(
                    text("SELECT status, error_code FROM agent_proposals WHERE id = :id"),
                    {"id": second_id},
                )
            ).one()
        assert (proposal[0], proposal[1]) == ("FAILED", "AGENT_RUN_PLAN_INVALID")
        # 运行未受影响：版本不递增（确认事务已回滚）、不新增操作。
        detail = await run_detail(session_factory, run_id)
        assert detail["status"] == "RUNNING"
        assert detail["plan_version"] == 1
        assert await count_rows(session_factory, "SELECT count(*) FROM agent_operations") == 2


# ---------------------------------------------------------------------------
# 参数变更重新确认（spec 决策 13 / 用户故事 23）：待执行步骤就地改写，不静默丢弃


@pytest.mark.anyio
async def test_replan_changed_params_replaces_pending_step(tmp_path: Path) -> None:
    """改参数重新确认：待执行步骤就地改写（同一 operation 身份、计划条目同步），
    执行按新参数落地——旧参数不执行、不重复建操作（工单 05 review）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_course(session_factory, COURSE_OTHER)
        await seed_items(session_factory, 1)
        first = await invoke_plan(session_factory, [update_entry(1)])
        run_id = await confirm(session_factory, await plan_proposal_id(first))

        second = await invoke_plan(session_factory, [update_entry(1, course_id=COURSE_OTHER)])
        assert "plan_proposal" in second
        assert await confirm(session_factory, await plan_proposal_id(second)) == run_id

        # 就地改写：仍是一条操作、载荷与计划条目均为新参数、版本递增。
        assert await count_rows(session_factory, "SELECT count(*) FROM agent_operations") == 1
        assert await operation_payloads(session_factory, run_id) == [
            {"item_id": item_id(1), "title": None, "course_id": COURSE_OTHER}
        ]
        detail = await run_detail(session_factory, run_id)
        assert detail["plan_version"] == 2
        plan_items = cast(list[dict[str, Any]], cast(dict[str, Any], detail["plan"])["items"])
        assert plan_items[0]["params"]["course_id"] == COURSE_OTHER
        # 确认前零业务事实；执行后落在新课程（旧课程从未写入）。
        assert await item_row(session_factory, 1) == ("条目1", None, "ACTIVE")
        assert await advance(session_factory, run_id) == "COMPLETED"
        assert await item_row(session_factory, 1) == ("条目1", COURSE_OTHER, "ACTIVE")


@pytest.mark.anyio
async def test_replan_changed_params_after_success_appends_new_step(tmp_path: Path) -> None:
    """已成功步骤的参数变更＝新事实：追加新步骤执行（不重做已成功项、不改写历史行）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_course(session_factory, COURSE_OTHER)
        await seed_items(session_factory, 2)
        direct = await invoke_plan(
            session_factory,
            [update_entry(1), archive_entry(2)],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        run_id = cast(str, direct["run"]["run_id"])
        assert await advance_step(session_factory, run_id) is True
        assert await statuses(session_factory, run_id) == ["SUCCEEDED", "PLANNED"]

        changed = await invoke_plan(
            session_factory,
            [update_entry(1, course_id=COURSE_OTHER)],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        # 固定计划约束：执行中目标超出已批准集合（对象＋参数）→ 升回确认。
        assert "plan_proposal" in changed
        assert await confirm(session_factory, await plan_proposal_id(changed)) == run_id

        assert await count_rows(session_factory, "SELECT count(*) FROM agent_operations") == 3
        assert await advance(session_factory, run_id) == "COMPLETED"
        assert await item_row(session_factory, 1) == ("条目1", COURSE_OTHER, "ACTIVE")
        assert await statuses(session_factory, run_id) == [
            "SUCCEEDED",
            "SUCCEEDED",
            "SUCCEEDED",
        ]


@pytest.mark.anyio
async def test_replan_changed_params_keeps_dependent_steps_intact(tmp_path: Path) -> None:
    """参数变更就地改写不破坏依赖：依赖该步骤的后续步骤照常推进（operation 身份与
    计划位置不变，依赖不指向被取代的旧操作）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_course(session_factory, COURSE_OTHER)
        await seed_items(session_factory, 2)
        first = await invoke_plan(
            session_factory, [update_entry(1), archive_entry(2, depends_on=[0])]
        )
        run_id = await confirm(session_factory, await plan_proposal_id(first))
        second = await invoke_plan(session_factory, [update_entry(1, course_id=COURSE_OTHER)])
        assert await confirm(session_factory, await plan_proposal_id(second)) == run_id

        assert await advance(session_factory, run_id) == "COMPLETED"
        assert await statuses(session_factory, run_id) == ["SUCCEEDED", "SUCCEEDED"]
        assert await item_row(session_factory, 1) == ("条目1", COURSE_OTHER, "ACTIVE")
        assert await item_row(session_factory, 2) == ("条目2", None, "ARCHIVED")


@pytest.mark.anyio
async def test_auto_approve_changed_params_compares_live_step(tmp_path: Path) -> None:
    """帮我批准档阈值内：参数变更直接生效（就地改写）；比较对象是「当前活步骤」
    ——改回原参数同样生效（不会命中更早的历史操作而静默丢弃）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_course(session_factory, COURSE_OTHER)
        await seed_items(session_factory, 1)
        direct = await invoke_plan(
            session_factory, [update_entry(1)], auth_mode=AuthMode.AUTO_APPROVE
        )
        run_id = cast(str, direct["run"]["run_id"])

        changed = await invoke_plan(
            session_factory,
            [update_entry(1, course_id=COURSE_OTHER)],
            auth_mode=AuthMode.AUTO_APPROVE,
        )
        assert changed["ok"] is True
        assert changed["run"]["added_item_count"] == 1
        assert await operation_payloads(session_factory, run_id) == [
            {"item_id": item_id(1), "title": None, "course_id": COURSE_OTHER}
        ]

        reverted = await invoke_plan(
            session_factory, [update_entry(1)], auth_mode=AuthMode.AUTO_APPROVE
        )
        assert reverted["ok"] is True
        assert await operation_payloads(session_factory, run_id) == [
            {"item_id": item_id(1), "title": None, "course_id": COURSE_ID}
        ]
        assert await count_rows(session_factory, "SELECT count(*) FROM agent_operations") == 1


# ---------------------------------------------------------------------------
# 触发交接（工单 05 review）：显式唤醒落在旧 job 收尾窗口时不得丢触发


@pytest.mark.anyio
async def test_writeback_hands_off_trigger_after_resume_in_flight_window(tmp_path: Path) -> None:
    """丢触发竞态（工单 05 review）：旧 job 仍 RUNNING 时「继续」的投递被守卫跳过，
    旧 job 收尾必须补投触发——否则 Run=RUNNING 且活动触发为 0，悬挂到重启恢复。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 2)
        direct = await invoke_plan(
            session_factory, [archive_entry(1), archive_entry(2)], auth_mode=AuthMode.AUTO_APPROVE
        )
        run_id = cast(str, direct["run"]["run_id"])
        spec = agent_run_spec(session_factory, RecordInvalidationNotifier())
        runner = JobRunner(spec, session_factory, RecordInvalidationNotifier())
        # 旧 worker 领取触发（job → RUNNING），随后推进遇冲突转等待：推进事务已提交、
        # 收尾未到——正是竞态窗口。
        ctx = await runner.claim_one()
        assert ctx is not None
        await project_stale(session_factory, 2)
        assert await advance(session_factory, run_id) == "WAITING_USER"

        # 用户「继续」落在窗口内：Run 抢占为 RUNNING，但守卫看到旧 job RUNNING
        # → 不投递（竞态前置，本修复要兜住的场景）。
        async with session_factory() as session:
            resumed = await RunControlService.resume_run(session, run_id)
        assert resumed["status"] == "RUNNING"
        assert await job_statuses(session_factory) == [("AGENT_RUN", "RUNNING")]

        # 旧 worker 收尾：补投新触发（不再留下无触发的 RUNNING 任务）。
        assert await spec.writeback(ctx, "WAITING_USER") is True
        assert await job_statuses(session_factory) == [
            ("AGENT_RUN", "SUCCEEDED"),
            ("AGENT_RUN", "PENDING"),
        ]

        # 新触发被真实消费并推进到终态（端到端：不再悬挂）。
        assert await runner.process_one() is True
        assert await job_statuses(session_factory) == [
            ("AGENT_RUN", "SUCCEEDED"),
            ("AGENT_RUN", "SUCCEEDED"),
        ]
        detail = await run_detail(session_factory, run_id)
        assert detail["status"] == "PARTIAL_COMPLETED"


@pytest.mark.anyio
async def test_writeback_hands_off_trigger_after_retry_in_flight_window(tmp_path: Path) -> None:
    """同一竞态的另一入口：失败项重试在旧 job 仍 RUNNING 时投递被跳过，
    收尾同样补投触发（Run 由等待态重开）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 2)
        direct = await invoke_plan(
            session_factory, [archive_entry(1), archive_entry(2)], auth_mode=AuthMode.AUTO_APPROVE
        )
        run_id = cast(str, direct["run"]["run_id"])
        spec = agent_run_spec(session_factory, RecordInvalidationNotifier())
        runner = JobRunner(spec, session_factory, RecordInvalidationNotifier())
        ctx = await runner.claim_one()
        assert ctx is not None
        await project_stale(session_factory, 2)
        assert await advance(session_factory, run_id) == "WAITING_USER"

        detail = await run_detail(session_factory, run_id)
        failed_id = next(
            operation["id"]
            for operation in cast(list[dict[str, Any]], detail["operations"])
            if operation["status"] == "FAILED"
        )
        async with session_factory() as session:
            retried = await RunControlService.retry_operation(
                session, run_id=run_id, operation_id=failed_id
            )
        assert retried["status"] == "RUNNING"
        assert await job_statuses(session_factory) == [("AGENT_RUN", "RUNNING")]

        assert await spec.writeback(ctx, "WAITING_USER") is True
        assert await job_statuses(session_factory) == [
            ("AGENT_RUN", "SUCCEEDED"),
            ("AGENT_RUN", "PENDING"),
        ]


@pytest.mark.anyio
async def test_writeback_keeps_waiting_and_settled_runs_without_new_trigger(
    tmp_path: Path,
) -> None:
    """收尾交接只在 Run 仍 RUNNING 时补投：等待态（只接受显式唤醒）与已终态
    不产生多余触发。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 3)
        spec = agent_run_spec(session_factory, RecordInvalidationNotifier())
        runner = JobRunner(spec, session_factory, RecordInvalidationNotifier())
        # 已终态 Run：全部成功（先建，避免后续提交被活跃 Run 约束转计划卡）。
        done_direct = await invoke_plan(
            session_factory, [archive_entry(3)], auth_mode=AuthMode.AUTO_APPROVE
        )
        done_run = cast(str, done_direct["run"]["run_id"])
        done_ctx = await runner.claim_one()
        assert done_ctx is not None
        assert await advance(session_factory, done_run) == "COMPLETED"
        # 等待态 Run：冲突转等待后旧 worker 收尾。
        waiting_direct = await invoke_plan(
            session_factory, [archive_entry(1), archive_entry(2)], auth_mode=AuthMode.AUTO_APPROVE
        )
        waiting_run = cast(str, waiting_direct["run"]["run_id"])
        waiting_ctx = await runner.claim_one()
        assert waiting_ctx is not None
        await project_stale(session_factory, 2)
        assert await advance(session_factory, waiting_run) == "WAITING_USER"

        assert await spec.writeback(done_ctx, "COMPLETED") is True
        assert await spec.writeback(waiting_ctx, "WAITING_USER") is True

        # 各自只有一条触发（无补投），Run 状态不变（等待态不被偷偷唤醒）。
        assert await job_statuses(session_factory) == [
            ("AGENT_RUN", "SUCCEEDED"),
            ("AGENT_RUN", "SUCCEEDED"),
        ]
        detail = await run_detail(session_factory, waiting_run)
        assert detail["status"] == "WAITING_USER"
        detail = await run_detail(session_factory, done_run)
        assert detail["status"] == "COMPLETED"


# 同进程降档约束（工单 05 review）：推进每步授权重检叠加会话覆盖（取更严格者）


@pytest.mark.anyio
async def test_live_downgrade_constrains_running_steps(tmp_path: Path) -> None:
    """同进程降档即时约束后续步骤（工单 05 review）：FULL_ACCESS 直建 Run 后会话
    降为请求批准，推进到首步即 OPERATION_APPROVAL_REQUIRED 转等待、零业务事实；
    切回档位后重试失败项可继续完成（重启后覆盖为空＝仅固化依据，不在此列）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 2)
        direct = await invoke_plan(
            session_factory, [update_entry(1), archive_entry(2)], auth_mode=AuthMode.FULL_ACCESS
        )
        run_id = cast(str, direct["run"]["run_id"])
        try:
            await switch_session_mode(
                session_factory, from_mode=AuthMode.FULL_ACCESS, to_mode=AuthMode.REQUEST_APPROVAL
            )
            assert await advance(session_factory, run_id) == "WAITING_USER"
            detail = await run_detail(session_factory, run_id)
            assert detail["waiting_reason"] == "OPERATION_APPROVAL_REQUIRED"
            steps = await step_rows(session_factory, run_id)
            assert [(action, status, code) for action, status, code, _a, _r in steps] == [
                ("update_library_item", "FAILED", "OPERATION_APPROVAL_REQUIRED"),
                ("archive_library_item", "PLANNED", None),
            ]
            # 零业务事实：降档后一步都没落库。
            assert await item_row(session_factory, 1) == ("条目1", None, "ACTIVE")
            assert await item_row(session_factory, 2) == ("条目2", None, "ACTIVE")

            # 恢复路径：切回档位（会话覆盖升回）后重试失败项 → 继续完成。
            set_session_auth_override(SESSION_ID, AuthMode.FULL_ACCESS)
            failed_id = cast(str, detail["operations"][0]["id"])
            async with session_factory() as session:
                retried = await RunControlService.retry_operation(
                    session, run_id=run_id, operation_id=failed_id
                )
            assert retried["status"] == "RUNNING"
            assert await advance(session_factory, run_id) == "COMPLETED"
            assert await statuses(session_factory, run_id) == ["SUCCEEDED", "SUCCEEDED"]
            assert await item_row(session_factory, 1) == ("条目1", COURSE_ID, "ACTIVE")
            assert await item_row(session_factory, 2) == ("条目2", None, "ARCHIVED")
        finally:
            clear_session_auth_override(SESSION_ID)


@pytest.mark.anyio
async def test_live_downgrade_resume_does_not_bypass(tmp_path: Path) -> None:
    """显式继续 ≠ 重新授权：降档未解除时「继续」唤醒推进，下一步仍被授权重检
    拦下（步骤 FAILED + Run 回到等待，零业务事实）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 2)
        direct = await invoke_plan(
            session_factory, [update_entry(1), archive_entry(2)], auth_mode=AuthMode.FULL_ACCESS
        )
        run_id = cast(str, direct["run"]["run_id"])
        try:
            await switch_session_mode(
                session_factory, from_mode=AuthMode.FULL_ACCESS, to_mode=AuthMode.REQUEST_APPROVAL
            )
            assert await advance(session_factory, run_id) == "WAITING_USER"

            async with session_factory() as session:
                resumed = await RunControlService.resume_run(session, run_id)
            assert resumed["status"] == "RUNNING"
            assert await advance(session_factory, run_id) == "WAITING_USER"
            detail = await run_detail(session_factory, run_id)
            assert detail["waiting_reason"] == "OPERATION_APPROVAL_REQUIRED"
            assert await statuses(session_factory, run_id) == ["FAILED", "FAILED"]
            assert await item_row(session_factory, 1) == ("条目1", None, "ACTIVE")
            assert await item_row(session_factory, 2) == ("条目2", None, "ACTIVE")
        finally:
            clear_session_auth_override(SESSION_ID)


@pytest.mark.anyio
async def test_live_downgrade_keeps_confirmed_plan_running(tmp_path: Path) -> None:
    """显式批准保留（spec Q3）：计划卡确认即批次授权——降档后确认的计划卡照常
    推进完成（proposal_id 非空的 Run 不因降档停摆，防授权重检过度扩张）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_items(session_factory, 11)
        entries = [update_entry(index) for index in range(1, 12)]
        card = await invoke_plan(session_factory, entries, auth_mode=AuthMode.AUTO_APPROVE)
        assert "plan_proposal" in card
        try:
            await switch_session_mode(
                session_factory, from_mode=AuthMode.AUTO_APPROVE, to_mode=AuthMode.REQUEST_APPROVAL
            )
            run_id = await confirm(session_factory, await plan_proposal_id(card))
            assert await advance(session_factory, run_id) == "COMPLETED"
            assert await statuses(session_factory, run_id) == ["SUCCEEDED"] * 11
        finally:
            clear_session_auth_override(SESSION_ID)
