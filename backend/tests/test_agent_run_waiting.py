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
from app.modules.agent.runs.undo import UndoService
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
from app.modules.capture.web_clip import ClipContent
from app.modules.capture.web_fetch_worker import web_fetch_spec
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.runner import CancelClaim, JobRunner, Ready, WaitingClaim
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
    session_id: str = SESSION_ID,
) -> dict[str, Any]:
    token = bind_agent_runtime_context(
        AgentRuntimeContext(
            session_factory=session_factory,
            session_id=session_id,
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
    """对等待中的 Run 跑一次领取闸门（模拟 JobRunner 轮询核对）。

    job 以 ORM 实体加载（与生产 find_candidate 同形态——等待分支会在实体上
    写调度退避，SQL Row 不可赋值）。"""
    async with session_factory() as session, session.begin():
        job_id = await waiting_trigger_job(session_factory, run_id)
        job = await session.get(ProcessingJob, job_id)
        assert job is not None
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
async def test_waiting_claim_skips_waiting_reason_write(tmp_path: Path) -> None:
    """等待领取走完整 JobRunner.claim_one（真实迁移库、0004 CHECK 生效）：
    processing_jobs.waiting_reason 是 audio 等待槽（CHECK 值域仅 audio 三态），
    Agent 等待不写该列——修复前此处 IntegrityError，等待期反复错误恢复。"""
    async with bare_db(tmp_path) as session_factory:
        direct = await invoke_plan(
            session_factory,
            [create_course_entry(), ingest_entry(course_id=COURSE_REF)],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        run_id = cast(str, direct["run"]["run_id"])
        assert await advance(session_factory, run_id) == "WAITING_JOB"

        runner = JobRunner(spec_of(session_factory), session_factory, RecordInvalidationNotifier())
        assert await runner.claim_one() is None  # 未消费触发（无可执行 ctx）

        # 触发 job 保留 PENDING、waiting_reason 未被触碰、Run 保持等待。
        job_id = await waiting_trigger_job(session_factory, run_id)
        async with session_factory() as session:
            row = (
                await session.execute(
                    text("SELECT status, waiting_reason FROM processing_jobs WHERE id = :id"),
                    {"id": job_id},
                )
            ).one()
        assert (row[0], row[1]) == ("PENDING", None)
        assert (await run_row(session_factory, run_id))[0] == "WAITING_JOB"


@pytest.mark.anyio
async def test_appended_batch_refs_bind_to_own_steps(tmp_path: Path) -> None:
    """追加批次的输出引用绑本批步骤（P1 回归）：引用 step 是本批局部索引，写入
    前须换算为 Run 全局编号——修复前局部 step=0 绑到第一批建课 A（URL2 归入
    A、课程 B 留空），违反步骤结果绑定与固定授权对象的要求。"""
    url2 = "https://example.com/diffusion-explained"
    async with bare_db(tmp_path) as session_factory:
        direct = await invoke_plan(
            session_factory,
            [create_course_entry(), ingest_entry(course_id=COURSE_REF)],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        run_id = cast(str, direct["run"]["run_id"])
        assert await advance(session_factory, run_id) == "WAITING_JOB"

        # 等待期间追加第二批（等待态只接受显式确认，转计划卡）：建课 B＋导入
        # URL2 引用本批第 0 步；确认后延展同一 Run。
        planned = await invoke_plan(
            session_factory,
            [
                create_course_entry(name="Diffusion 入门"),
                ingest_entry(url=url2, course_id=COURSE_REF),
            ],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        proposal_id = cast(str, planned["plan_proposal"]["proposal_id"])
        assert await confirm_plan(session_factory, proposal_id) == run_id

        # URL1 抓取完成 → 唤醒推进：第二批建课 B、URL2 提交 job 再转等待 → 完成。
        await finish_job(session_factory, "SUCCEEDED")
        assert isinstance(await claim_waiting(session_factory, run_id), Ready)
        assert await advance(session_factory, run_id) == "WAITING_JOB"
        await finish_job(session_factory, "SUCCEEDED")
        assert isinstance(await claim_waiting(session_factory, run_id), Ready)
        assert await advance(session_factory, run_id) == "COMPLETED"

        # URL2 归课程 B（引用本批建课步骤的全局编号），课程 A 只收 URL1。
        async with session_factory() as session:
            rows = (
                await session.execute(
                    text("SELECT name, id FROM courses WHERE created_at >= :now"),
                    {"now": NOW},
                )
            ).all()
        courses = {cast(str, row[0]): cast(str, row[1]) for row in rows}
        item_a = await ingested_item_row(session_factory)
        item_b = await ingested_item_row(session_factory, url=url2)
        assert item_a is not None and item_b is not None
        assert item_a[0] == courses["Transformer 精读"]
        assert item_b[0] == courses["Diffusion 入门"]
        # 计划投影里第二批引用已固化事实参数（执行回填），不再残留引用对象。
        payloads = await operation_payloads(session_factory, run_id)
        assert payloads[3]["course_id"] == courses["Diffusion 入门"]


@pytest.mark.anyio
async def test_ref_only_categorize_plan_is_accepted(tmp_path: Path) -> None:
    """纯引用归类计划不被拒（P2 回归）：「建课 → 既有资料归到新课」只传
    item_id＋course_id 引用是结果绑定的核心场景——剔除引用字段后不能因
    「至少一个修改字段」拒绝（引用即修改意图）；快照照常完整固化。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_item(session_factory, 0)
        direct = await invoke_plan(
            session_factory,
            [
                create_course_entry(),
                {"action": "update_library_item", "item_id": item_id(0), "course_id": COURSE_REF},
            ],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        run_id = cast(str, direct["run"]["run_id"])
        assert await advance(session_factory, run_id) == "COMPLETED"

        course_id, _name = await new_course_row(session_factory)
        async with session_factory() as session:
            item = (
                await session.execute(
                    text("SELECT course_id FROM library_items WHERE id = :id"),
                    {"id": item_id(0)},
                )
            ).one()
            snap = (
                await session.execute(
                    text(
                        "SELECT snapshot_json FROM agent_operations"
                        " WHERE run_id = :run_id AND action = 'update_library_item'"
                    ),
                    {"run_id": run_id},
                )
            ).one()
        assert item[0] == course_id
        snapshot = cast(dict[str, Any], json.loads(cast(str, snap[0])))
        assert snapshot["title"] == "条目0"
        assert snapshot["course_id"] is None


@pytest.mark.anyio
async def test_waiting_trigger_yields_scheduling_to_other_runs(tmp_path: Path) -> None:
    """等待核对让出调度窗口（P2 回归）：等待中的触发 job 恒居候选队头且
    WaitingClaim 原样保留，短退避前其他独立 Run 的触发领取不到——Run A 等待
    抓取期间，Run B（另一会话新建课程）始终 PLANNED 不被推进。"""
    async with bare_db(tmp_path) as session_factory:
        waiting = await invoke_plan(
            session_factory,
            [create_course_entry(), ingest_entry(course_id=COURSE_REF)],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        run_a = cast(str, waiting["run"]["run_id"])
        assert await advance(session_factory, run_a) == "WAITING_JOB"

        # 独立会话提交 Run B（触发 job 晚于 A 的等待触发）。
        direct_b = await invoke_plan(
            session_factory,
            [create_course_entry(name="独立课程")],
            auth_mode=AuthMode.FULL_ACCESS,
            session_id="sess-independent",
        )
        run_b = cast(str, direct_b["run"]["run_id"])

        runner = JobRunner(spec_of(session_factory), session_factory, RecordInvalidationNotifier())
        # 第一拍：领取 A 的等待触发——不消费、置短退避。
        assert await runner.claim_one() is None
        trigger_a = await waiting_trigger_job(session_factory, run_a)
        async with session_factory() as session:
            backoff = (
                await session.execute(
                    text("SELECT next_run_at FROM processing_jobs WHERE id = :id"),
                    {"id": trigger_a},
                )
            ).one()
        assert backoff[0] is not None

        # 第二拍（A 退避窗口内）：调度落到 B 的触发，B 完整推进收尾。
        assert await runner.process_one() is True
        steps = await step_rows(session_factory, run_b)
        assert [status for _a, status, _c, _attempts in steps] == ["SUCCEEDED"]
        assert (await run_row(session_factory, run_b))[0] == "COMPLETED"
        # A 不受影响：仍在等待。
        assert (await run_row(session_factory, run_a))[0] == "WAITING_JOB"


@pytest.mark.anyio
async def test_ref_update_step_snapshot_stale_blocks_overwrite(tmp_path: Path) -> None:
    """含引用的修改类步骤受对象版本绑定（P1 回归）：提交期固化目标快照（剔除
    引用字段抓取），执行时与普通步骤同口径重验——批准后用户改条目标题，Agent
    不得覆盖该修改（OPERATION_SNAPSHOT_STALE，ADR-0026）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_item(session_factory, 0)
        direct = await invoke_plan(
            session_factory,
            [
                create_course_entry(),
                ingest_entry(course_id=COURSE_REF),
                {
                    "action": "update_library_item",
                    "item_id": item_id(0),
                    "title": "Agent 改名",
                    "course_id": COURSE_REF,
                },
            ],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        run_id = cast(str, direct["run"]["run_id"])
        assert await advance(session_factory, run_id) == "WAITING_JOB"

        # 等待期间用户手动改条目标题（第三方修改＝快照失效）。
        await run_sql(
            "UPDATE library_items SET title = :title, updated_at = :later WHERE id = :id",
            {"title": "用户手改标题", "later": LATER, "id": item_id(0)},
            session_factory,
        )
        await finish_job(session_factory, "SUCCEEDED")
        assert isinstance(await claim_waiting(session_factory, run_id), Ready)

        # 修改步骤执行前重验失败：不覆盖用户修改、等待用户处置。
        assert await advance(session_factory, run_id) == "WAITING_USER"
        steps = await step_rows(session_factory, run_id)
        assert [(status, code) for _a, status, code, _attempts in steps] == [
            ("SUCCEEDED", None),
            ("SUCCEEDED", None),
            ("FAILED", "OPERATION_SNAPSHOT_STALE"),
        ]
        async with session_factory() as session:
            row = (
                await session.execute(
                    text("SELECT title, course_id FROM library_items WHERE id = :id"),
                    {"id": item_id(0)},
                )
            ).one()
        assert (row[0], row[1]) == ("用户手改标题", None)


@pytest.mark.anyio
async def test_ref_update_step_snapshot_complete_and_undoable(tmp_path: Path) -> None:
    """含引用修改步骤的正常路径（P1 回归另一半）：快照完整固化（非 "{}"）、
    执行归类生效、Undo 以快照恢复 before 值——修复前空快照撤销即
    OPERATION_UNDO_CONFLICT。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_item(session_factory, 0)
        direct = await invoke_plan(
            session_factory,
            [
                create_course_entry(),
                ingest_entry(course_id=COURSE_REF),
                {
                    "action": "update_library_item",
                    "item_id": item_id(0),
                    "title": "Agent 改名",
                    "course_id": COURSE_REF,
                },
            ],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        run_id = cast(str, direct["run"]["run_id"])
        assert await advance(session_factory, run_id) == "WAITING_JOB"

        await finish_job(session_factory, "SUCCEEDED")
        assert isinstance(await claim_waiting(session_factory, run_id), Ready)
        assert await advance(session_factory, run_id) == "COMPLETED"

        async with session_factory() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT snapshot_json FROM agent_operations"
                        " WHERE run_id = :run_id AND action = 'update_library_item'"
                    ),
                    {"run_id": run_id},
                )
            ).one()
        snapshot = cast(dict[str, Any], json.loads(cast(str, row[0])))
        assert snapshot["title"] == "条目0"
        assert snapshot["course_id"] is None

        # Undo 恢复归类前状态（快照 before 值）。
        step_id = await _step_id(session_factory, run_id, "update_library_item")
        async with session_factory() as session:
            await UndoService.undo_operation(session, operation_id=step_id)
        async with session_factory() as session:
            item = (
                await session.execute(
                    text("SELECT course_id FROM library_items WHERE id = :id"),
                    {"id": item_id(0)},
                )
            ).one()
        assert item[0] is None


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


# ---------------------------------------------------------------------------
# 执行中退出的自动恢复（工单 08）：进程中断 ≠ 业务失败


class _StaticClip:
    """恢复链路测试的抓取假体：恒返回同一正文（零真实网络）。"""

    def __init__(self, clip: ClipContent) -> None:
        self._clip = clip

    async def fetch_and_extract(self, url: str) -> ClipContent:
        return self._clip


async def interrupt_mid_fetch(session_factory: async_sessionmaker[AsyncSession]) -> str:
    """把等待中的 Run 推进到「抓取已领取、尚未写回」的中断瞬间：WEB_FETCH
    领取态（RUNNING、attempts=1），AGENT_RUN 触发随进程中断翻 FAILED。
    返回 run_id。"""
    direct = await invoke_plan(
        session_factory,
        [create_course_entry(), ingest_entry(course_id=COURSE_REF)],
        auth_mode=AuthMode.FULL_ACCESS,
    )
    run_id = cast(str, direct["run"]["run_id"])
    assert await advance(session_factory, run_id) == "WAITING_JOB"
    await run_sql(
        "UPDATE processing_jobs SET status = 'RUNNING', attempts = 1, started_at = :now"
        " WHERE job_type = 'WEB_FETCH'",
        {"now": NOW},
        session_factory,
    )
    await run_sql(
        "UPDATE processing_jobs SET status = 'FAILED', finished_at = :later"
        " WHERE job_type = 'AGENT_RUN'",
        {"later": LATER},
        session_factory,
    )
    return run_id


async def fetch_and_record_row(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[str, str | None, str | None]:
    """(job 状态, job 错误码, Record 状态)——抓取 job 关联记录联查。"""
    async with session_factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT j.status, j.error_code, r.status FROM processing_jobs j"
                    " JOIN records r ON r.id = j.record_id WHERE j.job_type = 'WEB_FETCH'"
                )
            )
        ).one()
    return (cast(str, row[0]), row[1], cast(str, row[2]))


@pytest.mark.anyio
async def test_interrupted_web_fetch_requeues_and_completes(tmp_path: Path) -> None:
    """WEB_FETCH 已领取尚未完成（进程中断）：重启恢复按 attempts 预算回
    PENDING 自动重投（对齐 DOCUMENT_PARSE 恢复形态）而非终态失败——Record
    维持处理中，经真实 worker 写回链路完成后 Run 对账唤醒续跑至 COMPLETED；
    来源对象不重复、Transcript 与记录状态一致（spec US32 自动续跑）。"""
    clip = ClipContent(
        text="中断恢复链路测试正文。" * 20,
        title="中断恢复测试页",
        metadata={"kind": "web", "url": URL},
    )
    async with bare_db(tmp_path) as session_factory:
        run_id = await interrupt_mid_fetch(session_factory)

        # 重启恢复（真实链路）：预算内（1 < 3）回 PENDING 带退避，Record 不翻失败。
        spec = web_fetch_spec(
            session_factory, tmp_path, RecordInvalidationNotifier(), _StaticClip(clip)
        )
        await spec.recover_interrupted()
        assert await fetch_and_record_row(session_factory) == (
            "PENDING",
            "WORKER_INTERRUPTED",
            "CONTENT_PROCESSING",
        )

        # Run 对账重投触发；退避到期后真实 worker 领取（attempts 2 ≤ 预算）
        # → 抓取 + 写回全链（Transcript 落库、Record 推进 SUMMARY_PENDING）。
        await spec_of(session_factory).recover_interrupted()
        await run_sql(
            "UPDATE processing_jobs SET next_run_at = NULL WHERE job_type = 'WEB_FETCH'",
            {},
            session_factory,
        )
        runner = JobRunner(spec, session_factory, RecordInvalidationNotifier())
        assert await runner.process_one() is True
        async with session_factory() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT j.status, r.status,"
                        " (SELECT COUNT(*) FROM transcripts t WHERE t.record_id = r.id)"
                        " FROM processing_jobs j JOIN records r ON r.id = j.record_id"
                        " WHERE j.job_type = 'WEB_FETCH'"
                    )
                )
            ).one()
        assert (row[0], row[1], row[2]) == ("SUCCEEDED", "SUMMARY_PENDING", 1)

        # 对账核对唤醒 → 续跑收尾；步骤不重做、来源对象不重复。
        decision = await claim_waiting(session_factory, run_id)
        assert isinstance(decision, Ready)
        assert await advance(session_factory, run_id) == "COMPLETED"
        steps = await step_rows(session_factory, run_id)
        assert [attempts for _a, _s, _c, attempts in steps] == [1, 1]
        async with session_factory() as session:
            counts = (
                await session.execute(
                    text(
                        "SELECT (SELECT COUNT(*) FROM library_items),"
                        " (SELECT COUNT(*) FROM records)"
                    )
                )
            ).one()
        assert (counts[0], counts[1]) == (1, 1)


@pytest.mark.anyio
async def test_interrupted_web_fetch_budget_exhausted_fails(tmp_path: Path) -> None:
    """执行中退出的预算边界：中断时 attempts 已达 max_attempts（多次中断重投
    后仍未完成）→ 恢复翻终态 FAILED（WORKER_INTERRUPTED）+ Record 失败；
    Run 对账走失败分流（PARTIAL_COMPLETED），保留手动重试通道。"""
    async with bare_db(tmp_path) as session_factory:
        run_id = await interrupt_mid_fetch(session_factory)
        await run_sql(
            "UPDATE processing_jobs SET attempts = 3 WHERE job_type = 'WEB_FETCH'",
            {},
            session_factory,
        )

        spec = web_fetch_spec(
            session_factory,
            tmp_path,
            RecordInvalidationNotifier(),
            _StaticClip(ClipContent(text="x", title=None, metadata={})),
        )
        await spec.recover_interrupted()
        assert await fetch_and_record_row(session_factory) == (
            "FAILED",
            "WORKER_INTERRUPTED",
            "FAILED",
        )

        # Run 对账重投触发 → 领取核对按失败分流 → 等待步骤 FAILED、部分完成。
        await spec_of(session_factory).recover_interrupted()
        assert isinstance(await claim_waiting(session_factory, run_id), Ready)
        assert await advance(session_factory, run_id) == "PARTIAL_COMPLETED"
        steps = await step_rows(session_factory, run_id)
        assert [(status, code) for _a, status, code, _attempts in steps] == [
            ("SUCCEEDED", None),
            ("FAILED", "AGENT_RUN_WAITING_JOB_FAILED"),
        ]


@pytest.mark.anyio
async def test_upgrade_migration_backfills_legacy_recovery_budget(tmp_path: Path) -> None:
    """升级前存量预算对齐（0040，工单 08 缺口收口）：恢复预算 1→3 只落在新建
    路径，升级前落库的 WEB_FETCH 未终态任务仍为 1——重启恢复 attempts(1) <
    max(1) 不成立，直接终态 FAILED，违反 spec US32。0040 迁移（0022 回填
    先例）在 worker 恢复前对齐存量预算，中断 job 照常回 PENDING 自动续跑。"""
    from tests.test_library import apply_migrations_upto

    db_path = tmp_path / "knowrealm.db"
    await apply_migrations_upto(db_path, 39)
    engine, session_factory = create_database(db_path)
    try:
        await interrupt_mid_fetch(session_factory)
        # 在真实 0039 库中预置旧预算，再重放后续迁移。
        await run_sql(
            "UPDATE processing_jobs SET max_attempts = 1 WHERE job_type = 'WEB_FETCH'",
            {},
            session_factory,
        )
        await run_migrations(db_path)
        async with session_factory() as session:
            legacy = (
                await session.execute(
                    text(
                        "SELECT max_attempts, status FROM processing_jobs"
                        " WHERE job_type = 'WEB_FETCH'"
                    )
                )
            ).one()
        assert (legacy[0], legacy[1]) == (3, "RUNNING")

        spec = web_fetch_spec(
            session_factory,
            tmp_path,
            RecordInvalidationNotifier(),
            _StaticClip(ClipContent(text="x", title=None, metadata={})),
        )
        await spec.recover_interrupted()
        assert await fetch_and_record_row(session_factory) == (
            "PENDING",
            "WORKER_INTERRUPTED",
            "CONTENT_PROCESSING",
        )
    finally:
        await engine.dispose()
