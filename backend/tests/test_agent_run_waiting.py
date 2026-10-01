"""通用 Agent 第三阶段工单 06：Run 等待与结果绑定（spec M2 执行闭环）。

- 结果绑定注入：后步参数按字段路径引用前步输出（建课 course_id → 导入归类），
  引用即依赖（自动并入 depends_on）、执行时解析回填事实参数；越界引用与
  缺参在提交时结构化拒绝；
- WAITING_JOB 激活：ingest 步骤提交 WEB_FETCH job 后 Run 转等待（waiting_job_id
  核对对象）；job 完成经领取闸门核对唤醒续跑、job 失败等待步骤翻 FAILED 交还
  推进既有失败口径（依赖步骤 SKIPPED、终态 PARTIAL_COMPLETED）；
- 启动对账：等待中的 Run（触发 job 随重启中断翻 FAILED）经 recover 重投触发，
  与运行期核对共用分流；已成功步骤不重做；
- 等待中取消：未执行步骤停止、已提交 job 保留回执；断开 SSE 不是业务取消
  （推进独立于连接，等待期间状态稳定）。
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
from app.modules.agent.runs.schemas import AuthMode
from app.modules.agent.runs.service import RunControlService, RunHistoryService
from app.modules.agent.runs.worker import (
    advance_run,
    agent_run_spec,
    resolve_waiting,
    validate_claim,
)
from app.modules.agent.runtime import (
    AgentRuntimeContext,
    ToolCallBudget,
    bind_agent_runtime_context,
    reset_agent_runtime_context,
)
from app.modules.agent.tools.plan_batch_operations import plan_batch_operations
from app.modules.jobs.runner import CancelClaim, Ready, WaitingClaim
from app.modules.library.proposals import ProposalService
from app.shared.events import RecordInvalidationNotifier

NOW = "2026-09-30T08:00:00.000000Z"
LATER = "2026-09-30T09:00:00.000000Z"
SESSION_ID = "sess-waiting"
URL = "https://example.com/transformers-explained"

COURSE_REF = {"step": 0, "field": "course_id"}


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


async def seed_item(session_factory: async_sessionmaker[AsyncSession], index: int) -> None:
    await run_sql(
        "INSERT INTO library_items (id, course_id, source_type, title, content_hash,"
        " metadata_json, status, created_at, updated_at)"
        " VALUES (:id, NULL, 'TEXT', :title, :hash, '{}', 'ACTIVE', :now, :now)",
        {
            "id": item_id(index),
            "title": f"条目{index}",
            "hash": f"hash-{index}",
            "now": NOW,
        },
        session_factory,
    )


def create_course_entry(**overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "action": "create_course",
        "name": "Transformer 精读",
        "learning_context": "CAREER",
        "depth": "INTERMEDIATE",
    }
    entry.update(overrides)
    return entry


def ingest_entry(**overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {"action": "ingest_library_item", "url": URL}
    entry.update(overrides)
    return entry


async def invoke_plan(
    session_factory: async_sessionmaker[AsyncSession],
    entries: list[dict[str, Any]],
    *,
    auth_mode: AuthMode = AuthMode.REQUEST_APPROVAL,
) -> dict[str, Any]:
    token = bind_agent_runtime_context(
        AgentRuntimeContext(
            session_factory=session_factory,
            session_id=SESSION_ID,
            auth_mode=auth_mode,
            instruction_excerpt="建课并导入这篇资料",
            message_id="msg-1",
            budget=ToolCallBudget(),
        )
    )
    try:
        raw = await plan_batch_operations.ainvoke({"items": entries})
        return dict(json.loads(raw))
    finally:
        reset_agent_runtime_context(token)


async def confirm_plan(session_factory: async_sessionmaker[AsyncSession], proposal_id: str) -> str:
    async with session_factory() as session:
        result = await ProposalService.confirm(session, proposal_id)
    applied: dict[str, Any] = result.result or {}
    return cast(str, applied["run_id"])


async def advance(session_factory: async_sessionmaker[AsyncSession], run_id: str) -> str:
    return await advance_run(session_factory, run_id)


async def run_row(
    session_factory: async_sessionmaker[AsyncSession], run_id: str
) -> tuple[str, str | None, str | None]:
    """(status, waiting_reason, waiting_job_id) 直读 Run 行（对账口径）。"""
    async with session_factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT status, waiting_reason, waiting_job_id FROM agent_runs WHERE id = :id"
                ),
                {"id": run_id},
            )
        ).one()
    return (cast(str, row[0]), row[1], row[2])


async def step_rows(
    session_factory: async_sessionmaker[AsyncSession], run_id: str
) -> list[tuple[str, str, str | None, int]]:
    """(action, status, error_code, attempts) 按计划顺序（同事务创建的行
    created_at 打平，顺序权威来自 run 详情的计划投影，05 票测试同口径）。"""
    async with session_factory() as session:
        detail = await RunHistoryService.get_run_detail(session, run_id)
    order = [item["id"] for item in cast(list[dict[str, Any]], detail["operations"])]
    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT id, action, status, error_code, attempts FROM agent_operations"
                    " WHERE run_id = :run_id"
                ),
                {"run_id": run_id},
            )
        ).all()
    by_id = {cast(str, row[0]): row for row in rows}
    return [
        (cast(str, row[1]), cast(str, row[2]), row[3], cast(int, row[4]))
        for row in (by_id[operation_id] for operation_id in order)
    ]


async def operation_payloads(
    session_factory: async_sessionmaker[AsyncSession], run_id: str
) -> list[dict[str, Any]]:
    """逐项操作载荷，按计划顺序（同 step_rows 口径）。"""
    async with session_factory() as session:
        detail = await RunHistoryService.get_run_detail(session, run_id)
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


async def waiting_trigger_job(
    session_factory: async_sessionmaker[AsyncSession], run_id: str
) -> str:
    """该 Run 当前 PENDING 的 AGENT_RUN 触发 job id（领取核对用）。"""
    async with session_factory() as session:
        found = await session.execute(
            text(
                "SELECT id FROM processing_jobs WHERE job_type = 'AGENT_RUN'"
                " AND status = 'PENDING' AND json_extract(input_json, '$.run_id') = :run_id"
            ),
            {"run_id": run_id},
        )
        row = found.scalar_one_or_none()
    assert row is not None, "等待中的 Run 应保有活动触发 job"
    return cast(str, row)


async def finish_job(session_factory: async_sessionmaker[AsyncSession], status: str) -> None:
    """模拟后台抓取 job 落定（成功 / 失败——WEB_FETCH 是唯一领域 job）。"""
    await run_sql(
        "UPDATE processing_jobs SET status = :status, finished_at = :later"
        " WHERE job_type = 'WEB_FETCH'",
        {"status": status, "later": LATER},
        session_factory,
    )


async def finish_jobs(
    session_factory: async_sessionmaker[AsyncSession], outcomes: list[str]
) -> None:
    """按序落定**尚未终态**的抓取 job（多份导入一成一败的构造用：每轮只碰
    当前在等的那个，已落定的历史 job 不重写）。"""
    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT id FROM processing_jobs WHERE job_type = 'WEB_FETCH'"
                    " AND status = 'PENDING' ORDER BY created_at, id"
                )
            )
        ).all()
    for row, status in zip(rows, outcomes, strict=True):
        await run_sql(
            "UPDATE processing_jobs SET status = :status, finished_at = :later WHERE id = :id",
            {"status": status, "later": LATER, "id": cast(str, row[0])},
            session_factory,
        )


async def web_fetch_statuses(session_factory: async_sessionmaker[AsyncSession]) -> list[str]:
    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT status FROM processing_jobs WHERE job_type = 'WEB_FETCH'"
                    " ORDER BY created_at, id"
                )
            )
        ).all()
    return [cast(str, row[0]) for row in rows]


async def new_course_row(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[str, str | None]:
    """计划新建的课程 (id, 名称)——库内唯一的计划建课产物。"""
    async with session_factory() as session:
        row = (
            await session.execute(
                text("SELECT id, name FROM courses WHERE created_at >= :now ORDER BY created_at"),
                {"now": NOW},
            )
        ).one()
    return (cast(str, row[0]), cast(str, row[1]))


async def ingested_item_row(
    session_factory: async_sessionmaker[AsyncSession],
    url: str = URL,
) -> tuple[str | None, str] | None:
    """导入产出的资料条目 (course_id, source_type)（origin_uri 定位；无则 None）。"""
    async with session_factory() as session:
        row = (
            await session.execute(
                text("SELECT course_id, source_type FROM library_items WHERE origin_uri = :url"),
                {"url": url},
            )
        ).one_or_none()
    return None if row is None else (row[0], cast(str, row[1]))


def spec_of(session_factory: async_sessionmaker[AsyncSession]):
    return agent_run_spec(session_factory, RecordInvalidationNotifier())


async def claim_waiting(session_factory: async_sessionmaker[AsyncSession], run_id: str) -> Any:
    """对等待中的 Run 跑一次领取闸门（模拟 JobRunner 轮询核对）。"""
    async with session_factory() as session, session.begin():
        job_id = await waiting_trigger_job(session_factory, run_id)
        job = cast(
            Any,
            (
                await session.execute(
                    text("SELECT * FROM processing_jobs WHERE id = :id"), {"id": job_id}
                )
            ).one(),
        )
        return await validate_claim(session, job, "", None)


# ---------------------------------------------------------------------------
# 结果绑定注入


@pytest.mark.anyio
async def test_binding_injects_prior_step_output(tmp_path: Path) -> None:
    """最小验证场景全链（前半）：建课 → 导入（course_id 引用注入）→ Run 转等待。

    引用即依赖（depends_on 自动并入）、执行时解析回填事实参数（载荷不再是
    引用对象）、资料真实归到新课程、WAITING_JOB 携带核对对象。"""
    async with bare_db(tmp_path) as session_factory:
        direct = await invoke_plan(
            session_factory,
            [create_course_entry(), ingest_entry(course_id=COURSE_REF)],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        run_id = cast(str, direct["run"]["run_id"])

        assert await advance(session_factory, run_id) == "WAITING_JOB"
        _status, reason, waiting_job_id = await run_row(session_factory, run_id)
        assert reason == "AGENT_RUN_WAITING_JOB_PENDING"
        assert waiting_job_id is not None
        assert await web_fetch_statuses(session_factory) == ["PENDING"]

        # 建课已执行；导入步骤提交 job 即成功（result 留回执）。
        steps = await step_rows(session_factory, run_id)
        assert [(action, status) for action, status, _code, _attempts in steps] == [
            ("create_course", "SUCCEEDED"),
            ("ingest_library_item", "SUCCEEDED"),
        ]
        # 引用注入：导入载荷的 course_id 已回填为新建课程 id（非引用对象）。
        course_id, course_name = await new_course_row(session_factory)
        assert course_name == "Transformer 精读"
        payloads = await operation_payloads(session_factory, run_id)
        assert payloads[1]["course_id"] == course_id
        ingested = await ingested_item_row(session_factory)
        assert ingested is not None
        assert ingested[0] == course_id
        assert ingested[1] == "WEB"


@pytest.mark.anyio
async def test_confirmed_plan_card_carries_waiting_steps(tmp_path: Path) -> None:
    """请求批准档：含创建步骤与引用的计划同样走计划卡（一次批准绑定整计划）；
    确认路径跳过引用项的快照读取，确认后建 Run 推进转等待。"""
    async with bare_db(tmp_path) as session_factory:
        planned = await invoke_plan(
            session_factory,
            [create_course_entry(), ingest_entry(course_id=COURSE_REF)],
        )
        assert "plan_proposal" in planned
        run_id = await confirm_plan(
            session_factory, cast(str, planned["plan_proposal"]["proposal_id"])
        )
        assert await advance(session_factory, run_id) == "WAITING_JOB"
        assert (await run_row(session_factory, run_id))[2] is not None


@pytest.mark.anyio
async def test_reference_must_point_to_earlier_step(tmp_path: Path) -> None:
    """越界引用（指向自身或更晚步骤）在提交时结构化拒绝（引用即依赖同规则）。"""
    async with bare_db(tmp_path) as session_factory:
        result = await invoke_plan(
            session_factory,
            [ingest_entry(course_id={"step": 1, "field": "course_id"}), create_course_entry()],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        assert result["ok"] is False
        assert result["error"] == "PROPOSAL_PAYLOAD_INVALID"


@pytest.mark.anyio
async def test_unresolvable_reference_skips_step(tmp_path: Path) -> None:
    """防御路径：来源步骤成功但其结果无引用字段（模型错配引用目标）→ 本步骤
    SKIPPED（依赖失败码），不执行领域写入。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_item(session_factory, 1)
        direct = await invoke_plan(
            session_factory,
            [
                {"action": "archive_library_item", "item_id": item_id(1)},
                ingest_entry(course_id={"step": 0, "field": "course_id"}),
            ],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        run_id = cast(str, direct["run"]["run_id"])

        assert await advance(session_factory, run_id) == "PARTIAL_COMPLETED"
        steps = await step_rows(session_factory, run_id)
        assert [(status, code) for _a, status, code, _attempts in steps] == [
            ("SUCCEEDED", None),
            ("SKIPPED", "OPERATION_DEPENDENCY_FAILED"),
        ]
        # 未执行领域写入：资料未导入。
        assert await ingested_item_row(session_factory) is None


@pytest.mark.anyio
async def test_create_course_step_requires_learning_context(tmp_path: Path) -> None:
    """创建步骤缺必填参数（learning_context）在提交时结构化拒绝。"""
    async with bare_db(tmp_path) as session_factory:
        result = await invoke_plan(
            session_factory,
            [
                {
                    "action": "create_course",
                    "name": "缺场景的课程",
                    "learning_context": None,
                }
            ],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        assert result["ok"] is False
        assert result["error"] == "PROPOSAL_PAYLOAD_INVALID"


# ---------------------------------------------------------------------------
# WAITING_JOB 激活与唤醒


@pytest.mark.anyio
async def test_waiting_wakes_and_completes_when_job_succeeds(tmp_path: Path) -> None:
    """最小验证场景全链（后半）：job 完成 → 领取核对唤醒 → 推进收尾 COMPLETED；
    建课与导入步骤不重做（attempts 恒 1）。"""
    async with bare_db(tmp_path) as session_factory:
        direct = await invoke_plan(
            session_factory,
            [create_course_entry(), ingest_entry(course_id=COURSE_REF)],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        run_id = cast(str, direct["run"]["run_id"])
        assert await advance(session_factory, run_id) == "WAITING_JOB"

        await finish_job(session_factory, "SUCCEEDED")
        decision = await claim_waiting(session_factory, run_id)
        assert isinstance(decision, Ready)
        assert (await run_row(session_factory, run_id))[0] == "RUNNING"

        assert await advance(session_factory, run_id) == "COMPLETED"
        steps = await step_rows(session_factory, run_id)
        assert [status for _a, status, _c, _attempts in steps] == ["SUCCEEDED", "SUCCEEDED"]
        assert [attempts for _a, _s, _c, attempts in steps] == [1, 1]


@pytest.mark.anyio
async def test_pending_job_keeps_run_waiting(tmp_path: Path) -> None:
    """job 未终态：领取闸门交还轮询（WaitingClaim 不消费触发）、Run 保持等待。"""
    async with bare_db(tmp_path) as session_factory:
        direct = await invoke_plan(
            session_factory,
            [create_course_entry(), ingest_entry(course_id=COURSE_REF)],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        run_id = cast(str, direct["run"]["run_id"])
        assert await advance(session_factory, run_id) == "WAITING_JOB"

        decision = await claim_waiting(session_factory, run_id)
        assert isinstance(decision, WaitingClaim)
        assert decision.reason == "waiting_job"
        assert (await run_row(session_factory, run_id))[0] == "WAITING_JOB"
        # 触发 job 未被消费（PENDING 保留，轮询下一周期再核对）。
        await waiting_trigger_job(session_factory, run_id)


@pytest.mark.anyio
async def test_job_failure_fails_waiting_step_and_settles_partial(tmp_path: Path) -> None:
    """job 失败分流：等待步骤翻 FAILED（稳定码、result 回执保留）、Run 经推进
    落 PARTIAL_COMPLETED——后续依赖（若有）由既有 SKIPPED 口径承接。"""
    async with bare_db(tmp_path) as session_factory:
        direct = await invoke_plan(
            session_factory,
            [create_course_entry(), ingest_entry(course_id=COURSE_REF)],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        run_id = cast(str, direct["run"]["run_id"])
        assert await advance(session_factory, run_id) == "WAITING_JOB"

        await finish_job(session_factory, "FAILED")
        decision = await claim_waiting(session_factory, run_id)
        assert isinstance(decision, Ready)

        assert await advance(session_factory, run_id) == "PARTIAL_COMPLETED"
        steps = await step_rows(session_factory, run_id)
        assert [(status, code) for _a, status, code, _attempts in steps] == [
            ("SUCCEEDED", None),
            ("FAILED", "AGENT_RUN_WAITING_JOB_FAILED"),
        ]
        # 失败的等待步骤可单独重试（既有失败项重试口径；导入动作的重试幂等
        # 边界见注册项备案，随 07 收口）。
        step_id = await _step_id(session_factory, run_id, "ingest_library_item")
        async with session_factory() as session:
            await RunControlService.retry_operation(session, run_id=run_id, operation_id=step_id)
        assert (await run_row(session_factory, run_id))[0] == "RUNNING"


@pytest.mark.anyio
async def test_second_waiting_step_after_wake_settles_partial(tmp_path: Path) -> None:
    """部分失败链（工单测试要求）：两份导入一成一败——首份等待唤醒后继续执行
    第二份导入、再次转等待（唤醒后仍有 waits_for_job 步骤），第二份失败 →
    等待步骤翻 FAILED → PARTIAL_COMPLETED；建课与首份导入不重做。"""
    async with bare_db(tmp_path) as session_factory:
        direct = await invoke_plan(
            session_factory,
            [
                create_course_entry(),
                ingest_entry(course_id=COURSE_REF),
                ingest_entry(url="https://example.com/another", course_id=COURSE_REF),
            ],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        run_id = cast(str, direct["run"]["run_id"])

        # 首份导入提交 job → 等待；job 成功 → 唤醒后执行第二份导入 → 再等待。
        assert await advance(session_factory, run_id) == "WAITING_JOB"
        await finish_jobs(session_factory, ["SUCCEEDED"])
        assert isinstance(await claim_waiting(session_factory, run_id), Ready)
        assert await advance(session_factory, run_id) == "WAITING_JOB"

        # 第二份失败：唤醒后等待步骤翻 FAILED，终态部分完成。
        await finish_jobs(session_factory, ["FAILED"])
        assert isinstance(await claim_waiting(session_factory, run_id), Ready)
        assert await advance(session_factory, run_id) == "PARTIAL_COMPLETED"
        steps = await step_rows(session_factory, run_id)
        assert [(action, status, code) for action, status, code, _a in steps] == [
            ("create_course", "SUCCEEDED", None),
            ("ingest_library_item", "SUCCEEDED", None),
            ("ingest_library_item", "FAILED", "AGENT_RUN_WAITING_JOB_FAILED"),
        ]
        assert [attempts for _a, _s, _c, attempts in steps] == [1, 1, 1]


@pytest.mark.anyio
async def test_cancel_during_waiting_race_settles_cancelled(tmp_path: Path) -> None:
    """唤醒与取消的竞态兜底：核对时已读到取消旗标 → 按取消收尾（不把已取消
    的 Run 复活为 RUNNING），触发 job 静默作废。"""
    async with bare_db(tmp_path) as session_factory:
        direct = await invoke_plan(
            session_factory,
            [
                create_course_entry(),
                ingest_entry(course_id=COURSE_REF),
                ingest_entry(url="https://example.com/another", depends_on=[1]),
            ],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        run_id = cast(str, direct["run"]["run_id"])
        assert await advance(session_factory, run_id) == "WAITING_JOB"

        # 抓取已完成 + 取消旗标已置（竞态窗口的读取序）：核对就地收尾。
        await finish_jobs(session_factory, ["SUCCEEDED"])
        await run_sql(
            "UPDATE agent_runs SET cancel_requested = 1 WHERE id = :id",
            {"id": run_id},
            session_factory,
        )
        decision = await claim_waiting(session_factory, run_id)
        assert isinstance(decision, CancelClaim)
        assert (await run_row(session_factory, run_id))[0] == "CANCELLED"
        statuses = [status for _a, status, _c, _a2 in await step_rows(session_factory, run_id)]
        assert statuses == ["SUCCEEDED", "SUCCEEDED", "CANCELLED"]


async def _step_id(
    session_factory: async_sessionmaker[AsyncSession], run_id: str, action: str
) -> str:
    async with session_factory() as session:
        found = await session.execute(
            text("SELECT id FROM agent_operations WHERE run_id = :run_id AND action = :action"),
            {"run_id": run_id, "action": action},
        )
        return cast(str, found.scalar_one())


# ---------------------------------------------------------------------------
# 启动对账与等待中取消


@pytest.mark.anyio
async def test_restart_reconcile_waiting_run_without_redo(tmp_path: Path) -> None:
    """重启对账：等待中的 Run（触发 job 随进程中断翻 FAILED）经 recover 重投
    触发，核对已成功的 job 续跑收尾；建课与导入步骤不重做。"""
    async with bare_db(tmp_path) as session_factory:
        direct = await invoke_plan(
            session_factory,
            [create_course_entry(), ingest_entry(course_id=COURSE_REF)],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        run_id = cast(str, direct["run"]["run_id"])
        assert await advance(session_factory, run_id) == "WAITING_JOB"

        # 重启：等待期间进程消失——活动触发 job 被恢复流程翻 FAILED，抓取 job
        # 已在此前完成（对账分流三态之一）。
        await finish_job(session_factory, "SUCCEEDED")
        await run_sql(
            "UPDATE processing_jobs SET status = 'FAILED', finished_at = :later"
            " WHERE job_type = 'AGENT_RUN'",
            {"later": LATER},
            session_factory,
        )

        await spec_of(session_factory).recover_interrupted()
        # 对账幂等：重复恢复不重复投递（活动触发守卫）。
        await spec_of(session_factory).recover_interrupted()

        # 重投的触发 job 被领取闸门核对：job 已成功 → 唤醒续跑收尾（不重做）。
        decision = await claim_waiting(session_factory, run_id)
        assert isinstance(decision, Ready)
        assert await advance(session_factory, run_id) == "COMPLETED"
        steps = await step_rows(session_factory, run_id)
        assert [attempts for _a, _s, _c, attempts in steps] == [1, 1]


@pytest.mark.anyio
async def test_restart_reconcile_failed_job_settles_partial(tmp_path: Path) -> None:
    """重启对账「败」分支：等待期间抓取 job 已失败 + 触发随进程中断翻 FAILED →
    recover 重投触发 → 领取核对按失败分流 → 等待步骤 FAILED → PARTIAL_COMPLETED。"""
    async with bare_db(tmp_path) as session_factory:
        direct = await invoke_plan(
            session_factory,
            [create_course_entry(), ingest_entry(course_id=COURSE_REF)],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        run_id = cast(str, direct["run"]["run_id"])
        assert await advance(session_factory, run_id) == "WAITING_JOB"

        await finish_job(session_factory, "FAILED")
        await run_sql(
            "UPDATE processing_jobs SET status = 'FAILED', finished_at = :later"
            " WHERE job_type = 'AGENT_RUN'",
            {"later": LATER},
            session_factory,
        )

        await spec_of(session_factory).recover_interrupted()
        assert isinstance(await claim_waiting(session_factory, run_id), Ready)
        assert await advance(session_factory, run_id) == "PARTIAL_COMPLETED"
        steps = await step_rows(session_factory, run_id)
        assert [(status, code) for _a, status, code, _attempts in steps] == [
            ("SUCCEEDED", None),
            ("FAILED", "AGENT_RUN_WAITING_JOB_FAILED"),
        ]


@pytest.mark.anyio
async def test_cancel_waiting_run_settles_and_keeps_submitted_job(tmp_path: Path) -> None:
    """等待中取消：未执行步骤停止、已提交的抓取 job 保留回执（不杀）、Run 落
    CANCELLED；等待期间无显式动作状态恒稳定（断开 SSE 不是业务取消）。"""
    async with bare_db(tmp_path) as session_factory:
        direct = await invoke_plan(
            session_factory,
            [
                create_course_entry(),
                ingest_entry(course_id=COURSE_REF),
                ingest_entry(url="https://example.com/another", depends_on=[1]),
            ],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        run_id = cast(str, direct["run"]["run_id"])
        assert await advance(session_factory, run_id) == "WAITING_JOB"
        assert (await run_row(session_factory, run_id))[0] == "WAITING_JOB"

        async with session_factory() as session:
            await RunControlService.cancel_run(session, run_id)
        assert (await run_row(session_factory, run_id))[0] == "CANCELLED"
        # 已提交的抓取 job 保留（回执语义），未执行步骤停止。
        assert await web_fetch_statuses(session_factory) == ["PENDING"]
        step_statuses = [status for _a, status, _c, _a2 in await step_rows(session_factory, run_id)]
        assert step_statuses == ["SUCCEEDED", "SUCCEEDED", "CANCELLED"]


@pytest.mark.anyio
async def test_missing_waiting_job_fails_step_conservatively(tmp_path: Path) -> None:
    """异常数据防御：等待 job 缺失（核对对象丢失）按失败分流，不悬挂。"""
    async with bare_db(tmp_path) as session_factory:
        direct = await invoke_plan(
            session_factory,
            [create_course_entry(), ingest_entry(course_id=COURSE_REF)],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        run_id = cast(str, direct["run"]["run_id"])
        assert await advance(session_factory, run_id) == "WAITING_JOB"

        await run_sql(
            "DELETE FROM processing_jobs WHERE job_type = 'WEB_FETCH'", {}, session_factory
        )
        decision = await claim_waiting(session_factory, run_id)
        assert isinstance(decision, Ready)
        assert await advance(session_factory, run_id) == "PARTIAL_COMPLETED"
        steps = await step_rows(session_factory, run_id)
        assert steps[1][1] == "FAILED"
        assert steps[1][2] == "AGENT_RUN_WAITING_JOB_FAILED"


@pytest.mark.anyio
async def test_resolve_waiting_signature_wakes_on_success(tmp_path: Path) -> None:
    """resolve_waiting 直接口径（对账与领取闸门共用的分流函数）：SUCCEEDED
    唤醒、清等待字段。"""
    from app.modules.agent.runs.models import AgentRun

    async with bare_db(tmp_path) as session_factory:
        direct = await invoke_plan(
            session_factory,
            [create_course_entry(), ingest_entry(course_id=COURSE_REF)],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        run_id = cast(str, direct["run"]["run_id"])
        assert await advance(session_factory, run_id) == "WAITING_JOB"
        await finish_job(session_factory, "SUCCEEDED")

        async with session_factory() as session, session.begin():
            run = await session.get(AgentRun, run_id)
            assert run is not None
            assert await resolve_waiting(session, run, now=datetime(2026, 9, 30, 9, 0, tzinfo=UTC))
            assert run.status == "RUNNING"
            assert run.waiting_job_id is None
            assert run.waiting_reason is None
