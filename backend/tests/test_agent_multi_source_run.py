"""通用 Agent 第三阶段工单 07：多资料建课编排（spec M2，User Stories 29~34）。

- 编排全链（含结果绑定链）：四类来源逐份导入（URL / 本地文档 / 粘贴文本 /
  库内资料挂课两路径）→ 建课 → 建目标（course_id 引用注入）→ 末步
  generate_plan_draft（goal_id 引用注入）产草案确认卡——草案确认是 Run 之外
  的人工闸门（learning_plans 仅确认时写入）；
- 部分成功：单项失败不回滚已完成步骤与已建课程，Run 落 PARTIAL_COMPLETED，
  失败步骤可单独重试（导入幂等收口：复用既有条目不再撞重复拒绝）；
- 重规划升回确认：执行中（等待态）追加新目标经工具提交也出计划卡，完全
  访问档亦然（固定对象集合 + 参数 + 版本即授权范围）；
- 授权语义：批次授权不跳过总结与学习资产的原有采纳审核（Run 完成后
  learning_plans / ai_summaries CONFIRMED / knowledge_points 零自动写入）；
- 大 PDF（本地文档）仍按整本一条记录处理。
"""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.data_dir import bind_data_dir, unbind_data_dir
from app.db.engine import create_database
from app.db.migrations import run_migrations
from app.modules.agent.operations import plan_draft as plan_draft_module
from app.modules.agent.operations.plan_draft import (
    PLAN_DRAFT_LLM_UNCONFIGURED,
    plan_draft_spec,
)
from app.modules.agent.runs.schemas import AuthMode
from app.modules.agent.runs.service import RunControlService, RunHistoryService
from app.modules.agent.runs.worker import advance_run, validate_claim
from app.modules.agent.runtime import (
    AgentRuntimeContext,
    ToolCallBudget,
    bind_agent_runtime_context,
    reset_agent_runtime_context,
)
from app.modules.agent.tools.plan_batch_operations import plan_batch_operations
from app.modules.jobs.models import ProcessingJob
from app.modules.jobs.runner import JobRunner, Ready
from app.modules.learning_plan.generation import (
    MaterialDigest,
    PlanGenerationOutcome,
    PlanGenerationService,
)
from app.modules.learning_plan.schemas import PlanConfirmCore
from app.modules.library.proposals import ProposalService
from app.modules.llm.service import StructuredGenerationError
from app.modules.settings.config import LlmProviderConfig
from app.modules.transcript import document_worker
from app.modules.transcript.document_parser import extract_document
from app.shared.errors import CodedHTTPException
from app.shared.events import RecordInvalidationNotifier

NOW = "2026-10-04T08:00:00.000000Z"
LATER = "2026-10-04T09:00:00.000000Z"
SESSION_ID = "sess-multi-source"
URL = "https://example.com/attention-paper"

COURSE_REF = {"step": 0, "field": "course_id"}
GOAL_REF = {"step": 1, "field": "goal_id"}


def item_id(index: int) -> str:
    return f"b0000000-0000-4000-8000-{index:012d}"


@asynccontextmanager
async def bare_db(tmp_path: Path) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    data_dir = tmp_path / "KnowRealm"
    data_dir.mkdir()
    db_path = data_dir / "knowrealm.db"
    await run_migrations(db_path)
    _engine, session_factory = create_database(db_path)
    # 本地文档导入步骤经 bound_data_dir() 取数据目录（files/ 落盘与磁盘检查）。
    bind_data_dir(data_dir)
    try:
        yield session_factory
    finally:
        unbind_data_dir()
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
            "title": f"共享候选{index}",
            "hash": f"mhash-{index}",
            "now": NOW,
        },
        session_factory,
    )


def orchestration_entries(local_file: Path) -> list[dict[str, Any]]:
    """四类来源 + 建课 + 建目标 + 挂课两路径 + 末步草案产出的完整编排
    （工单目标场景：把这几篇论文整理到新课程并生成学习计划）。"""
    return [
        {
            "action": "create_course",
            "name": "论文精读",
            "learning_context": "CAREER",
            "depth": "INTERMEDIATE",
        },
        {
            "action": "create_goal",
            "course_id": COURSE_REF,
            "goal_type": "SKILL",
            "title": "四周吃透这批论文",
        },
        {"action": "ingest_library_item", "url": URL, "course_id": COURSE_REF},
        {
            "action": "ingest_local_document",
            "path": str(local_file),
            "course_id": COURSE_REF,
        },
        {
            "action": "add_text_record_to_course",
            "content": "论文 A 的核心结论：注意力机制可并行化。",
            "course_id": COURSE_REF,
        },
        {"action": "update_library_item", "item_id": item_id(1), "course_id": COURSE_REF},
        {
            "action": "add_shared_ref",
            "library_item_id": item_id(2),
            "course_id": COURSE_REF,
        },
        {"action": "generate_plan_draft", "goal_id": GOAL_REF},
    ]


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
            instruction_excerpt="把这几篇论文整理到新课程并生成学习计划",
            message_id="msg-1",
            budget=ToolCallBudget(),
        )
    )
    try:
        raw = await plan_batch_operations.ainvoke({"items": entries})
        return dict(json.loads(raw))
    finally:
        reset_agent_runtime_context(token)


async def confirm_plan_card(
    session_factory: async_sessionmaker[AsyncSession], proposal_id: str
) -> str:
    async with session_factory() as session:
        result = await ProposalService.confirm(session, proposal_id)
    applied: dict[str, Any] = result.result or {}
    return cast(str, applied["run_id"])


async def advance(session_factory: async_sessionmaker[AsyncSession], run_id: str) -> str:
    return await advance_run(session_factory, run_id)


async def run_row(
    session_factory: async_sessionmaker[AsyncSession], run_id: str
) -> tuple[str, str | None, str | None]:
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
) -> list[tuple[str, str, str | None]]:
    async with session_factory() as session:
        detail = await RunHistoryService.get_run_detail(session, run_id)
    order = [item["id"] for item in cast(list[dict[str, Any]], detail["operations"])]
    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT id, action, status, error_code FROM agent_operations"
                    " WHERE run_id = :run_id"
                ),
                {"run_id": run_id},
            )
        ).all()
    by_id = {cast(str, row[0]): row for row in rows}
    return [
        (cast(str, row[1]), cast(str, row[2]), row[3])
        for row in (by_id[operation_id] for operation_id in order)
    ]


async def step_id(
    session_factory: async_sessionmaker[AsyncSession], run_id: str, action: str
) -> str:
    async with session_factory() as session:
        found = (
            await session.execute(
                text(
                    "SELECT id FROM agent_operations WHERE run_id = :run_id"
                    " AND action = :action ORDER BY created_at LIMIT 1"
                ),
                {"run_id": run_id, "action": action},
            )
        ).scalar_one()
    return cast(str, found)


async def pending_trigger_job(
    session_factory: async_sessionmaker[AsyncSession], run_id: str
) -> str:
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


async def claim_waiting(session_factory: async_sessionmaker[AsyncSession], run_id: str) -> Any:
    """对等待中的 Run 跑一次领取闸门（模拟 JobRunner 轮询核对 job 终态）。"""
    async with session_factory() as session, session.begin():
        job = await session.get(ProcessingJob, await pending_trigger_job(session_factory, run_id))
        assert job is not None
        return await validate_claim(session, job, "", None)


async def finish_pending_jobs(
    session_factory: async_sessionmaker[AsyncSession], job_type: str, status: str
) -> int:
    """把该类型全部 PENDING job 落定为终态（返回落数）。"""
    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT id FROM processing_jobs WHERE job_type = :type"
                    " AND status = 'PENDING' ORDER BY created_at, id"
                ),
                {"type": job_type},
            )
        ).all()
    for row in rows:
        await run_sql(
            "UPDATE processing_jobs SET status = :status, finished_at = :later WHERE id = :id",
            {"status": status, "later": LATER, "id": cast(str, row[0])},
            session_factory,
        )
    return len(rows)


async def scalar(
    session_factory: async_sessionmaker[AsyncSession], sql: str, params: dict[str, object]
) -> Any:
    async with session_factory() as session:
        return await session.execute(text(sql), params)


def fake_draft_plan(goal_id: str) -> PlanConfirmCore:
    # 日期用运行时今天：execute 的提交前重验按 local_today() 重算排期，
    # 硬编码日期会与期望铺排不符被拒（同日 60+30=90 ≤ 默认预算 120 自洽）。
    day = date.today()
    return PlanConfirmCore.model_validate(
        {
            "goal_id": goal_id,
            "phases": [
                {
                    "title": "第一阶段",
                    "items": [
                        {
                            "action_type": "STUDY_RECORD",
                            "content": "精读注意力论文",
                            "estimated_minutes": 60,
                            "reason": "核心资料",
                            "scheduled_date": day.isoformat(),
                        },
                        {
                            "action_type": "CUSTOM",
                            "content": "整理笔记",
                            "estimated_minutes": 30,
                            "reason": "巩固理解",
                            "scheduled_date": day.isoformat(),
                        },
                    ],
                }
            ],
        }
    )


@pytest.fixture
def draft_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """PLAN_DRAFT worker 的 LLM 假体：provider 恒可用、草案恒两项目
    （失败注入的用例在测试内另行 monkeypatch）。"""
    provider = LlmProviderConfig(
        base_url="https://llm.example.com/v1", api_key="test-key", model="test-model"
    )

    def fake_provider(_data_dir: Path) -> LlmProviderConfig:
        return provider

    monkeypatch.setattr("app.modules.agent.operations.plan_draft.load_llm_provider", fake_provider)

    async def fake_generate(**kwargs: Any) -> PlanGenerationOutcome:
        goal = kwargs["goal"]
        return PlanGenerationOutcome(
            kind="DRAFT",
            plan=fake_draft_plan(goal.id),
            total_minutes=90,
            materials_used=len(cast(list[MaterialDigest], kwargs.get("materials") or [])),
        )

    monkeypatch.setattr(PlanGenerationService, "generate", staticmethod(fake_generate))


async def run_draft_worker(
    session_factory: async_sessionmaker[AsyncSession], data_dir: Path
) -> bool:
    """跑一次 PLAN_DRAFT worker（claim → execute → writeback 全链）。"""
    runner = JobRunner(
        plan_draft_spec(session_factory, RecordInvalidationNotifier(), data_dir),
        session_factory,
        RecordInvalidationNotifier(),
    )
    return await runner.process_one()


# ---------------------------------------------------------------------------
# 编排全链（含结果绑定链）


@pytest.mark.anyio
async def test_full_orchestration_chain(tmp_path: Path, draft_llm: None) -> None:
    """目标场景全链：四类来源 → 建课（id 绑定注入）→ 建目标（id 绑定注入末步）
    → 挂课两路径 → 末步产草案确认卡；草案确认是 Run 外闸门（确认前零计划落库，
    确认后才 ACTIVE）；总结与学习资产不被批次授权自动采纳；本地文档整本一条
    记录。"""
    local_file = tmp_path / "paper.txt"
    local_file.write_text("Transformer 论文全文（大 PDF 场景的整本单记录口径）", encoding="utf-8")
    async with bare_db(tmp_path) as session_factory:
        await seed_item(session_factory, 1)
        await seed_item(session_factory, 2)
        planned = await invoke_plan(session_factory, orchestration_entries(local_file))
        assert "plan_proposal" in planned
        run_id = await confirm_plan_card(
            session_factory, cast(str, planned["plan_proposal"]["proposal_id"])
        )

        # 步骤 0~2：建课 → 建目标（引用注入）→ URL 导入提交 job → 转等待。
        assert await advance(session_factory, run_id) == "WAITING_JOB"
        steps = await step_rows(session_factory, run_id)
        assert [(action, status) for action, status, _code in steps[:3]] == [
            ("create_course", "SUCCEEDED"),
            ("create_goal", "SUCCEEDED"),
            ("ingest_library_item", "SUCCEEDED"),
        ]
        course = (
            await scalar(
                session_factory,
                "SELECT id FROM courses WHERE name = '论文精读'",
                {},
            )
        ).one()
        goal_row = (
            await scalar(
                session_factory,
                "SELECT id, scope_confirmed, scope_source, status FROM learning_goals",
                {},
            )
        ).one()
        assert goal_row[1] == 1 and goal_row[2] == "AI_INFERRED" and goal_row[3] == "ACTIVE"

        # WEB_FETCH 完成 → 唤醒 → 本地文档导入提交 DOCUMENT_PARSE → 再等待。
        await finish_pending_jobs(session_factory, "WEB_FETCH", "SUCCEEDED")
        assert isinstance(await claim_waiting(session_factory, run_id), Ready)
        assert await advance(session_factory, run_id) == "WAITING_JOB"
        doc_jobs = await finish_pending_jobs(session_factory, "DOCUMENT_PARSE", "SUCCEEDED")
        assert doc_jobs == 1

        # 文档解析完成 → 唤醒 → 粘贴文本 / 归类 / 共享引用瞬时完成 → 末步
        # 草案产出提交 PLAN_DRAFT job → 再等待。
        assert isinstance(await claim_waiting(session_factory, run_id), Ready)
        assert await advance(session_factory, run_id) == "WAITING_JOB"
        steps = await step_rows(session_factory, run_id)
        assert [(action, status) for action, status, _code in steps] == [
            ("create_course", "SUCCEEDED"),
            ("create_goal", "SUCCEEDED"),
            ("ingest_library_item", "SUCCEEDED"),
            ("ingest_local_document", "SUCCEEDED"),
            ("add_text_record_to_course", "SUCCEEDED"),
            ("update_library_item", "SUCCEEDED"),
            ("add_shared_ref", "SUCCEEDED"),
            ("generate_plan_draft", "SUCCEEDED"),
        ]

        # Run 外闸门：草案生成 job 未跑完前，learning_plans 零行、总结与
        # 学习资产零自动采纳（批次授权不跳过人工审核）。
        assert (
            await scalar(session_factory, "SELECT COUNT(*) FROM learning_plans", {})
        ).scalar_one() == 0
        assert (
            await scalar(
                session_factory,
                "SELECT COUNT(*) FROM ai_summaries WHERE status = 'CONFIRMED'",
                {},
            )
        ).scalar_one() == 0
        assert (
            await scalar(session_factory, "SELECT COUNT(*) FROM knowledge_points", {})
        ).scalar_one() == 0

        # PLAN_DRAFT worker 完成草案生成：落 OP_PLAN_CONFIRM 草案确认卡（PENDING）。
        assert await run_draft_worker(session_factory, tmp_path) is True
        proposal_row = (
            await scalar(
                session_factory,
                "SELECT id, status, proposal_type FROM agent_proposals"
                " WHERE proposal_type = 'OP_PLAN_CONFIRM'",
                {},
            )
        ).one()
        assert proposal_row[1] == "PENDING"

        # 草案 job 完成 → 唤醒 → Run 全部成功 COMPLETED。
        assert isinstance(await claim_waiting(session_factory, run_id), Ready)
        assert await advance(session_factory, run_id) == "COMPLETED"

        # 草案确认（Run 外人工闸门）→ 计划落库 ACTIVE。
        async with session_factory() as session:
            await ProposalService.confirm(session, cast(str, proposal_row[0]))
        assert (
            await scalar(
                session_factory,
                "SELECT status FROM learning_plans",
                {},
            )
        ).scalar_one() == "ACTIVE"

        # 本地文档整本一条记录；四类来源产物均归入新课程。
        assert (
            await scalar(
                session_factory,
                "SELECT COUNT(*) FROM records WHERE capture_type = 'DOCUMENT_IMPORT'",
                {},
            )
        ).scalar_one() == 1
        assert (
            await scalar(
                session_factory,
                "SELECT COUNT(*) FROM records WHERE course_id = :cid AND deleted_at IS NULL",
                {"cid": course[0]},
            )
        ).scalar_one() == 3  # URL + 本地文档 + 粘贴文本
        shared = (
            await scalar(
                session_factory,
                "SELECT COUNT(*) FROM course_shared_refs WHERE course_id = :cid",
                {"cid": course[0]},
            )
        ).scalar_one()
        assert shared == 1
        moved = (
            await scalar(
                session_factory,
                "SELECT course_id FROM library_items WHERE id = :id",
                {"id": item_id(1)},
            )
        ).one()
        assert moved[0] == course[0]


# ---------------------------------------------------------------------------
# 部分成功与单独重试


@pytest.mark.anyio
async def test_partial_failure_keeps_course_and_imports(tmp_path: Path) -> None:
    """单项失败不回滚已完成步骤与已建课程：两份导入一成一败 → Run
    PARTIAL_COMPLETED、课程与首份导入保留、依赖失败步骤 SKIPPED。"""
    async with bare_db(tmp_path) as session_factory:
        planned = await invoke_plan(
            session_factory,
            [
                {
                    "action": "create_course",
                    "name": "混合资料",
                    "learning_context": "INTEREST",
                    "depth": "BEGINNER",
                },
                {"action": "ingest_library_item", "url": URL, "course_id": COURSE_REF},
                {
                    "action": "ingest_library_item",
                    "url": "https://example.com/broken",
                    "course_id": COURSE_REF,
                },
                {
                    "action": "add_text_record_to_course",
                    "content": "备用笔记",
                    "course_id": COURSE_REF,
                    "depends_on": [2],
                },
            ],
        )
        run_id = await confirm_plan_card(
            session_factory, cast(str, planned["plan_proposal"]["proposal_id"])
        )
        assert await advance(session_factory, run_id) == "WAITING_JOB"
        await finish_pending_jobs(session_factory, "WEB_FETCH", "SUCCEEDED")
        assert isinstance(await claim_waiting(session_factory, run_id), Ready)
        assert await advance(session_factory, run_id) == "WAITING_JOB"
        await finish_pending_jobs(session_factory, "WEB_FETCH", "FAILED")
        assert isinstance(await claim_waiting(session_factory, run_id), Ready)
        assert await advance(session_factory, run_id) == "PARTIAL_COMPLETED"
        steps = await step_rows(session_factory, run_id)
        assert [(action, status, code) for action, status, code in steps] == [
            ("create_course", "SUCCEEDED", None),
            ("ingest_library_item", "SUCCEEDED", None),
            ("ingest_library_item", "FAILED", "AGENT_RUN_WAITING_JOB_FAILED"),
            ("add_text_record_to_course", "SKIPPED", "OPERATION_DEPENDENCY_FAILED"),
        ]
        # 已建课程保留、首份导入真实归课（不回滚）。
        course = (
            await scalar(session_factory, "SELECT id FROM courses WHERE name = '混合资料'", {})
        ).one()
        kept = (
            await scalar(
                session_factory,
                "SELECT course_id FROM library_items WHERE origin_uri = :url",
                {"url": URL},
            )
        ).one()
        assert kept[0] == course[0]


@pytest.mark.anyio
async def test_retry_failed_ingest_reuses_item(tmp_path: Path) -> None:
    """失败导入步骤单独重试的幂等收口：抓取失败后条目已在库，重试不撞重复
    拒绝也不重复入库——复用既有条目并重置 WEB_FETCH 任务重新抓取（如实等待，
    不直接消除失败；07 review 二轮 P1 的回归防线）。"""
    async with bare_db(tmp_path) as session_factory:
        planned = await invoke_plan(
            session_factory,
            [
                {
                    "action": "create_course",
                    "name": "重试课",
                    "learning_context": "INTEREST",
                    "depth": "BEGINNER",
                },
                {"action": "ingest_library_item", "url": URL, "course_id": COURSE_REF},
            ],
        )
        run_id = await confirm_plan_card(
            session_factory, cast(str, planned["plan_proposal"]["proposal_id"])
        )
        assert await advance(session_factory, run_id) == "WAITING_JOB"
        await finish_pending_jobs(session_factory, "WEB_FETCH", "FAILED")
        assert isinstance(await claim_waiting(session_factory, run_id), Ready)
        assert await advance(session_factory, run_id) == "PARTIAL_COMPLETED"

        async with session_factory() as session:
            await RunControlService.retry_operation(
                session,
                run_id=run_id,
                operation_id=await step_id(session_factory, run_id, "ingest_library_item"),
            )
        # 重试复用条目并重置既有任务重新等待（任务总数不变，未新投）。
        assert await advance(session_factory, run_id) == "WAITING_JOB"
        job_count = (
            await scalar(
                session_factory,
                "SELECT COUNT(*) FROM processing_jobs WHERE job_type = 'WEB_FETCH'",
                {},
            )
        ).scalar_one()
        assert job_count == 1
        # 重新抓取成功后 Run 才完成；再失败则仍部分成功（如实呈现）。
        assert await finish_pending_jobs(session_factory, "WEB_FETCH", "SUCCEEDED") == 1
        assert isinstance(await claim_waiting(session_factory, run_id), Ready)
        assert await advance(session_factory, run_id) == "COMPLETED"
        # 同 URL 条目只有一条（重试复用，未重复入库）。
        count = (
            await scalar(
                session_factory,
                "SELECT COUNT(*) FROM library_items WHERE origin_uri = :url",
                {"url": URL},
            )
        ).scalar_one()
        assert count == 1


@pytest.mark.anyio
async def test_retry_local_document_reschedules_parse(tmp_path: Path) -> None:
    """本地文档解析失败后的重试：复用既有导入行（不重复建记录），上次失败的
    解析任务原地重置（不新投——新投会使任务数超过文件数，finalizer 等数判定
    永不成立，任务成功后记录卡 CONTENT_PROCESSING、无正文），成功经真实
    writeback 链路落 Transcript（07 review P1 的回归防线）。"""
    source = tmp_path / "notes.md"
    source.write_text("# 重试笔记\n本地文档内容", encoding="utf-8")
    async with bare_db(tmp_path) as session_factory:
        planned = await invoke_plan(
            session_factory,
            [
                {
                    "action": "ingest_local_document",
                    "path": str(source),
                }
            ],
        )
        run_id = await confirm_plan_card(
            session_factory, cast(str, planned["plan_proposal"]["proposal_id"])
        )
        assert await advance(session_factory, run_id) == "WAITING_JOB"
        assert await finish_pending_jobs(session_factory, "DOCUMENT_PARSE", "FAILED") == 1
        assert isinstance(await claim_waiting(session_factory, run_id), Ready)
        assert await advance(session_factory, run_id) == "PARTIAL_COMPLETED"

        async with session_factory() as session:
            await RunControlService.retry_operation(
                session,
                run_id=run_id,
                operation_id=await step_id(session_factory, run_id, "ingest_local_document"),
            )
        # 重试后 Run 重新等待；解析任务原地重置（总数仍 1，未新投）。
        assert await advance(session_factory, run_id) == "WAITING_JOB"
        job_count = (
            await scalar(
                session_factory,
                "SELECT COUNT(*) FROM processing_jobs WHERE job_type = 'DOCUMENT_PARSE'",
                {},
            )
        ).scalar_one()
        assert job_count == 1

        # 真实 worker 写回链路：模拟领取（RUNNING）→ 解析 → writeback（内部
        # complete_source_job 判定文件数==任务数并落 Transcript）。
        data_dir = tmp_path / "KnowRealm"
        job_row = (
            await scalar(
                session_factory,
                "SELECT p.id, r.id, f.file_path FROM processing_jobs p"
                " JOIN records r ON p.record_id = r.id"
                " JOIN record_files f ON f.record_id = r.id"
                " WHERE p.job_type = 'DOCUMENT_PARSE'",
                {},
            )
        ).one()
        job_id = cast(str, job_row[0])
        record_id = cast(str, job_row[1])
        file_path = cast(str, job_row[2])
        await run_sql(
            "UPDATE processing_jobs SET status = 'RUNNING', attempts = 1 WHERE id = :id",
            {"id": job_id},
            session_factory,
        )
        ctx = document_worker.ClaimedDocument(
            job_id=job_id, record_id=record_id, path=data_dir / file_path
        )
        await document_worker.writeback(ctx, extract_document(ctx.path), session_factory, data_dir)

        # 任务成功且记录被 finalizer 落定（不卡 CONTENT_PROCESSING）。
        final_row = (
            await scalar(
                session_factory,
                "SELECT (SELECT status FROM processing_jobs WHERE id = :job_id),"
                " (SELECT status FROM records WHERE id = :record_id),"
                " (SELECT COUNT(*) FROM transcripts WHERE record_id = :record_id)",
                {"job_id": job_id, "record_id": record_id},
            )
        ).one()
        assert cast(str, final_row[0]) == "SUCCEEDED"
        assert cast(str, final_row[1]) == "SUMMARY_PENDING"
        assert cast(int, final_row[2]) == 1
        assert isinstance(await claim_waiting(session_factory, run_id), Ready)
        assert await advance(session_factory, run_id) == "COMPLETED"
        records = (
            await scalar(
                session_factory,
                "SELECT COUNT(*) FROM records WHERE capture_type = 'DOCUMENT_IMPORT'",
                {},
            )
        ).scalar_one()
        assert records == 1  # 复用既有导入，整本仍一条记录


# ---------------------------------------------------------------------------
# 草案产出的失败与重试


@pytest.mark.anyio
async def test_plan_draft_job_failure_then_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """草案生成 job 失败（LLM 输出无效）：等待步骤翻 FAILED、Run 落部分完成；
    单独重试后新投任务成功，草案确认卡落库。"""
    provider = LlmProviderConfig(
        base_url="https://llm.example.com/v1", api_key="test-key", model="test-model"
    )

    def fake_provider(_data_dir: Path) -> LlmProviderConfig:
        return provider

    monkeypatch.setattr("app.modules.agent.operations.plan_draft.load_llm_provider", fake_provider)
    calls: list[int] = []

    async def flaky_generate(**kwargs: Any) -> PlanGenerationOutcome:
        calls.append(1)
        if len(calls) == 1:
            raise StructuredGenerationError("LLM_OUTPUT_INVALID")
        goal = kwargs["goal"]
        return PlanGenerationOutcome(kind="DRAFT", plan=fake_draft_plan(goal.id), total_minutes=90)

    monkeypatch.setattr(PlanGenerationService, "generate", staticmethod(flaky_generate))
    async with bare_db(tmp_path) as session_factory:
        planned = await invoke_plan(
            session_factory,
            [
                {
                    "action": "create_course",
                    "name": "草案课",
                    "learning_context": "INTEREST",
                    "depth": "BEGINNER",
                },
                {
                    "action": "create_goal",
                    "course_id": COURSE_REF,
                    "goal_type": "SKILL",
                    "title": "读完这批资料",
                },
                {"action": "generate_plan_draft", "goal_id": GOAL_REF},
            ],
        )
        run_id = await confirm_plan_card(
            session_factory, cast(str, planned["plan_proposal"]["proposal_id"])
        )
        assert await advance(session_factory, run_id) == "WAITING_JOB"
        # PLAN_DRAFT job 首跑失败（LLM 输出无效）。
        assert await run_draft_worker(session_factory, tmp_path) is True
        assert isinstance(await claim_waiting(session_factory, run_id), Ready)
        assert await advance(session_factory, run_id) == "PARTIAL_COMPLETED"
        steps = await step_rows(session_factory, run_id)
        assert steps[-1] == (
            "generate_plan_draft",
            "FAILED",
            "AGENT_RUN_WAITING_JOB_FAILED",
        )
        # 单独重试：新投 PLAN_DRAFT job，本次成功产草案卡。
        async with session_factory() as session:
            await RunControlService.retry_operation(
                session,
                run_id=run_id,
                operation_id=await step_id(session_factory, run_id, "generate_plan_draft"),
            )
        assert await advance(session_factory, run_id) == "WAITING_JOB"
        assert await run_draft_worker(session_factory, tmp_path) is True
        assert isinstance(await claim_waiting(session_factory, run_id), Ready)
        assert await advance(session_factory, run_id) == "COMPLETED"
        proposal = (
            await scalar(
                session_factory,
                "SELECT COUNT(*) FROM agent_proposals WHERE proposal_type = 'OP_PLAN_CONFIRM'",
                {},
            )
        ).scalar_one()
        assert proposal == 1


@pytest.mark.anyio
async def test_plan_draft_rejects_stale_constraints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """生成期间目标预算 60→15：旧口径草案（单项 60 分钟）被提交前重验拒绝
    （稳定失败码、零草案卡落库），单独重试按新约束重新生成成功（spec 预算
    一致性：每日总量与 daily_minutes 相容，07 review 五轮 P2）。"""
    provider = LlmProviderConfig(
        base_url="https://llm.example.com/v1", api_key="test-key", model="test-model"
    )
    monkeypatch.setattr(
        "app.modules.agent.operations.plan_draft.load_llm_provider",
        lambda _data_dir: provider,
    )
    calls: list[int] = []
    async with bare_db(tmp_path) as session_factory:

        async def shifting_generate(**kwargs: Any) -> PlanGenerationOutcome:
            calls.append(1)
            goal = kwargs["goal"]
            day = date.today()
            if len(calls) == 1:
                # LLM 生成期间每日预算 60 → 15；草案按旧口径（单项 60 分钟）。
                async with session_factory() as session, session.begin():
                    await session.execute(
                        text("UPDATE learning_goals SET daily_minutes = 15 WHERE id = :id"),
                        {"id": goal.id},
                    )
                stale = PlanConfirmCore.model_validate(
                    {
                        "goal_id": goal.id,
                        "phases": [
                            {
                                "title": "第一阶段",
                                "items": [
                                    {
                                        "action_type": "CUSTOM",
                                        "content": "精读核心论文",
                                        "estimated_minutes": 60,
                                        "reason": "核心",
                                        "scheduled_date": day.isoformat(),
                                    }
                                ],
                            }
                        ],
                    }
                )
                return PlanGenerationOutcome(kind="DRAFT", plan=stale, total_minutes=60)
            fresh = PlanConfirmCore.model_validate(
                {
                    "goal_id": goal.id,
                    "phases": [
                        {
                            "title": "第一阶段",
                            "items": [
                                {
                                    "action_type": "CUSTOM",
                                    "content": "精读核心论文",
                                    "estimated_minutes": 15,
                                    "reason": "核心",
                                    "scheduled_date": day.isoformat(),
                                }
                            ],
                        }
                    ],
                }
            )
            return PlanGenerationOutcome(kind="DRAFT", plan=fresh, total_minutes=15)

        monkeypatch.setattr(PlanGenerationService, "generate", staticmethod(shifting_generate))
        planned = await invoke_plan(
            session_factory,
            [
                {
                    "action": "create_course",
                    "name": "预算课",
                    "learning_context": "INTEREST",
                    "depth": "BEGINNER",
                },
                {
                    "action": "create_goal",
                    "course_id": COURSE_REF,
                    "goal_type": "SKILL",
                    "title": "读完这批资料",
                    "daily_minutes": 60,
                },
                {"action": "generate_plan_draft", "goal_id": GOAL_REF},
            ],
        )
        run_id = await confirm_plan_card(
            session_factory, cast(str, planned["plan_proposal"]["proposal_id"])
        )
        assert await advance(session_factory, run_id) == "WAITING_JOB"
        # 首跑：生成期间约束已变 → 旧口径草案被提交前重验拒绝（稳定失败码）。
        assert await run_draft_worker(session_factory, tmp_path) is True
        job_row = (
            await scalar(
                session_factory,
                "SELECT status, error_code FROM processing_jobs WHERE job_type = 'PLAN_DRAFT'",
                {},
            )
        ).one()
        assert job_row == ("FAILED", "PLAN_SCHEDULE_INFEASIBLE")
        assert isinstance(await claim_waiting(session_factory, run_id), Ready)
        assert await advance(session_factory, run_id) == "PARTIAL_COMPLETED"
        # 零草案卡（旧口径草案不落确认卡）。
        assert (
            await scalar(
                session_factory,
                "SELECT COUNT(*) FROM agent_proposals WHERE proposal_type = 'OP_PLAN_CONFIRM'",
                {},
            )
        ).scalar_one() == 0
        # 单独重试：约束已变 → 提交期快照比对失效，升回用户确认（既有防线，
        # 等待重新预览授权后才会按新约束重新生成）。
        async with session_factory() as session:
            await RunControlService.retry_operation(
                session,
                run_id=run_id,
                operation_id=await step_id(session_factory, run_id, "generate_plan_draft"),
            )
        assert await advance(session_factory, run_id) == "WAITING_USER"
        steps = await step_rows(session_factory, run_id)
        assert steps[-1] == ("generate_plan_draft", "FAILED", "OPERATION_SNAPSHOT_STALE")
        assert await run_row(session_factory, run_id) == (
            "WAITING_USER",
            "OPERATION_SNAPSHOT_STALE",
            None,
        )


@pytest.mark.anyio
async def test_plan_draft_writeback_revalidates_in_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """execute 校验通过后、写回事务前约束再变（120→15）：写回事务内终验拦截
    旧草案、不落确认卡（07 review 九轮 P2——execute 尾部校验只覆盖生成期间
    窗口，最后窗口由写回事务内核对，变化不再被新快照掩盖）。"""
    provider = LlmProviderConfig(
        base_url="https://llm.example.com/v1", api_key="test-key", model="test-model"
    )
    monkeypatch.setattr(
        "app.modules.agent.operations.plan_draft.load_llm_provider",
        lambda _data_dir: provider,
    )
    day = date.today().isoformat()

    async def plain_generate(**kwargs: Any) -> PlanGenerationOutcome:
        goal = kwargs["goal"]
        plan = PlanConfirmCore.model_validate(
            {
                "goal_id": goal.id,
                "phases": [
                    {
                        "title": "第一阶段",
                        "items": [
                            {
                                "action_type": "CUSTOM",
                                "content": "精读",
                                "estimated_minutes": 60,
                                "reason": "核心",
                                "scheduled_date": day,
                            },
                            {
                                "action_type": "CUSTOM",
                                "content": "整理",
                                "estimated_minutes": 30,
                                "reason": "巩固",
                                "scheduled_date": day,
                            },
                        ],
                    }
                ],
            }
        )
        return PlanGenerationOutcome(kind="DRAFT", plan=plan, total_minutes=90)

    monkeypatch.setattr(PlanGenerationService, "generate", staticmethod(plain_generate))
    async with bare_db(tmp_path) as session_factory:
        original_validate = plan_draft_module.validate_plan_confirm_submission
        validate_calls: list[int] = []

        async def injecting_validate(session: Any, payload: Any) -> None:
            # 第一次（execute 尾部，默认预算 120）通过后即注入 15——模拟两阶段
            # 之间用户改预算；第二次（writeback 终验，修复后存在）将如实拒绝。
            await original_validate(session, payload)
            validate_calls.append(1)
            if len(validate_calls) == 1:
                async with session_factory() as s, s.begin():
                    await s.execute(
                        text("UPDATE learning_goals SET daily_minutes = 15 WHERE id = :id"),
                        {"id": payload.goal_id},
                    )

        monkeypatch.setattr(
            plan_draft_module, "validate_plan_confirm_submission", injecting_validate
        )
        planned = await invoke_plan(
            session_factory,
            [
                {
                    "action": "create_course",
                    "name": "终验课",
                    "learning_context": "INTEREST",
                    "depth": "BEGINNER",
                },
                {
                    "action": "create_goal",
                    "course_id": COURSE_REF,
                    "goal_type": "SKILL",
                    "title": "读完这批资料",
                },
                {"action": "generate_plan_draft", "goal_id": GOAL_REF},
            ],
        )
        run_id = await confirm_plan_card(
            session_factory, cast(str, planned["plan_proposal"]["proposal_id"])
        )
        assert await advance(session_factory, run_id) == "WAITING_JOB"
        # 写回事务内终验拒绝旧口径草案（稳定失败码，零确认卡落库）。
        with pytest.raises(CodedHTTPException) as excinfo:
            await run_draft_worker(session_factory, tmp_path)
        assert excinfo.value.code == "PLAN_SCHEDULE_INFEASIBLE"
        assert (
            await scalar(
                session_factory,
                "SELECT COUNT(*) FROM agent_proposals WHERE proposal_type = 'OP_PLAN_CONFIRM'",
                {},
            )
        ).scalar_one() == 0


@pytest.mark.anyio
async def test_plan_draft_requires_llm_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LLM 未配置：草案生成 job 落稳定失败码（不误报成功），等待步骤翻
    FAILED 可重试（配置后重试即生成）。"""

    def no_provider(_data_dir: Path) -> None:
        return None

    monkeypatch.setattr("app.modules.agent.operations.plan_draft.load_llm_provider", no_provider)
    async with bare_db(tmp_path) as session_factory:
        planned = await invoke_plan(
            session_factory,
            [
                {
                    "action": "create_course",
                    "name": "无配置课",
                    "learning_context": "INTEREST",
                    "depth": "BEGINNER",
                },
                {
                    "action": "create_goal",
                    "course_id": COURSE_REF,
                    "goal_type": "SKILL",
                    "title": "无 LLM 配置的目标",
                },
                {"action": "generate_plan_draft", "goal_id": GOAL_REF},
            ],
        )
        run_id = await confirm_plan_card(
            session_factory, cast(str, planned["plan_proposal"]["proposal_id"])
        )
        assert await advance(session_factory, run_id) == "WAITING_JOB"
        assert await run_draft_worker(session_factory, tmp_path) is True
        job_row = (
            await scalar(
                session_factory,
                "SELECT status, error_code FROM processing_jobs WHERE job_type = 'PLAN_DRAFT'",
                {},
            )
        ).one()
        assert job_row[0] == "FAILED"
        assert job_row[1] == PLAN_DRAFT_LLM_UNCONFIGURED
        assert isinstance(await claim_waiting(session_factory, run_id), Ready)
        assert await advance(session_factory, run_id) == "PARTIAL_COMPLETED"


@pytest.mark.anyio
async def test_plan_draft_without_materials_fails_with_stable_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """课程无资料（SUGGESTIONS 路径）：job 落稳定失败码而非静默成功——等待
    步骤翻 FAILED、Run 部分完成，补资料后可单独重试（工单 07 review：指引
    已承诺任务完成产草案卡，此路径不得无产出地报成功）。"""
    from app.modules.learning_plan.schemas import PlanSuggestions

    provider = LlmProviderConfig(
        base_url="https://llm.example.com/v1", api_key="test-key", model="test-model"
    )

    def fake_provider(_data_dir: Path) -> LlmProviderConfig:
        return provider

    monkeypatch.setattr("app.modules.agent.operations.plan_draft.load_llm_provider", fake_provider)

    async def suggestions_generate(**kwargs: Any) -> PlanGenerationOutcome:
        return PlanGenerationOutcome(
            kind="SUGGESTIONS",
            suggestions=PlanSuggestions.model_validate(
                {
                    "suggested_contents": [
                        {"title": "先补充资料", "why": "课程还没有任何学习资料"}
                    ],
                    "material_gaps": [{"what": "基础资料", "why": "生成计划需要资料上下文"}],
                }
            ),
        )

    monkeypatch.setattr(PlanGenerationService, "generate", staticmethod(suggestions_generate))
    async with bare_db(tmp_path) as session_factory:
        planned = await invoke_plan(
            session_factory,
            [
                {
                    "action": "create_course",
                    "name": "空课程",
                    "learning_context": "INTEREST",
                    "depth": "BEGINNER",
                },
                {
                    "action": "create_goal",
                    "course_id": COURSE_REF,
                    "goal_type": "SKILL",
                    "title": "空课程目标",
                },
                {"action": "generate_plan_draft", "goal_id": GOAL_REF},
            ],
        )
        run_id = await confirm_plan_card(
            session_factory, cast(str, planned["plan_proposal"]["proposal_id"])
        )
        assert await advance(session_factory, run_id) == "WAITING_JOB"
        assert await run_draft_worker(session_factory, tmp_path) is True
        job_row = (
            await scalar(
                session_factory,
                "SELECT status, error_code FROM processing_jobs WHERE job_type = 'PLAN_DRAFT'",
                {},
            )
        ).one()
        assert job_row == ("FAILED", "PLAN_DRAFT_NO_MATERIALS")
        assert isinstance(await claim_waiting(session_factory, run_id), Ready)
        assert await advance(session_factory, run_id) == "PARTIAL_COMPLETED"
        # 零草案卡落库（SUGGESTIONS 不建提案）。
        assert (
            await scalar(
                session_factory,
                "SELECT COUNT(*) FROM agent_proposals WHERE proposal_type = 'OP_PLAN_CONFIRM'",
                {},
            )
        ).scalar_one() == 0


@pytest.mark.anyio
async def test_shared_ref_only_course_produces_plan_draft(
    tmp_path: Path, draft_llm: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """仅通过共享引用挂课的资料也进计划草案：gather_materials 可见口径须含
    共享覆盖（与 COURSE 检索同源），否则误报 PLAN_DRAFT_NO_MATERIALS、
    「共享引用→草案」路径断裂（工单承诺两路径之一，07 review 三轮 P1）。
    草案的 STUDY_RECORD 项引用共享记录——生成提示把共享资料连同 record_id
    呈给模型，写回与确认校验须同样接受共享可见口径（07 review 八轮 P1）。"""
    owner_course = "c0000000-0000-4000-8000-0000000000ff"
    shared_record = "a0000000-0000-4000-8000-0000000000f1"
    day = date.today().isoformat()
    async with bare_db(tmp_path) as session_factory:
        # 原课程 + 资料条目 + 归属原课程的 Record（经 library_item_records 关联）。
        await run_sql(
            "INSERT INTO courses (id, name, learning_context, depth, status, created_at,"
            " updated_at) VALUES (:id, '原课程', 'INTEREST', 'BEGINNER', 'ACTIVE', :now, :now)",
            {"id": owner_course, "now": NOW},
            session_factory,
        )
        await run_sql(
            "INSERT INTO library_items (id, course_id, source_type, title, content_hash,"
            " metadata_json, status, created_at, updated_at)"
            " VALUES (:id, :owner, 'TEXT', '共享论文', :hash, '{}', 'ACTIVE', :now, :now)",
            {"id": item_id(9), "owner": owner_course, "hash": "mhash-9", "now": NOW},
            session_factory,
        )
        await run_sql(
            "INSERT INTO records (id, course_id, capture_type, title, status, duration_ms,"
            " created_at, updated_at) VALUES (:id, :owner, 'PASTE', '共享论文正文',"
            " 'SUMMARY_READY', 0, :now, :now)",
            {"id": shared_record, "owner": owner_course, "now": NOW},
            session_factory,
        )
        await run_sql(
            "INSERT INTO library_item_records"
            " (library_item_id, record_id, role, sequence_no, created_at)"
            " VALUES (:item, :record, 'PRIMARY', 0, :now)",
            {"item": item_id(9), "record": shared_record, "now": NOW},
            session_factory,
        )

        # 草案带 STUDY_RECORD 项引用共享记录（record_id=归属原课程的 Record）。
        async def shared_generate(**kwargs: Any) -> PlanGenerationOutcome:
            goal = kwargs["goal"]
            plan = PlanConfirmCore.model_validate(
                {
                    "goal_id": goal.id,
                    "phases": [
                        {
                            "title": "第一阶段",
                            "items": [
                                {
                                    "action_type": "STUDY_RECORD",
                                    "record_id": shared_record,
                                    "content": "精读共享论文",
                                    "estimated_minutes": 30,
                                    "reason": "核心资料",
                                    "scheduled_date": day,
                                }
                            ],
                        }
                    ],
                }
            )
            return PlanGenerationOutcome(kind="DRAFT", plan=plan, total_minutes=30)

        monkeypatch.setattr(PlanGenerationService, "generate", staticmethod(shared_generate))
        planned = await invoke_plan(
            session_factory,
            [
                {
                    "action": "create_course",
                    "name": "共享课",
                    "learning_context": "INTEREST",
                    "depth": "BEGINNER",
                },
                {
                    "action": "create_goal",
                    "course_id": COURSE_REF,
                    "goal_type": "SKILL",
                    "title": "吃透共享资料",
                },
                {
                    "action": "add_shared_ref",
                    "library_item_id": item_id(9),
                    "course_id": COURSE_REF,
                },
                {"action": "generate_plan_draft", "goal_id": GOAL_REF},
            ],
        )
        run_id = await confirm_plan_card(
            session_factory, cast(str, planned["plan_proposal"]["proposal_id"])
        )
        # 前三步瞬时完成（新课程无归属记录），末步提交 PLAN_DRAFT job 后等待。
        assert await advance(session_factory, run_id) == "WAITING_JOB"
        assert await run_draft_worker(session_factory, tmp_path) is True
        job_row = (
            await scalar(
                session_factory,
                "SELECT status, error_code FROM processing_jobs WHERE job_type = 'PLAN_DRAFT'",
                {},
            )
        ).one()
        assert job_row == ("SUCCEEDED", None)
        assert isinstance(await claim_waiting(session_factory, run_id), Ready)
        assert await advance(session_factory, run_id) == "COMPLETED"
        # 草案确认卡落库（非无资料失败）。
        assert (
            await scalar(
                session_factory,
                "SELECT COUNT(*) FROM agent_proposals WHERE proposal_type = 'OP_PLAN_CONFIRM'",
                {},
            )
        ).scalar_one() == 1


# ---------------------------------------------------------------------------
# 重规划升回确认（固定计划集合）


@pytest.mark.anyio
async def test_replanning_during_wait_escalates_to_card(tmp_path: Path) -> None:
    """执行中（等待资料解析）重规划新增目标升回确认——完全访问档亦然：
    等待态 Run 只接受显式唤醒，经工具追加也转计划卡。"""
    async with bare_db(tmp_path) as session_factory:
        direct = await invoke_plan(
            session_factory,
            [
                {
                    "action": "create_course",
                    "name": "原计划课",
                    "learning_context": "INTEREST",
                    "depth": "BEGINNER",
                },
                {"action": "ingest_library_item", "url": URL, "course_id": COURSE_REF},
            ],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        run_id = cast(str, direct["run"]["run_id"])
        assert await advance(session_factory, run_id) == "WAITING_JOB"

        # 追加批次的引用只指本批（跨批引用不支持，模型应改用已建课程具体 id）。
        course_id = cast(
            str,
            (
                await scalar(session_factory, "SELECT id FROM courses WHERE name = '原计划课'", {})
            ).scalar_one(),
        )
        appended = await invoke_plan(
            session_factory,
            [
                {
                    "action": "add_text_record_to_course",
                    "content": "追加的粘贴文本",
                    "course_id": course_id,
                }
            ],
            auth_mode=AuthMode.FULL_ACCESS,
        )
        assert "plan_proposal" in appended
        assert "run" not in appended


# ---------------------------------------------------------------------------
# 计划卡授权语义（L2 末步经一次批准在 Run 内执行）


@pytest.mark.anyio
async def test_batch_authorization_covers_l2_draft_step(tmp_path: Path) -> None:
    """L2 动作（generate_plan_draft）在 AUTO_APPROVE 档不能直执行（出计划卡），
    但经计划卡一次批准后即为已批准集合成员，Run 内照常执行（授权 = 计划
    版本 + 固定对象集合 + 参数）。"""
    async with bare_db(tmp_path) as session_factory:
        auto = await invoke_plan(
            session_factory,
            [
                {
                    "action": "create_course",
                    "name": "自动档课",
                    "learning_context": "INTEREST",
                    "depth": "BEGINNER",
                },
                {
                    "action": "create_goal",
                    "course_id": COURSE_REF,
                    "goal_type": "SKILL",
                    "title": "自动档目标",
                },
                {"action": "generate_plan_draft", "goal_id": GOAL_REF},
            ],
            auth_mode=AuthMode.AUTO_APPROVE,
        )
        # 含 L2 末步：帮我批准档不自动执行，出计划卡。
        assert "plan_proposal" in auto
        run_id = await confirm_plan_card(
            session_factory, cast(str, auto["plan_proposal"]["proposal_id"])
        )
        assert await advance(session_factory, run_id) == "WAITING_JOB"
        steps = await step_rows(session_factory, run_id)
        assert steps[-1][0] == "generate_plan_draft"
        assert steps[-1][1] == "SUCCEEDED"
        assert (await run_row(session_factory, run_id))[1] == "AGENT_RUN_WAITING_JOB_PENDING"
