"""通用 Agent 第二阶段工单 06：有限 Undo 与重试。

- operation 级 Undo：改名 / 归类 / 归档 / 恢复 / 迁移补偿恢复（undo_of 链、
  原操作标记 undone_by、历史保留）；撤销前重验（目标已被后续修改 →
  OPERATION_UNDO_CONFLICT，不覆盖用户后续修改）；不可撤销动作（记录软删、
  课程删除、创建类）409＋注册项声明的原因；已撤销重复拒绝；
- Agent undo 工具（走三档授权）：默认档落 OP_UNDO 提案确认后补偿、
  FULL_ACCESS 直执行回执（与正向直执行同形）；
- run 级批次 Undo：按依赖逆序补偿、逐项结果如实呈现（单项失败不谎报）、
  未结束任务拒绝；
- 自动重试：瞬时故障（SQLITE_BUSY 锁竞争）原 operation 身份自动重试 ≤2 次
  （推进 worker 与直执行两条路径，attempts／attempts_json 如实累计）、耗尽落
  FAILED＋OPERATION_TRANSIENT_ERROR、非瞬时故障维持系统性故障口径；
- 手动重试：单步 FAILED 沿用原身份同步重执行（快照重验、attempts 递增）；
- 语义分离与对账：取消停止后续不补偿已完成；应用器异常＝operation 行与业务
  写同事务回滚（崩溃＝未发生，可安全重试）。
"""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import create_database
from app.db.migrations import run_migrations
from app.modules.agent.runs.retry import retry_standalone_operation
from app.modules.agent.runs.schemas import AuthMode
from app.modules.agent.runs.service import RunControlService
from app.modules.agent.runs.undo import UndoService
from app.modules.agent.runs.worker import advance_run, advance_step
from app.modules.agent.runtime import (
    AgentRuntimeContext,
    ToolCallBudget,
    bind_agent_runtime_context,
    reset_agent_runtime_context,
)
from app.modules.agent.tools.create_course import create_course
from app.modules.agent.tools.delete_course import delete_course
from app.modules.agent.tools.move_record_course import move_record_course
from app.modules.agent.tools.plan_batch_operations import plan_batch_operations
from app.modules.agent.tools.undo_operation import undo_operation
from app.modules.agent.tools.update_course import update_course
from app.modules.agent.tools.update_library_item import update_library_item
from app.modules.library.proposals import ProposalService
from app.shared.errors import CodedHTTPException

NOW = "2026-09-28T08:00:00.000000Z"
COURSE_ID = "c0000000-0000-4000-8000-000000000001"
COURSE_OTHER = "c0000000-0000-4000-8000-000000000002"
COURSE_ARCHIVED = "c0000000-0000-4000-8000-000000000003"
SESSION_ID = "sess-undo"
RECORD_ID = "d0000000-0000-4000-8000-00000000000d"


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


async def scalar(
    session_factory: async_sessionmaker[AsyncSession], sql: str, **params: object
) -> Any:
    async with session_factory() as session:
        return (await session.execute(text(sql), params)).scalar_one()


async def seed_course(
    session_factory: async_sessionmaker[AsyncSession],
    course_id: str = COURSE_ID,
    *,
    name: str = "整理目标课程",
    status: str = "ACTIVE",
) -> None:
    await run_sql(
        "INSERT INTO courses (id, name, learning_context, depth, status, created_at,"
        " updated_at) VALUES (:id, :name, 'INTEREST', 'INTERMEDIATE', :status, :now, :now)",
        {"id": course_id, "name": name, "status": status, "now": NOW},
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


async def seed_record(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    course_id: str | None = COURSE_ID,
) -> None:
    await run_sql(
        "INSERT INTO records (id, course_id, capture_type, title, status, duration_ms, "
        "created_at, updated_at) "
        "VALUES (:id, :course_id, 'PASTE', '第 1 讲 一致性哈希', 'COMPLETED', 0, :now, :now)",
        {"id": RECORD_ID, "course_id": course_id, "now": NOW},
        session_factory,
    )


async def item_row(
    session_factory: async_sessionmaker[AsyncSession], index: int
) -> tuple[str, str | None, str]:
    row = await scalar_one_row(
        session_factory,
        "SELECT title, course_id, status FROM library_items WHERE id = :id",
        {"id": item_id(index)},
    )
    return cast("tuple[str, str | None, str]", row)


async def scalar_one_row(
    session_factory: async_sessionmaker[AsyncSession],
    sql: str,
    params: dict[str, object],
) -> tuple[Any, ...]:
    async with session_factory() as session:
        row = (await session.execute(text(sql), params)).one()
    return tuple(row)


async def invoke_tool(
    tool: Any,
    session_factory: async_sessionmaker[AsyncSession],
    args: dict[str, Any],
    *,
    auth_mode: AuthMode = AuthMode.FULL_ACCESS,
) -> dict[str, Any]:
    """直调薄工具（绑定统一运行时上下文的工具层缝隙，先例：操作工具往返）。"""
    token = bind_agent_runtime_context(
        AgentRuntimeContext(
            session_factory=session_factory,
            session_id=SESSION_ID,
            auth_mode=auth_mode,
            instruction_excerpt="把这些整理一下",
            message_id="msg-undo-1",
            budget=ToolCallBudget(),
        )
    )
    try:
        raw = await tool.ainvoke(args)
        return dict(json.loads(raw))
    finally:
        reset_agent_runtime_context(token)


async def operation_rows(
    session_factory: async_sessionmaker[AsyncSession],
    where: str = "run_id IS NULL",
    params: dict[str, object] | None = None,
) -> list[dict[str, Any]]:
    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT id, action, status, undo_of, undone_by, attempts,"
                    " attempts_json, authorization_json, snapshot_json, result_json,"
                    " error_code, run_id"
                    f" FROM agent_operations WHERE {where}"
                    " ORDER BY created_at, id"
                ),
                params or {},
            )
        ).all()
    keys = (
        "id",
        "action",
        "status",
        "undo_of",
        "undone_by",
        "attempts",
        "attempts_json",
        "authorization_json",
        "snapshot_json",
        "result_json",
        "error_code",
        "run_id",
    )
    return [dict(zip(keys, row, strict=True)) for row in rows]


def locked_error(message: str = "database is locked") -> OperationalError:
    return OperationalError("SQL", {}, Exception(message))


# ---------------------------------------------------------------------------
# operation 级 Undo


@pytest.mark.anyio
async def test_undo_rename_library_item_restores_before(tmp_path: Path) -> None:
    """改名 → 撤销恢复旧名：补偿行 undo_of 关联、原行标记 undone_by、授权
    依据 trigger=USER_UNDO、补偿快照＝撤销前目标态（供再撤销）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_item(session_factory, 1)
        receipt = await invoke_tool(
            update_library_item,
            session_factory,
            {"item_id": item_id(1), "title": "新标题"},
        )
        original_id = receipt["executed"]["operation_id"]
        assert (await item_row(session_factory, 1))[0] == "新标题"

        async with session_factory() as session:
            compensation = await UndoService.undo_operation(session, original_id)

        assert (await item_row(session_factory, 1))[0] == "条目1"
        rows = await operation_rows(session_factory)
        assert [row["status"] for row in rows] == ["SUCCEEDED", "SUCCEEDED"]
        original, undo_row = rows
        assert original["id"] == original_id
        assert original["undone_by"] == compensation["id"]
        assert undo_row["undo_of"] == original_id
        assert undo_row["undone_by"] is None
        assert undo_row["snapshot_json"] is not None
        assert json.loads(undo_row["snapshot_json"])["title"] == "新标题"
        assert json.loads(undo_row["authorization_json"])["trigger"] == "USER_UNDO"
        assert json.loads(undo_row["result_json"])["restored"] == {"title": "条目1"}


@pytest.mark.anyio
async def test_undo_rejected_when_target_modified_after(tmp_path: Path) -> None:
    """用户真机验收场景：撤销前又手动改过名 → 明确拒绝（OPERATION_UNDO_CONFLICT）
    且不覆盖后续修改。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_item(session_factory, 1)
        receipt = await invoke_tool(
            update_library_item,
            session_factory,
            {"item_id": item_id(1), "title": "新标题"},
        )
        await run_sql(
            "UPDATE library_items SET title = '用户手改', updated_at = :later WHERE id = :id",
            {"id": item_id(1), "later": "2026-09-28T10:00:00.000000Z"},
            session_factory,
        )
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc:
                await UndoService.undo_operation(session, receipt["executed"]["operation_id"])
        assert exc.value.code == "OPERATION_UNDO_CONFLICT"
        assert (await item_row(session_factory, 1))[0] == "用户手改"
        rows = await operation_rows(session_factory)
        assert len(rows) == 1  # 撤销失败＝未发生，无补偿行
        assert rows[0]["undone_by"] is None


@pytest.mark.anyio
async def test_undo_non_undoable_actions_report_reason(tmp_path: Path) -> None:
    """不可撤销动作明确告知原因：课程删除（含级联）与创建类（不在首批）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        delete_receipt = await invoke_tool(delete_course, session_factory, {"course_id": COURSE_ID})
        create_receipt = await invoke_tool(
            create_course,
            session_factory,
            {
                "name": "撤销范围外的课",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        for receipt, fragment in (
            (delete_receipt, "不可撤销"),
            (create_receipt, "不在首批撤销范围"),
        ):
            async with session_factory() as session:
                with pytest.raises(CodedHTTPException) as exc:
                    await UndoService.undo_operation(session, receipt["executed"]["operation_id"])
            assert exc.value.code == "OPERATION_NOT_UNDOABLE"
            assert fragment in exc.value.detail


@pytest.mark.anyio
async def test_undo_twice_rejected_and_requires_succeeded(tmp_path: Path) -> None:
    """已撤销重复拒绝（OPERATION_ALREADY_UNDONE）；失败态操作不可撤销。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory, COURSE_ARCHIVED, status="ARCHIVED")
        await seed_item(session_factory, 1)
        receipt = await invoke_tool(
            update_library_item,
            session_factory,
            {"item_id": item_id(1), "course_id": COURSE_ARCHIVED},
        )
        assert receipt["ok"] is False  # 目标课程已归档 → 直执行 FAILED
        failed_id = (await operation_rows(session_factory))[0]["id"]

        # 失败态：不可撤销
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc:
                await UndoService.undo_operation(session, failed_id)
        assert exc.value.code == "OPERATION_NOT_UNDOABLE"

        # 成功撤销后重复撤销
        await invoke_tool(
            update_library_item, session_factory, {"item_id": item_id(1), "title": "改名"}
        )
        succeeded_id = (await operation_rows(session_factory))[-1]["id"]
        async with session_factory() as session:
            await UndoService.undo_operation(session, succeeded_id)
            with pytest.raises(CodedHTTPException) as exc:
                await UndoService.undo_operation(session, succeeded_id)
        assert exc.value.code == "OPERATION_ALREADY_UNDONE"


@pytest.mark.anyio
async def test_undo_update_course_restores_name(tmp_path: Path) -> None:
    """课程改名撤销：恢复旧名（update 类补偿的字段级恢复）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory, name="旧课名")
        receipt = await invoke_tool(
            update_course, session_factory, {"course_id": COURSE_ID, "name": "新课名"}
        )
        assert (
            await scalar(session_factory, "SELECT name FROM courses WHERE id = :id", id=COURSE_ID)
            == "新课名"
        )
        async with session_factory() as session:
            await UndoService.undo_operation(session, receipt["executed"]["operation_id"])
        assert (
            await scalar(session_factory, "SELECT name FROM courses WHERE id = :id", id=COURSE_ID)
            == "旧课名"
        )


@pytest.mark.anyio
async def test_undo_move_record_reverse(tmp_path: Path) -> None:
    """跨课迁移撤销＝反向迁移过全部校验（spec 决策 19）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_course(session_factory, COURSE_OTHER, name="目标课程")
        await seed_record(session_factory)
        receipt = await invoke_tool(
            move_record_course,
            session_factory,
            {"record_id": RECORD_ID, "target_course_id": COURSE_OTHER},
        )
        assert (
            await scalar(
                session_factory, "SELECT course_id FROM records WHERE id = :id", id=RECORD_ID
            )
            == COURSE_OTHER
        )

        async with session_factory() as session:
            await UndoService.undo_operation(session, receipt["executed"]["operation_id"])

        assert (
            await scalar(
                session_factory, "SELECT course_id FROM records WHERE id = :id", id=RECORD_ID
            )
            == COURSE_ID
        )


@pytest.mark.anyio
async def test_undo_move_record_to_inbox_guards_running_jobs(tmp_path: Path) -> None:
    """收件箱来源的迁移撤销：恢复为未归类仍过「无进行中任务」守卫（决策 17
    全部校验口径），无任务时轻量恢复＋索引重建。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_record(session_factory, course_id=None)
        receipt = await invoke_tool(
            move_record_course,
            session_factory,
            {"record_id": RECORD_ID, "target_course_id": COURSE_ID},
        )
        assert receipt["ok"] is True

        # 记录有进行中任务 → 撤销被拒（RECORD_MOVE_JOB_IN_PROGRESS）。
        await run_sql(
            "INSERT INTO processing_jobs (id, record_id, job_type, status, progress, "
            "attempts, max_attempts, input_json, created_at, updated_at) "
            "VALUES ('j0000000-0000-4000-8000-00000000000j', :record_id, 'SUMMARY',"
            " 'RUNNING', 0.0, 0, 3, '{}', :now, :now)",
            {"record_id": RECORD_ID, "now": NOW},
            session_factory,
        )
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc:
                await UndoService.undo_operation(session, receipt["executed"]["operation_id"])
        assert exc.value.code == "RECORD_MOVE_JOB_IN_PROGRESS"
        assert await scalar(
            session_factory, "SELECT course_id FROM records WHERE id = :id", id=RECORD_ID
        ) == COURSE_ID

        # 任务终态后撤销成功：恢复为收件箱（course_id 空）。
        await run_sql(
            "UPDATE processing_jobs SET status = 'SUCCEEDED' WHERE record_id = :id",
            {"id": RECORD_ID},
            session_factory,
        )
        async with session_factory() as session:
            await UndoService.undo_operation(session, receipt["executed"]["operation_id"])
        assert (
            await scalar(
                session_factory, "SELECT course_id FROM records WHERE id = :id", id=RECORD_ID
            )
            is None
        )


# ---------------------------------------------------------------------------
# Agent undo 工具（三档授权）


@pytest.mark.anyio
async def test_agent_undo_tool_proposal_and_confirm(tmp_path: Path) -> None:
    """默认档：undo 工具落 OP_UNDO 提案，确认后补偿执行（走三档授权）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_item(session_factory, 1)
        receipt = await invoke_tool(
            update_library_item,
            session_factory,
            {"item_id": item_id(1), "title": "新标题"},
        )
        original_id = receipt["executed"]["operation_id"]

        result = await invoke_tool(
            undo_operation,
            session_factory,
            {"operation_id": original_id},
            auth_mode=AuthMode.REQUEST_APPROVAL,
        )
        assert result["ok"] is True
        proposal_entry = result["proposals"][0]
        assert proposal_entry["action"] == "undo_operation"
        assert (await item_row(session_factory, 1))[0] == "新标题"  # 确认前零补偿

        async with session_factory() as session:
            applied = await ProposalService.confirm(session, proposal_entry["proposal_id"])

        assert (await item_row(session_factory, 1))[0] == "条目1"
        undo_rows = [row for row in await operation_rows(session_factory) if row["undo_of"]]
        assert len(undo_rows) == 1
        assert undo_rows[0]["undo_of"] == original_id
        authorization = json.loads(undo_rows[0]["authorization_json"])
        assert authorization["trigger"] == "USER_CONFIRMED_PROPOSAL"
        compensation_id = cast(str, applied.result and applied.result["operation_id"])
        assert undo_rows[0]["id"] == compensation_id


@pytest.mark.anyio
async def test_agent_undo_tool_direct_execution(tmp_path: Path) -> None:
    """FULL_ACCESS：undo 工具直执行（L1 撤销自动执行）并给回执。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_item(session_factory, 1)
        receipt = await invoke_tool(
            update_library_item,
            session_factory,
            {"item_id": item_id(1), "title": "新标题"},
        )
        result = await invoke_tool(
            undo_operation,
            session_factory,
            {"operation_id": receipt["executed"]["operation_id"]},
        )
        assert result["ok"] is True
        executed = result["executed"]
        assert executed["operation_id"]
        assert executed["action"] == "update_library_item"
        assert executed["auth_mode"] == "FULL_ACCESS"
        assert executed["result"]["undone_operation_id"] == receipt["executed"]["operation_id"]
        assert (await item_row(session_factory, 1))[0] == "条目1"


@pytest.mark.anyio
async def test_agent_undo_tool_reports_non_undoable_reason(tmp_path: Path) -> None:
    """工具结果透出不可撤销原因（结构化返回，模型转述）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        receipt = await invoke_tool(delete_course, session_factory, {"course_id": COURSE_ID})
        result = await invoke_tool(
            undo_operation,
            session_factory,
            {"operation_id": receipt["executed"]["operation_id"]},
            auth_mode=AuthMode.REQUEST_APPROVAL,
        )
        assert result["ok"] is False
        assert result["error"] == "OPERATION_NOT_UNDOABLE"
        assert "不可撤销" in result["detail"]


# ---------------------------------------------------------------------------
# run 级批次 Undo


async def run_batch_and_complete(
    session_factory: async_sessionmaker[AsyncSession],
    entries: list[dict[str, Any]],
    *,
    advance: bool = True,
) -> str:
    """计划卡确认（advance=True 时推进至终态；取消 / 故障注入用例自行控制推进）。"""
    token = bind_agent_runtime_context(
        AgentRuntimeContext(
            session_factory=session_factory,
            session_id=SESSION_ID,
            auth_mode=AuthMode.REQUEST_APPROVAL,
            instruction_excerpt="批量归类",
            message_id="msg-batch",
            budget=ToolCallBudget(),
        )
    )
    try:
        raw = await plan_batch_operations.ainvoke({"items": entries})
        planned = dict(json.loads(raw))
    finally:
        reset_agent_runtime_context(token)
    proposal_id = planned["plan_proposal"]["proposal_id"]
    async with session_factory() as session:
        applied = await ProposalService.confirm(session, proposal_id)
    assert applied.result is not None
    run_id = cast(str, applied.result["run_id"])
    if advance:
        await advance_run(session_factory, run_id)
    return run_id


@pytest.mark.anyio
async def test_run_batch_undo_reverses_in_dependency_order(tmp_path: Path) -> None:
    """批量归类后整批撤销：按依赖逆序补偿（items 逆序）、逐项恢复、补偿行
    挂同一 run（操作历史 run 展开可见）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_item(session_factory, 1)
        await seed_item(session_factory, 2)
        run_id = await run_batch_and_complete(
            session_factory,
            [
                {"action": "update_library_item", "item_id": item_id(1), "course_id": COURSE_ID},
                {"action": "update_library_item", "item_id": item_id(2), "course_id": COURSE_ID},
            ],
        )
        assert (await item_row(session_factory, 1))[1] == COURSE_ID
        assert (await item_row(session_factory, 2))[1] == COURSE_ID

        async with session_factory() as session:
            result = await UndoService.undo_run(session, run_id)

        assert result.undone_count == 2
        assert result.failed_count == 0
        assert (await item_row(session_factory, 1))[1] is None
        assert (await item_row(session_factory, 2))[1] is None
        rows = await operation_rows(session_factory, "run_id = :rid", {"rid": run_id})
        originals = [row for row in rows if row["undo_of"] is None]
        compensations = [row for row in rows if row["undo_of"] is not None]
        assert len(originals) == 2 and len(compensations) == 2
        assert all(row["status"] == "SUCCEEDED" for row in rows)
        assert {row["undo_of"] for row in compensations} == {row["id"] for row in originals}
        # 逆序补偿：批次 undo 的逐项结果按计划倒序（后执行的先补偿）——补偿行
        # 按撤销执行序落库（created_at 递增），其 undo_of 序即计划倒序。
        assert [item.operation_id for item in result.items] == [
            row["undo_of"] for row in compensations
        ]


@pytest.mark.anyio
async def test_run_undo_reports_item_failures_honestly(tmp_path: Path) -> None:
    """单项补偿失败不谎报整体成功：被手动改过的项 FAILED（CONFLICT）、
    其余项照常补偿、目标状态不被覆盖；失败补偿独立小事务留痕（undo_of
    挂原行、error_code 记原因），刷新后 run 展开仍可见（review P2）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_course(session_factory, COURSE_OTHER, name="用户手改目标课程")
        await seed_item(session_factory, 1)
        await seed_item(session_factory, 2)
        run_id = await run_batch_and_complete(
            session_factory,
            [
                {"action": "update_library_item", "item_id": item_id(1), "course_id": COURSE_ID},
                {"action": "update_library_item", "item_id": item_id(2), "course_id": COURSE_ID},
            ],
        )
        # 条目 2 在批次后被手动改归类（模拟用户后续修改）。
        await run_sql(
            "UPDATE library_items SET course_id = :course, updated_at = :later WHERE id = :id",
            {"id": item_id(2), "course": COURSE_OTHER, "later": "2026-09-28T10:00:00.000000Z"},
            session_factory,
        )

        async with session_factory() as session:
            result = await UndoService.undo_run(session, run_id)

        assert result.undone_count == 1
        assert result.failed_count == 1
        failed = next(item for item in result.items if item.status == "FAILED")
        assert failed.error_code == "OPERATION_UNDO_CONFLICT"
        assert (await item_row(session_factory, 1))[1] is None  # 成功项恢复
        assert (await item_row(session_factory, 2))[1] == COURSE_OTHER  # 不覆盖
        # 失败留痕持久化：FAILED 补偿行 undo_of 挂原行、错误码可查；原行保持
        # SUCCEEDED 且无 undone_by（可再次发起撤销）。
        rows = await operation_rows(session_factory, "run_id = :rid", {"rid": run_id})
        originals = {row["id"]: row for row in rows if row["undo_of"] is None}
        compensations = [row for row in rows if row["undo_of"] is not None]
        failed_rows = [row for row in compensations if row["status"] == "FAILED"]
        assert len(failed_rows) == 1
        assert failed_rows[0]["error_code"] == "OPERATION_UNDO_CONFLICT"
        conflicted_original = originals[failed_rows[0]["undo_of"]]
        assert conflicted_original["status"] == "SUCCEEDED"
        assert conflicted_original["undone_by"] is None
        succeeded_compensations = [row for row in compensations if row["status"] == "SUCCEEDED"]
        assert len(succeeded_compensations) == 1
        assert (
            originals[succeeded_compensations[0]["undo_of"]]["undone_by"]
            == succeeded_compensations[0]["id"]
        )


@pytest.mark.anyio
async def test_retry_rejects_compensation_rows(tmp_path: Path) -> None:
    """任务重试拒绝补偿行（undo_of 非空）：重试会按其 payload 重放正向操作
    语义，失败补偿的正确路径是重新发起撤销（review P2 守卫）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_course(session_factory, COURSE_OTHER, name="用户手改目标课程")
        await seed_item(session_factory, 1)
        run_id = await run_batch_and_complete(
            session_factory,
            [{"action": "update_library_item", "item_id": item_id(1), "course_id": COURSE_ID}],
        )
        # 批次后手动改归类 → 撤销失败留痕 FAILED 补偿行。
        await run_sql(
            "UPDATE library_items SET course_id = :course, updated_at = :later WHERE id = :id",
            {"id": item_id(1), "course": COURSE_OTHER, "later": "2026-09-28T10:00:00.000000Z"},
            session_factory,
        )
        async with session_factory() as session:
            await UndoService.undo_run(session, run_id)
        failed_compensation = next(
            row
            for row in await operation_rows(session_factory, "run_id = :rid", {"rid": run_id})
            if row["undo_of"] is not None and row["status"] == "FAILED"
        )
        # 部分完成任务可重开推进（_require_live_run 放行），但补偿行仍须拒绝。
        await run_sql(
            "UPDATE agent_runs SET status = 'PARTIAL_COMPLETED' WHERE id = :id",
            {"id": run_id},
            session_factory,
        )
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc:
                await RunControlService.retry_operation(
                    session, run_id=run_id, operation_id=failed_compensation["id"]
                )
        assert exc.value.code == "AGENT_RUN_OPERATION_NOT_RETRYABLE"
        assert "补偿" in exc.value.detail


@pytest.mark.anyio
async def test_run_undo_requires_finished_run(tmp_path: Path) -> None:
    """撤销不与推进并发：未结束（RUNNING）任务拒绝整批撤销。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_item(session_factory, 1)
        token = bind_agent_runtime_context(
            AgentRuntimeContext(
                session_factory=session_factory,
                session_id=SESSION_ID,
                auth_mode=AuthMode.REQUEST_APPROVAL,
                instruction_excerpt="批量归档",
                message_id="msg-batch",
                budget=ToolCallBudget(),
            )
        )
        try:
            raw = await plan_batch_operations.ainvoke(
                {"items": [{"action": "archive_library_item", "item_id": item_id(1)}]}
            )
            planned = dict(json.loads(raw))
        finally:
            reset_agent_runtime_context(token)
        async with session_factory() as session:
            applied = await ProposalService.confirm(
                session, planned["plan_proposal"]["proposal_id"]
            )
        assert applied.result is not None
        run_id = cast(str, applied.result["run_id"])
        # 推进前（仍 RUNNING）撤销 → 拒绝
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc:
                await UndoService.undo_run(session, run_id)
        assert exc.value.code == "AGENT_RUN_NOT_FINISHED"


# ---------------------------------------------------------------------------
# 自动重试（瞬时故障）


@pytest.mark.anyio
async def test_worker_transient_retry_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SQLITE_BUSY 前两次、第三次成功：原身份 attempts=3、SUCCEEDED、
    attempts_json 留两次瞬时历史。"""
    from app.modules.agent.runs import worker as worker_module

    calls = 0

    async def flaky(session: AsyncSession, spec: Any, payload_json: str) -> Any:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise locked_error()
        from app.modules.agent.schemas import LibraryItemArchiveResult

        return LibraryItemArchiveResult(item_id=item_id(1), status="ARCHIVED")

    monkeypatch.setattr(worker_module, "run_operation_applier", flaky)
    async with bare_db(tmp_path) as session_factory:
        await seed_item(session_factory, 1)
        run_id = await run_batch_and_complete(
            session_factory,
            [{"action": "archive_library_item", "item_id": item_id(1)}],
        )
        status = await advance_run(session_factory, run_id)
        assert status == "COMPLETED"
        assert calls == 3
        rows = await operation_rows(session_factory, "run_id = :rid", {"rid": run_id})
        assert rows[0]["status"] == "SUCCEEDED"
        assert rows[0]["attempts"] == 3
        history = json.loads(rows[0]["attempts_json"] or "[]")
        assert len(history) == 2
        assert all(entry["error_code"] == "OPERATION_TRANSIENT_ERROR" for entry in history)


@pytest.mark.anyio
async def test_worker_transient_retry_exhausted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """恒锁竞争：重试 ≤2 次后 FAILED＋OPERATION_TRANSIENT_ERROR，批次按独立项
    收尾（部分完成）。"""
    from app.modules.agent.runs import worker as worker_module

    async def always_locked(session: AsyncSession, spec: Any, payload_json: str) -> Any:
        raise locked_error()

    monkeypatch.setattr(worker_module, "run_operation_applier", always_locked)
    async with bare_db(tmp_path) as session_factory:
        await seed_item(session_factory, 1)
        run_id = await run_batch_and_complete(
            session_factory,
            [{"action": "archive_library_item", "item_id": item_id(1)}],
        )
        status = await advance_run(session_factory, run_id)
        assert status == "PARTIAL_COMPLETED"
        rows = await operation_rows(session_factory, "run_id = :rid", {"rid": run_id})
        assert rows[0]["status"] == "FAILED"
        assert rows[0]["error_code"] == "OPERATION_TRANSIENT_ERROR"
        assert rows[0]["attempts"] == 3  # 初试＋2 次自动重试


@pytest.mark.anyio
async def test_worker_non_transient_error_is_system_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """非瞬时 OperationalError（如 SQL 语法错误）不走自动重试，维持系统性
    故障上抛口径（job 层落 AGENT_RUN_FAILED）。"""
    from app.modules.agent.runs import worker as worker_module

    async def broken(session: AsyncSession, spec: Any, payload_json: str) -> Any:
        raise OperationalError("SQL", {}, Exception("no such table: missing"))

    monkeypatch.setattr(worker_module, "run_operation_applier", broken)
    async with bare_db(tmp_path) as session_factory:
        await seed_item(session_factory, 1)
        run_id = await run_batch_and_complete(
            session_factory,
            [{"action": "archive_library_item", "item_id": item_id(1)}],
            advance=False,
        )
        with pytest.raises(OperationalError):
            await advance_run(session_factory, run_id)


@pytest.mark.anyio
async def test_direct_execution_transient_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """直执行路径的瞬时自动重试：成功回执 ok=True、attempts=3、留痕两条。"""
    from app.modules.agent.operations import registry as registry_module

    calls = 0

    async def flaky(session: AsyncSession, spec: Any, payload_json: str) -> Any:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise locked_error()
        from app.modules.agent.schemas import LibraryItemUpdateResult

        return LibraryItemUpdateResult(item_id=item_id(1), before={}, after={})

    monkeypatch.setattr(registry_module, "run_operation_applier", flaky)
    async with bare_db(tmp_path) as session_factory:
        await seed_item(session_factory, 1)
        receipt = await invoke_tool(
            update_library_item,
            session_factory,
            {"item_id": item_id(1), "title": "新标题"},
        )
        assert receipt["ok"] is True
        rows = await operation_rows(session_factory)
        assert rows[0]["attempts"] == 3
        assert len(json.loads(rows[0]["attempts_json"] or "[]")) == 2


@pytest.mark.anyio
async def test_direct_retry_rechecks_auth_on_downgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """重试轮授权重检（spec 决策 20）：首试遇锁后会话降档 → 停止重试、
    FAILED＋OPERATION_APPROVAL_REQUIRED、第二轮不执行业务写。"""
    from app.modules.agent.auth_mode import (
        clear_session_auth_override,
        set_session_auth_override,
    )
    from app.modules.agent.operations import registry as registry_module

    calls = 0

    async def locked_and_downgraded(session: AsyncSession, spec: Any, payload_json: str) -> Any:
        nonlocal calls
        calls += 1
        # 首试即遇锁；模拟用户在重试窗口内把会话降回默认档。
        set_session_auth_override(SESSION_ID, AuthMode.REQUEST_APPROVAL)
        raise locked_error()

    monkeypatch.setattr(registry_module, "run_operation_applier", locked_and_downgraded)
    try:
        async with bare_db(tmp_path) as session_factory:
            await seed_item(session_factory, 1)
            receipt = await invoke_tool(
                update_library_item,
                session_factory,
                {"item_id": item_id(1), "title": "新标题"},
            )
            assert receipt["ok"] is False
            assert receipt["error"] == "OPERATION_APPROVAL_REQUIRED"
            # 第二轮在授权重检处拦截，业务写不再执行。
            assert calls == 1
            rows = await operation_rows(session_factory)
            assert rows[0]["status"] == "FAILED"
            assert rows[0]["error_code"] == "OPERATION_APPROVAL_REQUIRED"
            assert rows[0]["attempts"] == 2  # 首试＋降档拦截轮
    finally:
        clear_session_auth_override(SESSION_ID)


@pytest.mark.anyio
async def test_direct_retry_rejects_target_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """重试轮版本重验（spec 决策 20）：锁竞争窗口内目标被手改（快照偏离
    首试基线）→ FAILED＋OPERATION_SNAPSHOT_STALE，不覆盖手改。"""
    from app.modules.agent.operations import registry as registry_module
    from app.modules.agent.operations.registry import get_operation

    calls = 0

    async def always_locked(session: AsyncSession, spec: Any, payload_json: str) -> Any:
        nonlocal calls
        calls += 1
        raise locked_error()

    monkeypatch.setattr(registry_module, "run_operation_applier", always_locked)
    # 冻结 dataclass：经 object.__setattr__ 挂钩快照采集，第二轮模拟目标漂移。
    spec = get_operation("update_library_item")
    assert spec is not None
    original_capture = spec.capture_state
    capture_calls = 0

    async def drifting_capture(session: AsyncSession, payload: Any) -> Any:
        nonlocal capture_calls
        capture_calls += 1
        snapshot = await original_capture(session, payload)
        if capture_calls > 1:
            return snapshot.model_copy(update={"title": "用户手改标题"})
        return snapshot

    object.__setattr__(spec, "capture_state", drifting_capture)
    try:
        async with bare_db(tmp_path) as session_factory:
            await seed_item(session_factory, 1)
            receipt = await invoke_tool(
                update_library_item,
                session_factory,
                {"item_id": item_id(1), "title": "新标题"},
            )
            assert receipt["ok"] is False
            assert receipt["error"] == "OPERATION_SNAPSHOT_STALE"
            assert calls == 1  # 第二轮在版本重验处拦截
            rows = await operation_rows(session_factory)
            assert rows[0]["status"] == "FAILED"
            assert rows[0]["error_code"] == "OPERATION_SNAPSHOT_STALE"
            assert rows[0]["attempts"] == 2
    finally:
        object.__setattr__(spec, "capture_state", original_capture)


# ---------------------------------------------------------------------------
# 手动重试（单步）


@pytest.mark.anyio
async def test_standalone_manual_retry_reuses_identity(tmp_path: Path) -> None:
    """失败项手动重试沿用原 operation 身份：修复后重试成功、attempts 递增、
    业务恰好生效一次（无重复副作用）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory, COURSE_ARCHIVED, status="ARCHIVED")
        await seed_item(session_factory, 1)
        # 归类到已归档课程 → 直执行 FAILED（快照已固化、领域拒绝不自动重试）。
        failed_receipt = await invoke_tool(
            update_library_item,
            session_factory,
            {"item_id": item_id(1), "course_id": COURSE_ARCHIVED},
        )
        assert failed_receipt["ok"] is False
        rows = await operation_rows(session_factory)
        failed_row = rows[-1]
        assert failed_row["status"] == "FAILED"
        assert failed_row["snapshot_json"] is not None

        # 修复冲突（恢复课程 ACTIVE）后手动重试：沿用原身份成功。
        await run_sql(
            "UPDATE courses SET status = 'ACTIVE' WHERE id = :id",
            {"id": COURSE_ARCHIVED},
            session_factory,
        )
        async with session_factory() as session:
            result = await retry_standalone_operation(session, failed_row["id"])

        assert result["status"] == "SUCCEEDED"
        assert result["attempts"] == failed_row["attempts"] + 1
        assert (await item_row(session_factory, 1))[1] == COURSE_ARCHIVED  # 恰好一次
        rows_after = await operation_rows(session_factory)
        assert len(rows_after) == len(rows)  # 无新增行（原身份重试）


@pytest.mark.anyio
async def test_standalone_retry_stale_after_target_changed(tmp_path: Path) -> None:
    """手动重试同样执行前重验：目标已变 → FAILED＋OPERATION_SNAPSHOT_STALE
    （旧批准失效，需重新发起操作）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory, COURSE_ARCHIVED, status="ARCHIVED")
        await seed_item(session_factory, 1)
        receipt = await invoke_tool(
            update_library_item,
            session_factory,
            {"item_id": item_id(1), "course_id": COURSE_ARCHIVED},
        )
        assert receipt["ok"] is False
        rows = await operation_rows(session_factory)
        failed_row = rows[-1]
        # 失败后手动改名（目标已偏离失败时快照）。
        await run_sql(
            "UPDATE library_items SET title = '手改标题', updated_at = :later WHERE id = :id",
            {"id": item_id(1), "later": "2026-09-28T10:00:00.000000Z"},
            session_factory,
        )
        async with session_factory() as session:
            result = await retry_standalone_operation(session, failed_row["id"])
        assert result["status"] == "FAILED"
        assert result["error_code"] == "OPERATION_SNAPSHOT_STALE"
        assert result["attempts"] == failed_row["attempts"] + 1
        # attempts_json 逐次尝试错误历史可查（工单 06）。
        history: list[dict[str, Any]] = result["attempts_history"] or []
        assert history and history[-1]["error_code"] == "OPERATION_SNAPSHOT_STALE"


@pytest.mark.anyio
async def test_standalone_retry_guards(tmp_path: Path) -> None:
    """守卫：不存在 404；非失败态拒绝；run 内操作指引走任务面板。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_item(session_factory, 1)
        await invoke_tool(
            update_library_item, session_factory, {"item_id": item_id(1), "title": "改名"}
        )
        succeeded_id = (await operation_rows(session_factory))[-1]["id"]
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc:
                await retry_standalone_operation(session, "00000000-0000-4000-8000-0000000000ff")
        assert exc.value.code == "AGENT_OPERATION_NOT_FOUND"

        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc:
                await retry_standalone_operation(session, succeeded_id)
        assert exc.value.code == "OPERATION_NOT_RETRYABLE"

        # run 内操作拒绝（走任务面板重试）。
        run_id = await run_batch_and_complete(
            session_factory,
            [{"action": "archive_library_item", "item_id": item_id(1)}],
        )
        await advance_run(session_factory, run_id)
        run_step_id = (await operation_rows(session_factory, "run_id = :rid", {"rid": run_id}))[0][
            "id"
        ]
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc:
                await retry_standalone_operation(session, run_step_id)
        assert exc.value.code == "OPERATION_NOT_RETRYABLE"


@pytest.mark.anyio
async def test_direct_failure_receipt_anchors_failed_operation(
    tmp_path: Path,
) -> None:
    """直执行失败载荷携带 operation_id（工单 06 review 修复）：真实失败回执的
    id 与落库 FAILED 行一致，且经 graph 事件解析产锚点事件——消息流回执卡的
    手动重试入口据此真实可达（此前锚点只覆盖成功路径，按钮为死代码）。"""
    from langchain_core.messages import ToolMessage

    from app.modules.agent.graph import _operation_execution_event

    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory, COURSE_ARCHIVED, status="ARCHIVED")
        await seed_item(session_factory, 1)
        receipt = await invoke_tool(
            update_library_item,
            session_factory,
            {"item_id": item_id(1), "course_id": COURSE_ARCHIVED},
        )
        assert receipt["ok"] is False
        failed_row = (await operation_rows(session_factory))[-1]
        assert failed_row["status"] == "FAILED"
        # 失败回执携带 FAILED 行 id（消息流锚点与模型引用的定位依据）。
        assert receipt["operation_id"] == failed_row["id"]

        event = _operation_execution_event(
            ToolMessage(
                content=json.dumps(receipt, ensure_ascii=False),
                name="update_library_item",
                tool_call_id="tc-1",
            )
        )
        assert event is not None
        assert event.executions[0]["operation_id"] == failed_row["id"]
        assert event.executions[0]["failed"] is True
        assert event.executions[0]["error"] == receipt["error"]


# ---------------------------------------------------------------------------
# 语义分离与对账


@pytest.mark.anyio
async def test_cancel_keeps_completed_without_compensation(tmp_path: Path) -> None:
    """取消与撤销语义分离：取消停止后续（未执行项 CANCELLED）、不补偿已完成
    （成功项原样保留、无补偿行）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_item(session_factory, 1)
        await seed_item(session_factory, 2)
        run_id = await run_batch_and_complete(
            session_factory,
            [
                {"action": "archive_library_item", "item_id": item_id(1)},
                {"action": "archive_library_item", "item_id": item_id(2)},
            ],
            advance=False,
        )
        assert await advance_step(session_factory, run_id) is True  # 第 1 项成功
        async with session_factory() as session:
            await RunControlService.cancel_run(session, run_id)
        await advance_run(session_factory, run_id)

        rows = await operation_rows(session_factory, "run_id = :rid", {"rid": run_id})
        # 同批提交行序不稳定（created_at 相同按 id 排），按语义断言。
        assert sorted(row["status"] for row in rows) == ["CANCELLED", "SUCCEEDED"]
        assert all(row["undone_by"] is None for row in rows)
        assert all(row["undo_of"] is None for row in rows)  # 取消不产生补偿
        assert (await item_row(session_factory, 1))[2] == "ARCHIVED"  # 已提交保留
        assert (await item_row(session_factory, 2))[2] == "ACTIVE"


@pytest.mark.anyio
async def test_applier_crash_leaves_no_operation_or_business_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """未知结果对账锚点（spec 决策 20）：应用器在业务写之后崩溃 → operation
    行与业务写同事务回滚（崩溃＝未发生、可安全重试；行在＝已执行由成功路径
    的同事务断言覆盖）。"""
    from app.modules.agent.runs import worker as worker_module

    async def crash_after_write(session: AsyncSession, spec: Any, payload_json: str) -> Any:
        await session.execute(
            text("UPDATE library_items SET status = 'ARCHIVED' WHERE id = :id"),
            {"id": item_id(1)},
        )
        raise RuntimeError("boom after business write")

    monkeypatch.setattr(worker_module, "run_operation_applier", crash_after_write)
    async with bare_db(tmp_path) as session_factory:
        await seed_item(session_factory, 1)
        run_id = await run_batch_and_complete(
            session_factory,
            [{"action": "archive_library_item", "item_id": item_id(1)}],
            advance=False,
        )
        with pytest.raises(RuntimeError):
            await advance_run(session_factory, run_id)
        rows = await operation_rows(session_factory, "run_id = :rid", {"rid": run_id})
        assert rows[0]["status"] == "PLANNED"  # 未落定＝未发生
        assert (await item_row(session_factory, 1))[2] == "ACTIVE"  # 业务写已回滚
