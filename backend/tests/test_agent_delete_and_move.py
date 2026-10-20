"""通用 Agent 第二阶段工单 04：删除与跨课迁移。

- soft_delete_record（L3）：影响快照＝记录级资产计数；确认应用复用记录软删
  领域核心（级联软删 + 取消任务 + 掌握度重算挂钩）；预览后资产新增 →
  快照失效不覆盖；任何档位逐项确认（AUTO_APPROVE 恒落提案、FULL_ACCESS
  直执行）。
- delete_course（L3）：影响快照＝记录清单与计数；Q8 场景＝批准后新增记录 →
  确认失效、新记录不被悄悄删除；确认应用经课程删除领域应用函数（级联 +
  重算一体编排，与 HTTP 路由共用，既有 test_courses 删除测试零改动通过）。
- move_record_course（L2）：快照存原 course_id；迁移改 course_id + 维护
  updated_at + 重建索引；目标课程 ARCHIVED / 同课程 / 进行中任务结构化拒绝；
  迁移语义＝quiz 存量绑定、quiz_test_items、learning_events / evidence、
  record_concepts 行零触碰（历史归属保留），新概念绑定按目标课程校验。

updated_at 纪律防线（spec 决策 12）融进各用例：seed 钉死过去固定时刻。
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import create_database
from app.db.migrations import run_migrations
from app.modules.agent.runs.schemas import AuthMode
from app.modules.agent.runtime import (
    AgentRuntimeContext,
    ToolCallBudget,
    bind_agent_runtime_context,
    reset_agent_runtime_context,
)
from app.modules.agent.tools.delete_course import delete_course
from app.modules.agent.tools.move_record_course import move_record_course
from app.modules.agent.tools.soft_delete_record import soft_delete_record
from app.modules.library.proposals import ProposalService
from app.modules.quiz.schemas import QuizConceptUpdateRequest
from app.modules.quiz.service import QuizService
from app.modules.record.service import RecordService
from app.shared.errors import CodedHTTPException

NOW = "2026-09-21T08:00:00.000000Z"
COURSE_ID = "c0000000-0000-4000-8000-000000000001"
TARGET_COURSE = "c0000000-0000-4000-8000-000000000002"
RECORD_ID = "d0000000-0000-4000-8000-00000000000d"
RECORD_OTHER = "d0000000-0000-4000-8000-00000000000e"
QUIZ_ID = "q0000000-0000-4000-8000-00000000000q"
KP_ID = "k0000000-0000-4000-8000-00000000000k"
CONCEPT_ID = "b0000000-0000-4000-8000-00000000000b"
CONCEPT_TARGET = "b0000000-0000-4000-8000-00000000000c"
UNKNOWN_ID = "c0000000-0000-4000-8000-00000000dead"


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


async def seed_course(
    session_factory: async_sessionmaker[AsyncSession],
    course_id: str = COURSE_ID,
    *,
    status: str = "ACTIVE",
) -> None:
    await run_sql(
        "INSERT INTO courses (id, name, learning_context, depth, status, created_at, "
        "updated_at) VALUES (:id, :name, 'INTEREST', 'INTERMEDIATE', :status, :now, :now)",
        {"id": course_id, "name": f"课程-{course_id[-1]}", "status": status, "now": NOW},
        session_factory,
    )


async def seed_record(
    session_factory: async_sessionmaker[AsyncSession],
    record_id: str = RECORD_ID,
    *,
    course_id: str | None = COURSE_ID,
    title: str = "第 1 讲 一致性哈希",
) -> None:
    await run_sql(
        "INSERT INTO records (id, course_id, capture_type, title, status, duration_ms, "
        "created_at, updated_at) "
        "VALUES (:id, :course_id, 'PASTE', :title, 'COMPLETED', 0, :now, :now)",
        {"id": record_id, "course_id": course_id, "title": title, "now": NOW},
        session_factory,
    )


async def seed_kp(
    session_factory: async_sessionmaker[AsyncSession],
    kp_id: str = KP_ID,
    *,
    record_id: str = RECORD_ID,
) -> None:
    await run_sql(
        "INSERT INTO knowledge_points (id, record_id, name, detail, tags, importance, "
        "generation_status, created_at, updated_at) "
        "VALUES (:id, :record_id, '一致性哈希', '…', '[]', 3.0, 'ACTIVE', :now, :now)",
        {"id": kp_id, "record_id": record_id, "now": NOW},
        session_factory,
    )


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
            session_id="sess-delete-move",
            auth_mode=auth_mode,
            budget=ToolCallBudget(),
        )
    )
    try:
        raw = await tool.ainvoke(args)
        return dict(json.loads(raw))
    finally:
        reset_agent_runtime_context(token)


async def scalar(session_factory: async_sessionmaker[AsyncSession], sql: str) -> Any:
    async with session_factory() as session:
        return (await session.execute(text(sql))).scalar_one()


async def scalar_or_none(session_factory: async_sessionmaker[AsyncSession], sql: str) -> Any:
    async with session_factory() as session:
        return (await session.execute(text(sql))).scalar_one_or_none()


async def rows_of(
    session_factory: async_sessionmaker[AsyncSession], sql: str
) -> list[tuple[Any, ...]]:
    async with session_factory() as session:
        return [tuple(row) for row in (await session.execute(text(sql))).all()]


async def proposal_row(
    session_factory: async_sessionmaker[AsyncSession], proposal_id: str
) -> tuple[str, str | None, dict[str, Any] | None]:
    """提案行 (status, error_code, snapshot)。"""
    snapshot_raw = await scalar_or_none(
        session_factory,
        f"SELECT snapshot_json FROM agent_proposals WHERE id = '{proposal_id}'",
    )
    status = await scalar(
        session_factory,
        f"SELECT status FROM agent_proposals WHERE id = '{proposal_id}'",
    )
    error_code = await scalar_or_none(
        session_factory,
        f"SELECT error_code FROM agent_proposals WHERE id = '{proposal_id}'",
    )
    snapshot = None
    if snapshot_raw is not None:
        value: object = json.loads(cast(str, snapshot_raw))
        snapshot = cast(dict[str, Any], value)
    return (cast(str, status), cast(str | None, error_code), snapshot)


async def operation_row(
    session_factory: async_sessionmaker[AsyncSession], proposal_id: str
) -> dict[str, Any] | None:
    async with session_factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT action, level, status, snapshot_json, result_json, "
                    "authorization_json, target_type, target_id FROM agent_operations"
                    " WHERE proposal_id = :id"
                ),
                {"id": proposal_id},
            )
        ).first()
    if row is None:
        return None
    return {
        "action": row[0],
        "level": row[1],
        "status": row[2],
        "snapshot": json.loads(row[3]) if row[3] else None,
        "result": json.loads(row[4]) if row[4] else None,
        "authorization": json.loads(row[5]) if row[5] else None,
        "target_type": row[6],
        "target_id": row[7],
    }


async def drain_background_tasks() -> None:
    """等 after_commit 调度的重算任务跑完（aiosqlite 线程往返，sleep(0) 不够）。"""
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        await asyncio.wait(pending, timeout=5.0)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# record.soft_delete：影响快照与级联应用
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_soft_delete_record_freezes_asset_counts_snapshot(tmp_path: Path) -> None:
    """提交时固化资产计数影响快照；PENDING 期间零业务事实。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_record(session_factory)
        await seed_kp(session_factory)
        await run_sql(
            "INSERT INTO quizzes (id, record_id, generation_status, question_type, stem, "
            "options_json, correct_answer_json, explanation, difficulty, created_at, "
            "updated_at) VALUES (:id, :record_id, 'ACTIVE', 'MULTIPLE_CHOICE', '题干', '[]', "
            "'\"A\"', '解析', 'MEDIUM', :now, :now)",
            {"id": QUIZ_ID, "record_id": RECORD_ID, "now": NOW},
            session_factory,
        )
        payload = await invoke_tool(soft_delete_record, session_factory, {"record_id": RECORD_ID})
        assert payload["ok"] is True
        proposal = payload["proposals"][0]
        assert proposal["action"] == "soft_delete_record"
        # 创建不改业务事实：记录仍在。
        assert (
            await scalar(
                session_factory,
                f"SELECT deleted_at FROM records WHERE id = '{RECORD_ID}'",
            )
            is None
        )
        status, error_code, snapshot = await proposal_row(session_factory, proposal["proposal_id"])
        assert (status, error_code) == ("PENDING", None)
        assert snapshot is not None
        assert snapshot["title"] == "第 1 讲 一致性哈希"
        assert snapshot["knowledge_point_count"] == 1
        assert snapshot["quiz_count"] == 1
        assert snapshot["todo_count"] == 0
        assert snapshot["review_material_count"] == 0
        assert snapshot["has_summary"] is False


@pytest.mark.anyio
async def test_soft_delete_record_confirm_cascades_and_recomputes_mastery(
    tmp_path: Path,
) -> None:
    """确认应用：记录与记录级资产级联软删、进行中任务取消、updated_at 前进、
    operation 行携带快照与回执；掌握度重算经 after_commit 提交后执行。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_record(session_factory)
        await run_sql(
            "INSERT INTO todo_items (id, record_id, content, status, source, "
            "sort_order, created_at, updated_at) "
            "VALUES ('t0000000-0000-4000-8000-00000000000t', :record_id, '复习', "
            "'TODO', 'MANUAL', 0, :now, :now)",
            {"record_id": RECORD_ID, "now": NOW},
            session_factory,
        )
        await run_sql(
            "INSERT INTO processing_jobs (id, record_id, job_type, status, progress, "
            "attempts, max_attempts, input_json, created_at, updated_at) "
            "VALUES ('j0000000-0000-4000-8000-00000000000j', "
            ":record_id, 'SUMMARY', 'RUNNING', 0.0, 0, 3, '{}', :now, :now)",
            {"record_id": RECORD_ID, "now": NOW},
            session_factory,
        )
        # 受影响概念（learning_events）：删除后应触发重算写快照。
        await run_sql(
            "INSERT INTO concepts (id, course_id, canonical_name, normalized_name, status, "
            "created_at, updated_at) VALUES (:id, :course_id, '哈希', '哈希', 'CONFIRMED', "
            ":now, :now)",
            {"id": CONCEPT_ID, "course_id": COURSE_ID, "now": NOW},
            session_factory,
        )
        await run_sql(
            "INSERT INTO learning_events (id, course_id, record_id, concept_id, event_type, "
            "source_type, source_id, metadata_json, idempotency_key, schema_version, "
            "occurred_at, created_at) VALUES ('e0000000-0000-4000-8000-00000000000e', "
            ":course_id, :record_id, :concept_id, 'QUIZ_ANSWERED', 'QUIZ', :quiz_id, '{}', "
            "'idem-1', 1, :now, :now)",
            {
                "course_id": COURSE_ID,
                "record_id": RECORD_ID,
                "concept_id": CONCEPT_ID,
                "quiz_id": QUIZ_ID,
                "now": NOW,
            },
            session_factory,
        )
        payload = await invoke_tool(soft_delete_record, session_factory, {"record_id": RECORD_ID})
        proposal_id = payload["proposals"][0]["proposal_id"]
        async with session_factory() as session:
            confirmed = await ProposalService.confirm(session, proposal_id)
        await drain_background_tasks()

        assert confirmed.status.value == "APPLIED"
        # 记录与 Todo 级联软删、任务取消。
        deleted_at, updated_at = (
            await rows_of(
                session_factory,
                f"SELECT deleted_at, updated_at FROM records WHERE id = '{RECORD_ID}'",
            )
        )[0]
        assert deleted_at is not None
        # updated_at 纪律：写路径必须维护（seed 钉死过去时刻）。
        assert str(updated_at) != NOW
        assert (
            await scalar(
                session_factory,
                "SELECT deleted_at FROM todo_items"
                " WHERE id = 't0000000-0000-4000-8000-00000000000t'",
            )
            is not None
        )
        assert (
            await scalar(
                session_factory,
                "SELECT status FROM processing_jobs"
                " WHERE id = 'j0000000-0000-4000-8000-00000000000j'",
            )
            == "CANCELLED"
        )
        # 掌握度重算已跑（快照行生成，algorithm_version 非 stale 哨兵）。
        algorithm_version = await scalar(
            session_factory,
            f"SELECT algorithm_version FROM user_concept_mastery WHERE concept_id = '{CONCEPT_ID}'",
        )
        assert algorithm_version is not None
        assert algorithm_version != "stale"
        # operation 行：快照 + 回执 + 目标定位。
        operation = await operation_row(session_factory, proposal_id)
        assert operation is not None
        assert operation["action"] == "soft_delete_record"
        assert operation["level"] == "L3"
        assert operation["status"] == "SUCCEEDED"
        assert operation["snapshot"]["knowledge_point_count"] == 0
        assert operation["result"]["record_id"] == RECORD_ID
        assert (operation["target_type"], operation["target_id"]) == ("record", RECORD_ID)


@pytest.mark.anyio
async def test_soft_delete_record_stale_when_asset_added_after_preview(
    tmp_path: Path,
) -> None:
    """预览后确认了新知识点（资产新增＝实质差异）：确认失效，资产不被删。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_record(session_factory)
        payload = await invoke_tool(soft_delete_record, session_factory, {"record_id": RECORD_ID})
        proposal_id = payload["proposals"][0]["proposal_id"]
        # 预览后用户新增知识点。
        await seed_kp(session_factory)
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc_info:
                await ProposalService.confirm(session, proposal_id)
        assert exc_info.value.params == {"errorCode": "OPERATION_SNAPSHOT_STALE"}
        status, error_code, _ = await proposal_row(session_factory, proposal_id)
        assert (status, error_code) == ("FAILED", "OPERATION_SNAPSHOT_STALE")
        # 新资产与记录不被删除、operation 不落（未发生）。
        assert (
            await scalar(
                session_factory, f"SELECT deleted_at FROM records WHERE id = '{RECORD_ID}'"
            )
            is None
        )
        assert (
            await scalar(
                session_factory, f"SELECT deleted_at FROM knowledge_points WHERE id = '{KP_ID}'"
            )
            is None
        )
        assert await operation_row(session_factory, proposal_id) is None


@pytest.mark.anyio
async def test_soft_delete_record_target_missing_rejected_without_proposal(
    tmp_path: Path,
) -> None:
    """目标不存在：结构化拒绝、零提案。"""
    async with bare_db(tmp_path) as session_factory:
        payload = await invoke_tool(soft_delete_record, session_factory, {"record_id": UNKNOWN_ID})
        assert payload["ok"] is False
        assert payload["error"] == "RECORD_NOT_FOUND"
        assert payload["proposals"] == []


# ---------------------------------------------------------------------------
# delete_course：影响清单快照与 Q8 场景
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_delete_course_freezes_record_list_snapshot(tmp_path: Path) -> None:
    """提交时固化级联影响清单（记录 id+标题、计数）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_record(session_factory, RECORD_ID)
        await seed_record(session_factory, RECORD_OTHER, title="第 2 讲 布隆过滤器")
        payload = await invoke_tool(delete_course, session_factory, {"course_id": COURSE_ID})
        assert payload["ok"] is True
        proposal = payload["proposals"][0]
        assert proposal["action"] == "delete_course"
        _, _, snapshot = await proposal_row(session_factory, proposal["proposal_id"])
        assert snapshot is not None
        assert snapshot["record_count"] == 2
        assert snapshot["records"] == sorted(
            snapshot["records"], key=lambda item: item["record_id"]
        )
        assert {item["record_id"] for item in snapshot["records"]} == {
            RECORD_ID,
            RECORD_OTHER,
        }


@pytest.mark.anyio
async def test_delete_course_stale_when_record_added_after_approval(
    tmp_path: Path,
) -> None:
    """Q8 场景（spec 用户故事 15）：批准后、执行前向课程新增记录 → 旧批准失效
    （OPERATION_SNAPSHOT_STALE），新增记录不被悄悄纳入删除。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_record(session_factory, RECORD_ID)
        payload = await invoke_tool(delete_course, session_factory, {"course_id": COURSE_ID})
        proposal_id = payload["proposals"][0]["proposal_id"]
        # 批准后、执行前：向课程新增一条记录（影响清单实质差异）。
        await seed_record(session_factory, RECORD_OTHER, title="批准后新增")
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc_info:
                await ProposalService.confirm(session, proposal_id)
        assert exc_info.value.params == {"errorCode": "OPERATION_SNAPSHOT_STALE"}
        status, error_code, _ = await proposal_row(session_factory, proposal_id)
        assert (status, error_code) == ("FAILED", "OPERATION_SNAPSHOT_STALE")
        # 新增记录与课程都不被删除。
        assert (
            await scalar(
                session_factory,
                f"SELECT deleted_at FROM records WHERE id = '{RECORD_OTHER}'",
            )
            is None
        )
        assert (
            await scalar(
                session_factory, f"SELECT deleted_at FROM courses WHERE id = '{COURSE_ID}'"
            )
            is None
        )


@pytest.mark.anyio
async def test_delete_course_confirm_cascades_and_returns_record_count(
    tmp_path: Path,
) -> None:
    """确认应用：课程与记录级联软删、updated_at 前进、operation 行带计数回执。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_record(session_factory, RECORD_ID)
        payload = await invoke_tool(delete_course, session_factory, {"course_id": COURSE_ID})
        proposal_id = payload["proposals"][0]["proposal_id"]
        async with session_factory() as session:
            confirmed = await ProposalService.confirm(session, proposal_id)
        await drain_background_tasks()
        assert confirmed.status.value == "APPLIED"
        course_deleted_at, course_updated_at = (
            await rows_of(
                session_factory,
                f"SELECT deleted_at, updated_at FROM courses WHERE id = '{COURSE_ID}'",
            )
        )[0]
        assert course_deleted_at is not None
        # updated_at 纪律：课程与级联记录写路径都维护 updated_at（seed 钉死过去时刻）。
        assert str(course_updated_at) != NOW
        record_deleted_at, record_updated_at = (
            await rows_of(
                session_factory,
                f"SELECT deleted_at, updated_at FROM records WHERE id = '{RECORD_ID}'",
            )
        )[0]
        assert record_deleted_at is not None
        assert str(record_updated_at) != NOW
        operation = await operation_row(session_factory, proposal_id)
        assert operation is not None
        assert operation["action"] == "delete_course"
        assert operation["level"] == "L3"
        assert operation["result"] == {"course_id": COURSE_ID, "record_count": 1}
        assert (operation["target_type"], operation["target_id"]) == ("course", COURSE_ID)


# ---------------------------------------------------------------------------
# move_record_course：快照、校验与迁移语义
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_move_record_freezes_original_course_and_moves_on_confirm(
    tmp_path: Path,
) -> None:
    """快照存原 course_id（06 票 Undo 补偿数据）；确认后 course_id 变化、
    updated_at 前进、搜索索引重建（全局搜索可命中迁移后记录）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_course(session_factory, TARGET_COURSE)
        await seed_record(session_factory)
        payload = await invoke_tool(
            move_record_course,
            session_factory,
            {"record_id": RECORD_ID, "target_course_id": TARGET_COURSE},
        )
        assert payload["ok"] is True
        proposal = payload["proposals"][0]
        assert proposal["action"] == "move_record_course"
        _, _, snapshot = await proposal_row(session_factory, proposal["proposal_id"])
        assert snapshot is not None
        assert snapshot["course_id"] == COURSE_ID
        # PENDING 期间零业务事实。
        assert (
            await scalar(session_factory, f"SELECT course_id FROM records WHERE id = '{RECORD_ID}'")
            == COURSE_ID
        )

        async with session_factory() as session:
            confirmed = await ProposalService.confirm(session, proposal["proposal_id"])
        assert confirmed.status.value == "APPLIED"
        course_id, updated_at = (
            await rows_of(
                session_factory,
                f"SELECT course_id, updated_at FROM records WHERE id = '{RECORD_ID}'",
            )
        )[0]
        assert course_id == TARGET_COURSE
        assert str(updated_at) != NOW
        # 搜索索引行存在（重建路径幂等可达；索引不含 course 维度）。
        assert (
            await scalar(
                session_factory,
                "SELECT COUNT(*) FROM search_index WHERE entity_type = 'record'"
                f" AND entity_id = '{RECORD_ID}'",
            )
            == 1
        )
        operation = await operation_row(session_factory, proposal["proposal_id"])
        assert operation is not None
        assert operation["level"] == "L2"
        result = operation["result"]
        assert result["record_id"] == RECORD_ID
        assert result["before_course_id"] == COURSE_ID
        assert result["after_course_id"] == TARGET_COURSE
        # 执行后版本戳（undo 版本重验用）随 result 固化。
        assert result["after_updated_at"] is not None


@pytest.mark.anyio
async def test_move_record_rejections(tmp_path: Path) -> None:
    """目标归档（COURSE_ARCHIVED）、同课程（RECORD_ALREADY_IN_COURSE）、
    进行中任务（RECORD_MOVE_JOB_IN_PROGRESS）：提案 FAILED 可重试；任务终态
    后同提案再次确认成功（FAILED 可重确认先例）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_course(session_factory, TARGET_COURSE)
        await seed_record(session_factory)
        await run_sql(
            "INSERT INTO processing_jobs (id, record_id, job_type, status, progress, "
            "attempts, max_attempts, input_json, created_at, updated_at) "
            "VALUES ('j0000000-0000-4000-8000-00000000000j', "
            ":record_id, 'SUMMARY', 'RUNNING', 0.0, 0, 3, '{}', :now, :now)",
            {"record_id": RECORD_ID, "now": NOW},
            session_factory,
        )
        payload = await invoke_tool(
            move_record_course,
            session_factory,
            {"record_id": RECORD_ID, "target_course_id": TARGET_COURSE},
        )
        proposal_id = payload["proposals"][0]["proposal_id"]
        # 进行中任务 → 拒绝（提示等待处理完成）。
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc_info:
                await ProposalService.confirm(session, proposal_id)
        assert exc_info.value.params == {"errorCode": "RECORD_MOVE_JOB_IN_PROGRESS"}
        status, error_code, _ = await proposal_row(session_factory, proposal_id)
        assert (status, error_code) == ("FAILED", "RECORD_MOVE_JOB_IN_PROGRESS")
        assert (
            await scalar(session_factory, f"SELECT course_id FROM records WHERE id = '{RECORD_ID}'")
            == COURSE_ID
        )

        # 任务终态后：同一 FAILED 提案再次确认成功（可重试）。
        await run_sql(
            "UPDATE processing_jobs SET status = 'SUCCEEDED' "
            "WHERE id = 'j0000000-0000-4000-8000-00000000000j'",
            {},
            session_factory,
        )
        async with session_factory() as session:
            confirmed = await ProposalService.confirm(session, proposal_id)
        assert confirmed.status.value == "APPLIED"
        assert (
            await scalar(session_factory, f"SELECT course_id FROM records WHERE id = '{RECORD_ID}'")
            == TARGET_COURSE
        )

        # 同课程 → 提交后确认被拒（RECORD_ALREADY_IN_COURSE）。
        payload = await invoke_tool(
            move_record_course,
            session_factory,
            {"record_id": RECORD_ID, "target_course_id": TARGET_COURSE},
        )
        same_id = payload["proposals"][0]["proposal_id"]
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc_info:
                await ProposalService.confirm(session, same_id)
        assert exc_info.value.params == {"errorCode": "RECORD_ALREADY_IN_COURSE"}

        # 目标归档 → COURSE_ARCHIVED。
        await run_sql(
            f"UPDATE courses SET status = 'ARCHIVED' WHERE id = '{COURSE_ID}'",
            {},
            session_factory,
        )
        payload = await invoke_tool(
            move_record_course,
            session_factory,
            {"record_id": RECORD_ID, "target_course_id": COURSE_ID},
        )
        archived_id = payload["proposals"][0]["proposal_id"]
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc_info:
                await ProposalService.confirm(session, archived_id)
        assert exc_info.value.params == {"errorCode": "COURSE_ARCHIVED"}


@pytest.mark.anyio
async def test_move_record_preserves_history_attribution(tmp_path: Path) -> None:
    """迁移语义（spec 决策 18）：quiz 存量 concept_id 绑定、quiz_test_items、
    learning_events / learning_evidence（course_id 固化＝历史归属）、
    record_concepts、quiz_tests 行零触碰；知识点行不动（挂 record_id 天然随走）；
    习题主概念新绑定按目标课程校验（同课程 CONFIRMED 才可绑定）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_course(session_factory, TARGET_COURSE)
        await seed_record(session_factory)
        await seed_kp(session_factory)
        # 原课程概念（习题存量绑定）与目标课程概念（新绑定用）。
        await run_sql(
            "INSERT INTO concepts (id, course_id, canonical_name, normalized_name, status, "
            "created_at, updated_at) VALUES (:id, :course_id, :name, :name, 'CONFIRMED', "
            ":now, :now)",
            {"id": CONCEPT_ID, "course_id": COURSE_ID, "name": "一致性哈希", "now": NOW},
            session_factory,
        )
        await run_sql(
            "INSERT INTO concepts (id, course_id, canonical_name, normalized_name, status, "
            "created_at, updated_at) VALUES (:id, :course_id, :name, :name, 'CONFIRMED', "
            ":now, :now)",
            {"id": CONCEPT_TARGET, "course_id": TARGET_COURSE, "name": "目标概念", "now": NOW},
            session_factory,
        )
        await run_sql(
            "INSERT INTO quizzes (id, record_id, concept_id, generation_status, "
            "question_type, stem, options_json, correct_answer_json, explanation, "
            "difficulty, created_at, updated_at) VALUES (:id, :record_id, :concept_id, "
            "'ACTIVE', 'MULTIPLE_CHOICE', '题干', '[]', '\"A\"', '解析', 'MEDIUM', :now, :now)",
            {"id": QUIZ_ID, "record_id": RECORD_ID, "concept_id": CONCEPT_ID, "now": NOW},
            session_factory,
        )
        # 旧课程历史测试（quiz_tests 只按 course_id 归属）与其试卷题位
        # （题位未作答：主概念可改，供迁移后新绑定校验断言）。
        await run_sql(
            "INSERT INTO quiz_tests (id, course_id, mode, status, score, started_at, "
            "completed_at, created_at, updated_at) VALUES ('s0000000-0000-4000-8000-00000000000s', "
            ":course_id, 'MOCK', 'COMPLETED', 0.8, :now, :now, :now, :now)",
            {"course_id": COURSE_ID, "now": NOW},
            session_factory,
        )
        await run_sql(
            "INSERT INTO quiz_test_items (id, test_id, quiz_id, sequence_no, created_at, "
            "updated_at) VALUES ('i0000000-0000-4000-8000-00000000000i', "
            "'s0000000-0000-4000-8000-00000000000s', :quiz_id, 1, :now, :now)",
            {"quiz_id": QUIZ_ID, "now": NOW},
            session_factory,
        )
        await run_sql(
            "INSERT INTO learning_events (id, course_id, record_id, concept_id, event_type, "
            "source_type, source_id, metadata_json, idempotency_key, schema_version, "
            "occurred_at, created_at) VALUES ('e0000000-0000-4000-8000-00000000000e', "
            ":course_id, :record_id, :concept_id, 'QUIZ_ANSWERED', 'QUIZ', :quiz_id, '{}', "
            "'idem-1', 1, :now, :now)",
            {
                "course_id": COURSE_ID,
                "record_id": RECORD_ID,
                "concept_id": CONCEPT_ID,
                "quiz_id": QUIZ_ID,
                "now": NOW,
            },
            session_factory,
        )
        await run_sql(
            "INSERT INTO learning_evidence (id, course_id, concept_id, event_id, "
            "evidence_type, weight, confidence, metadata_json, occurred_at, created_at) "
            "VALUES ('v0000000-0000-4000-8000-00000000000v', :course_id, :concept_id, "
            "'e0000000-0000-4000-8000-00000000000e', 'QUIZ', 1.0, 1.0, '{}', :now, :now)",
            {"course_id": COURSE_ID, "concept_id": CONCEPT_ID, "now": NOW},
            session_factory,
        )
        await run_sql(
            "INSERT INTO record_concepts (id, record_id, concept_id, knowledge_point_id, "
            "relevance, evidence_count, created_at, updated_at) VALUES "
            "('m0000000-0000-4000-8000-00000000000m', :record_id, :concept_id, :kp_id, "
            "0.9, 1, :now, :now)",
            {"record_id": RECORD_ID, "concept_id": CONCEPT_ID, "kp_id": KP_ID, "now": NOW},
            session_factory,
        )
        # 记录级资产齐种（总结 / Todo / 复习资料）：随记录天然随走的断言面。
        await run_sql(
            "INSERT INTO ai_summaries (id, record_id, version_no, transcript_source_version, "
            "topic, abstract, summary_json, status, model, prompt_version, token_usage_json, "
            "latency_ms, confirmed_at, created_at, updated_at) VALUES "
            "('f0000000-0000-4000-8000-00000000000f', :record_id, 1, 1, '主题', '摘要', '{}', "
            "'CONFIRMED', 'test-model', 'v1', '{}', 10, :now, :now, :now)",
            {"record_id": RECORD_ID, "now": NOW},
            session_factory,
        )
        await run_sql(
            "INSERT INTO todo_items (id, record_id, content, status, source, sort_order, "
            "created_at, updated_at) VALUES ('t0000000-0000-4000-8000-00000000000t', "
            ":record_id, '复习一致性哈希', 'TODO', 'MANUAL', 0, :now, :now)",
            {"record_id": RECORD_ID, "now": NOW},
            session_factory,
        )
        await run_sql(
            "INSERT INTO review_materials (id, record_id, version_no, transcript_source_version, "
            "generated_from_summary_id, quick_review, key_list_json, mind_map_markdown, status, "
            "model, prompt_version, token_usage_json, latency_ms, created_at, updated_at) "
            "VALUES ('w0000000-0000-4000-8000-00000000000w', :record_id, 1, 1, "
            "'f0000000-0000-4000-8000-00000000000f', '速览', '[]', '# 图', 'CONFIRMED', "
            "'test-model', 'v1', '{}', 10, :now, :now)",
            {"record_id": RECORD_ID, "now": NOW},
            session_factory,
        )

        payload = await invoke_tool(
            move_record_course,
            session_factory,
            {"record_id": RECORD_ID, "target_course_id": TARGET_COURSE},
        )
        proposal_id = payload["proposals"][0]["proposal_id"]
        async with session_factory() as session:
            confirmed = await ProposalService.confirm(session, proposal_id)
        assert confirmed.status.value == "APPLIED"
        assert (
            await scalar(session_factory, f"SELECT course_id FROM records WHERE id = '{RECORD_ID}'")
            == TARGET_COURSE
        )
        # 读取路径：记录可见于目标课程、退出原课程课程列表。
        async with session_factory() as session:
            target_records = await RecordService.list_for_course(session, TARGET_COURSE)
            source_records = await RecordService.list_for_course(session, COURSE_ID)
        assert target_records is not None and source_records is not None
        assert [record.id for record in target_records] == [RECORD_ID]
        assert [record.id for record in source_records] == []

        # 不触碰清单：行级零变化（迁移前后同值）。
        assert await rows_of(
            session_factory,
            f"SELECT concept_id, deleted_at FROM quizzes WHERE id = '{QUIZ_ID}'",
        ) == [(CONCEPT_ID, None)]
        assert await rows_of(
            session_factory,
            "SELECT course_id, deleted_at FROM quiz_tests"
            " WHERE id = 's0000000-0000-4000-8000-00000000000s'",
        ) == [(COURSE_ID, None)]
        assert await rows_of(
            session_factory,
            "SELECT quiz_id, answered_at FROM quiz_test_items"
            " WHERE id = 'i0000000-0000-4000-8000-00000000000i'",
        ) == [(QUIZ_ID, None)]
        assert await rows_of(
            session_factory,
            "SELECT course_id, concept_id FROM learning_events"
            " WHERE id = 'e0000000-0000-4000-8000-00000000000e'",
        ) == [(COURSE_ID, CONCEPT_ID)]
        assert await rows_of(
            session_factory,
            "SELECT course_id, concept_id FROM learning_evidence"
            " WHERE id = 'v0000000-0000-4000-8000-00000000000v'",
        ) == [(COURSE_ID, CONCEPT_ID)]
        assert await rows_of(
            session_factory,
            "SELECT concept_id FROM record_concepts"
            " WHERE id = 'm0000000-0000-4000-8000-00000000000m'",
        ) == [(CONCEPT_ID,)]
        # 知识点随记录可见于目标课程（行不动，挂 record_id）。
        assert await rows_of(
            session_factory,
            f"SELECT record_id, deleted_at FROM knowledge_points WHERE id = '{KP_ID}'",
        ) == [(RECORD_ID, None)]
        # 总结 / Todo / 复习资产行零触碰（挂 record_id 天然随记录走）。
        assert await rows_of(
            session_factory,
            "SELECT record_id, deleted_at FROM ai_summaries"
            " WHERE id = 'f0000000-0000-4000-8000-00000000000f'",
        ) == [(RECORD_ID, None)]
        assert await rows_of(
            session_factory,
            "SELECT record_id, deleted_at FROM todo_items"
            " WHERE id = 't0000000-0000-4000-8000-00000000000t'",
        ) == [(RECORD_ID, None)]
        assert await rows_of(
            session_factory,
            "SELECT record_id, deleted_at FROM review_materials"
            " WHERE id = 'w0000000-0000-4000-8000-00000000000w'",
        ) == [(RECORD_ID, None)]

        # 习题主概念「同课程 CONFIRMED」校验只管新绑定：目标课程概念可绑、
        # 原课程概念拒绝（QUIZ_CONCEPT_INVALID），存量绑定不回溯。
        async with session_factory() as session:
            rebound = await QuizService.set_concept(
                session,
                RECORD_ID,
                QUIZ_ID,
                QuizConceptUpdateRequest(concept_id=CONCEPT_TARGET),
            )
        assert rebound.concept_id == CONCEPT_TARGET
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc_info:
                await QuizService.set_concept(
                    session,
                    RECORD_ID,
                    QUIZ_ID,
                    QuizConceptUpdateRequest(concept_id=CONCEPT_ID),
                )
        assert exc_info.value.code == "QUIZ_CONCEPT_INVALID"


# ---------------------------------------------------------------------------
# 档位分流：L3 逐项确认、L2 阈值边界（注册表零改动继承）
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_delete_and_move_auth_mode_dispatch(tmp_path: Path) -> None:
    """AUTO_APPROVE：L3 删除恒落提案、L2 迁移落提案（批量阈值自动执行随 05 票
    计划卡落地，当前注册表口径 AUTO_APPROVE 只 L1 直执行）；
    FULL_ACCESS：L3 与 L2 均直执行（operation 行带授权依据与快照）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_course(session_factory, TARGET_COURSE)
        await seed_record(session_factory)

        # AUTO_APPROVE：删除与迁移都落提案。
        delete_payload = await invoke_tool(
            soft_delete_record,
            session_factory,
            {"record_id": RECORD_ID},
            auth_mode=AuthMode.AUTO_APPROVE,
        )
        assert delete_payload["ok"] is True
        assert delete_payload["proposals"][0]["status"] == "PENDING"
        move_payload = await invoke_tool(
            move_record_course,
            session_factory,
            {"record_id": RECORD_ID, "target_course_id": TARGET_COURSE},
            auth_mode=AuthMode.AUTO_APPROVE,
        )
        assert move_payload["ok"] is True
        assert move_payload["proposals"][0]["status"] == "PENDING"
        # 业务零变化。
        assert (
            await scalar(
                session_factory, f"SELECT deleted_at FROM records WHERE id = '{RECORD_ID}'"
            )
            is None
        )
        assert (
            await scalar(session_factory, f"SELECT course_id FROM records WHERE id = '{RECORD_ID}'")
            == COURSE_ID
        )

        # FULL_ACCESS：迁移直执行（L2）。
        executed = await invoke_tool(
            move_record_course,
            session_factory,
            {"record_id": RECORD_ID, "target_course_id": TARGET_COURSE},
            auth_mode=AuthMode.FULL_ACCESS,
        )
        assert executed["ok"] is True
        receipt = executed["executed"]
        assert receipt["action"] == "move_record_course"
        assert receipt["level"] == "L2"
        assert receipt["auth_mode"] == "FULL_ACCESS"
        assert receipt["result"]["after_course_id"] == TARGET_COURSE
        assert (
            await scalar(session_factory, f"SELECT course_id FROM records WHERE id = '{RECORD_ID}'")
            == TARGET_COURSE
        )

        # FULL_ACCESS：删除直执行（L3）。
        executed = await invoke_tool(
            soft_delete_record,
            session_factory,
            {"record_id": RECORD_ID},
            auth_mode=AuthMode.FULL_ACCESS,
        )
        assert executed["ok"] is True
        receipt = executed["executed"]
        assert receipt["action"] == "soft_delete_record"
        assert receipt["level"] == "L3"
        assert (
            await scalar(
                session_factory, f"SELECT deleted_at FROM records WHERE id = '{RECORD_ID}'"
            )
            is not None
        )
        # 直执行 operation 行：授权依据 + 快照。
        operation = await _direct_operation_row(session_factory, receipt["operation_id"])
        assert operation is not None
        assert operation["authorization"]["auth_mode"] == "FULL_ACCESS"
        assert operation["snapshot"]["course_id"] == TARGET_COURSE


async def _direct_operation_row(
    session_factory: async_sessionmaker[AsyncSession], operation_id: str
) -> dict[str, Any] | None:
    async with session_factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT action, status, snapshot_json, authorization_json"
                    " FROM agent_operations WHERE id = :id"
                ),
                {"id": operation_id},
            )
        ).first()
    if row is None:
        return None
    return {
        "action": row[0],
        "status": row[1],
        "snapshot": json.loads(row[2]) if row[2] else None,
        "authorization": json.loads(row[3]) if row[3] else None,
    }
