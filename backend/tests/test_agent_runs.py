"""通用 Agent 第二阶段工单 01：执行事实地基与操作历史。

- 迁移 0030：三表落地 + proposal_type OP_ 前缀通配 + 存量 APPLIED 不回填
  （新纪元起点）；
- operation 回写：确认执行同事务写 operation（run_id 空、payload 投影、
  result 回填、authorization_json），拒绝 / 失败零 operation，重试恰好一条；
- 提案框架并发加固：reject 与失败回写条件 UPDATE 抢占（终态守卫），非编码
  异常落 FAILED + INTERNAL；
- 查询与清理：runs / operations / activity 列表、run 详情、终态守卫删除、
  批量清理已结束（提案审批事实永不删）。
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

import aiosqlite
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# 导入即注册操作类型（payload schema / 应用器随操作模块注册进提案框架）；
# 元组引用钉住注册副作用，避免被 lint 判为未使用导入而误删。
import app.modules.agent.operations.course_create  # noqa: F401
import app.modules.agent.operations.text_record_add  # noqa: F401
from app.db.engine import create_database
from app.db.migrations import MIGRATIONS_DIR, run_migrations
from app.modules.agent.runs.service import RunHistoryService
from app.modules.library.proposals import ProposalService
from app.modules.library.schemas import ProposalCreateRequest, ProposalType
from app.shared.errors import CodedHTTPException

_OPERATION_REGISTRARS = (
    app.modules.agent.operations.course_create,
    app.modules.agent.operations.text_record_add,
)

NOW = "2026-09-22T08:00:00.000000Z"


@asynccontextmanager
async def bare_db(tmp_path: Path) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    _engine, session_factory = create_database(db_path)
    try:
        yield session_factory
    finally:
        await _engine.dispose()


async def table_count(session_factory: async_sessionmaker[AsyncSession], sql: str) -> int:
    async with session_factory() as session:
        return int(cast(int, (await session.execute(text(sql))).scalar_one()))


async def operation_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[tuple[str, str | None, str, str, str | None, str | None, str]]:
    """agent_operations 关键列 (action, run_id, level, status, result_json,
    authorization_json, payload_json)，按创建时间序。"""
    async with session_factory() as session:
        return [
            (
                cast(str, row[0]),
                row[1],
                cast(str, row[2]),
                cast(str, row[3]),
                row[4],
                row[5],
                cast(str, row[6]),
            )
            for row in (
                await session.execute(
                    text(
                        "SELECT action, run_id, level, status, result_json,"
                        " authorization_json, payload_json FROM agent_operations"
                        " ORDER BY created_at, id"
                    )
                )
            ).all()
        ]


async def create_course_proposal(
    session_factory: async_sessionmaker[AsyncSession], *, session_id: str | None = None
) -> str:
    async with session_factory() as session:
        proposal = await ProposalService.create(
            session,
            ProposalCreateRequest(
                proposal_type=ProposalType.COURSE_CREATE,
                payload={
                    "name": "高中物理",
                    "learning_context": "SCHOOL",
                    "education_stage": "HIGH_SCHOOL",
                },
                session_id=session_id,
            ),
        )
    return proposal.id


async def apply_migrations_upto(db_path: Path, upto: int) -> None:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    async with aiosqlite.connect(db_path) as connection:
        for path in files:
            version = int(path.name[:4])
            if version > upto:
                continue
            sql = path.read_text(encoding="utf-8")
            await connection.executescript(
                f"PRAGMA foreign_keys=OFF;\nBEGIN IMMEDIATE;\n{sql}\n"
                f"PRAGMA user_version={version};\nCOMMIT;"
            )


async def seed_run(
    session_factory: async_sessionmaker[AsyncSession],
    run_id: str,
    status: str,
) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO agent_runs (id, auth_mode, status, created_at, updated_at)"
                " VALUES (:id, 'REQUEST_APPROVAL', :status, :now, :now)"
            ),
            {"id": run_id, "status": status, "now": NOW},
        )


async def seed_step_operation(
    session_factory: async_sessionmaker[AsyncSession],
    op_id: str,
    status: str,
    *,
    run_id: str | None = None,
) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO agent_operations (id, run_id, action, level, payload_json,"
                " status, created_at, updated_at) VALUES"
                " (:id, :run_id, 'create_course', 'L1', '{}', :status, :now, :now)"
            ),
            {"id": op_id, "run_id": run_id, "status": status, "now": NOW},
        )


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# 迁移 0030：三表 + OP_ 通配 + 新纪元起点


@pytest.mark.anyio
async def test_migration_0030_new_epoch_and_op_prefix(tmp_path: Path) -> None:
    """0029 旧库带 APPLIED 存量提案升级：三表就位、OP_ 前缀通配生效、
    存量不回填（agent_operations 恒空——新纪元起点，旧回执经提案查询可达）。"""
    db_path = tmp_path / "old.db"
    await apply_migrations_upto(db_path, 29)
    async with aiosqlite.connect(db_path) as connection:
        await connection.execute(
            "INSERT INTO agent_proposals (id, proposal_type, status, payload_json,"
            " result_json, created_at, decided_at) VALUES"
            " ('p1', 'COURSE_CREATE', 'APPLIED', '{}', '{\"course_id\": \"c1\"}', 't', 't')"
        )
        await connection.commit()
    await run_migrations(db_path)
    async with aiosqlite.connect(db_path) as connection:
        version_row = await (await connection.execute("PRAGMA user_version")).fetchone()
        assert version_row is not None
        assert cast(int, version_row[0]) == 30
        for table in ("agent_runs", "agent_operations", "agent_activity"):
            exists = await (
                await connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=:t", (table,)
                )
            ).fetchone()
            assert exists is not None, table
        # 存量 APPLIED 不回填：操作历史新纪元起点。
        ops = await (await connection.execute("SELECT count(*) FROM agent_operations")).fetchone()
        assert ops is not None and cast(int, ops[0]) == 0
        # 旧回执仍可达。
        kept = await (
            await connection.execute(
                "SELECT status, result_json FROM agent_proposals WHERE id='p1'"
            )
        ).fetchone()
        assert kept == ("APPLIED", '{"course_id": "c1"}')
        # OP_ 命名空间通配 + 存量五类型白名单仍然可写。
        await connection.execute(
            "INSERT INTO agent_proposals (id, proposal_type, status, payload_json, created_at)"
            " VALUES ('p2', 'OP_COURSE_UPDATE', 'PENDING', '{}', 't')"
        )
        await connection.execute(
            "INSERT INTO agent_proposals (id, proposal_type, status, payload_json, created_at)"
            " VALUES ('p3', 'MEMORY', 'PENDING', '{}', 't')"
        )
        await connection.commit()
        try:
            await connection.execute(
                "INSERT INTO agent_proposals (id, proposal_type, status, payload_json,"
                " created_at) VALUES ('p4', 'op_bad-lower', 'PENDING', '{}', 't')"
            )
            await connection.commit()
            pytest.fail("小写 op_ 前缀应被 GLOB 拒绝（OP_ 命名空间区分大小写）")
        except aiosqlite.IntegrityError:
            pass
        fk = await (await connection.execute("PRAGMA foreign_key_check")).fetchall()
        assert fk == []


# ---------------------------------------------------------------------------
# operation 回写：确认执行同事务写 operation


@pytest.mark.anyio
async def test_confirm_course_create_writes_operation_row(tmp_path: Path) -> None:
    """确认建课 → operation 行（action/level/run_id 空/proposal 关联/payload
    投影/result 回填/授权依据/SUCCEEDED），提案 result_json 与 operation 恒等。"""
    async with bare_db(tmp_path) as session_factory:
        proposal_id = await create_course_proposal(session_factory, session_id="sess-1")
        async with session_factory() as session:
            applied = await ProposalService.confirm(session, proposal_id)
        rows = await operation_rows(session_factory)
        assert len(rows) == 1
        action, run_id, level, status, result_json, authorization_json, payload_json = rows[0]
        assert (action, run_id, level, status) == ("create_course", None, "L1", "SUCCEEDED")
        # payload 投影 = 提案载荷同值。
        assert json.loads(payload_json) == {
            "name": "高中物理",
            "learning_context": "SCHOOL",
            "education_stage": "HIGH_SCHOOL",
            "depth": None,
            "course_type": None,
            "description": None,
        }
        # result 单向投影：operation 结果与提案 result_json 恒等。
        assert applied.result is not None
        assert json.loads(cast(str, result_json)) == applied.result
        # 授权依据：档位 + 触发方式 + 会话引用（单步无 run 的授权事实载体）。
        authorization = json.loads(cast(str, authorization_json))
        assert authorization["auth_mode"] == "REQUEST_APPROVAL"
        assert authorization["trigger"] == "USER_CONFIRMED_PROPOSAL"
        assert authorization["session_id"] == "sess-1"
        async with session_factory() as session:
            linked = (
                await session.execute(
                    text("SELECT proposal_id, attempts, finished_at FROM agent_operations")
                )
            ).one()
        assert linked[0] == proposal_id
        assert (linked[1], linked[2] is not None) == (1, True)


@pytest.mark.anyio
async def test_confirm_text_record_writes_operation_row(tmp_path: Path) -> None:
    """确认文本记录同样回写 operation（公共机制复用，第二动作零适配）。"""
    from app.core.data_dir import bind_data_dir, unbind_data_dir

    course_id = "d0000000-0000-4000-8000-000000000001"
    async with bare_db(tmp_path) as session_factory:
        async with session_factory() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO courses (id, name, learning_context, depth, status,"
                    " created_at, updated_at)"
                    " VALUES (:id, '课', 'INTEREST', 'BEGINNER', 'ACTIVE', :now, :now)"
                ),
                {"id": course_id, "now": NOW},
            )
        async with session_factory() as session:
            proposal = await ProposalService.create(
                session,
                ProposalCreateRequest(
                    proposal_type=ProposalType.TEXT_RECORD_ADD,
                    payload={"course_id": course_id, "content": "学习笔记内容"},
                ),
            )
        bind_data_dir(tmp_path)
        try:
            async with session_factory() as session:
                await ProposalService.confirm(session, proposal.id)
        finally:
            unbind_data_dir()
        rows = await operation_rows(session_factory)
        assert len(rows) == 1
        assert rows[0][0] == "add_text_record_to_course"
        assert rows[0][3] == "SUCCEEDED"
        assert json.loads(cast(str, rows[0][4]))["record_id"]


@pytest.mark.anyio
async def test_reject_writes_no_operation(tmp_path: Path) -> None:
    """拒绝零业务事实：无 operation 行。"""
    async with bare_db(tmp_path) as session_factory:
        proposal_id = await create_course_proposal(session_factory)
        async with session_factory() as session:
            rejected = await ProposalService.reject(session, proposal_id)
        assert rejected.status.value == "REJECTED"
        assert await table_count(session_factory, "SELECT count(*) FROM agent_operations") == 0


@pytest.mark.anyio
async def test_failed_confirm_leaves_no_operation_retry_succeeds_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """失败＝未发生（事务回滚不落 operation）；恢复后重试恰好一条 operation。"""
    from app.modules.course.service import CourseService

    original = CourseService.create_core
    calls = {"count": 0}

    async def failing_then_ok(session: AsyncSession, payload: Any) -> Any:
        calls["count"] += 1
        if calls["count"] == 1:
            raise CodedHTTPException(
                code="TEST_COURSE_CREATE_FAILURE", status_code=503, detail="注入的应用器故障"
            )
        return await original(session, payload)

    monkeypatch.setattr(CourseService, "create_core", failing_then_ok)

    async with bare_db(tmp_path) as session_factory:
        proposal_id = await create_course_proposal(session_factory)
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException):
                await ProposalService.confirm(session, proposal_id)
        assert await table_count(session_factory, "SELECT count(*) FROM agent_operations") == 0
        assert await table_count(session_factory, "SELECT count(*) FROM courses") == 0

        monkeypatch.setattr(CourseService, "create_core", original)
        async with session_factory() as session:
            applied = await ProposalService.confirm(session, proposal_id)
        assert applied.status.value == "APPLIED"
        assert await table_count(session_factory, "SELECT count(*) FROM courses") == 1
        assert await table_count(session_factory, "SELECT count(*) FROM agent_operations") == 1


# ---------------------------------------------------------------------------
# 提案框架并发加固（Further Notes：条件 UPDATE 抢占）


@pytest.mark.anyio
async def test_concurrent_reject_vs_confirm_single_outcome(tmp_path: Path) -> None:
    """并发 reject vs confirm：终态互斥、业务事实与状态一致——
    APPLIED → 一门课程 + 一条 operation；REJECTED → 零课程零 operation。"""
    async with bare_db(tmp_path) as session_factory:
        proposal_id = await create_course_proposal(session_factory)

        async def confirm_once() -> str:
            try:
                async with session_factory() as session:
                    applied = await ProposalService.confirm(session, proposal_id)
                return applied.status.value
            except CodedHTTPException as exc:
                return exc.code

        async def reject_once() -> str:
            try:
                async with session_factory() as session:
                    rejected = await ProposalService.reject(session, proposal_id)
                return rejected.status.value
            except CodedHTTPException as exc:
                return exc.code

        outcomes = sorted(await asyncio.gather(confirm_once(), reject_once(), reject_once()))
        # 恰好一个终态判定成功，其余 409。
        assert "PROPOSAL_ALREADY_DECIDED" in outcomes
        decided = [outcome for outcome in outcomes if outcome != "PROPOSAL_ALREADY_DECIDED"]
        assert decided == ["APPLIED"] or decided == ["REJECTED"]
        if decided == ["APPLIED"]:
            assert await table_count(session_factory, "SELECT count(*) FROM courses") == 1
            assert await table_count(session_factory, "SELECT count(*) FROM agent_operations") == 1
        else:
            assert await table_count(session_factory, "SELECT count(*) FROM courses") == 0
            assert await table_count(session_factory, "SELECT count(*) FROM agent_operations") == 0
        status = await table_count(
            session_factory,
            f"SELECT count(*) FROM agent_proposals WHERE id='{proposal_id}'"
            f" AND status IN ('APPLIED', 'REJECTED')",
        )
        assert status == 1


@pytest.mark.anyio
async def test_mark_failed_never_overwrites_applied(tmp_path: Path) -> None:
    """失败回写条件抢占：提案已 APPLIED 后迟到的失败回写不覆盖回执。"""
    async with bare_db(tmp_path) as session_factory:
        proposal_id = await create_course_proposal(session_factory)
        async with session_factory() as session:
            await ProposalService.confirm(session, proposal_id)
        async with session_factory() as session:
            await ProposalService._mark_failed(  # pyright: ignore[reportPrivateUsage]
                session, proposal_id, "LATE_FAILURE"
            )
        kept = await table_count(
            session_factory,
            f"SELECT count(*) FROM agent_proposals WHERE id='{proposal_id}'"
            " AND status='APPLIED' AND error_code IS NULL",
        )
        assert kept == 1


@pytest.mark.anyio
async def test_applier_non_coded_exception_marks_failed_internal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """应用器非编码异常：原子回滚＝未发生，落 FAILED + INTERNAL 稳定错误码。"""
    from app.modules.course.service import CourseService

    async def crashing_create_core(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("注入的非编码异常")

    monkeypatch.setattr(CourseService, "create_core", crashing_create_core)

    async with bare_db(tmp_path) as session_factory:
        proposal_id = await create_course_proposal(session_factory)
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc_info:
                await ProposalService.confirm(session, proposal_id)
        assert exc_info.value.code == "PROPOSAL_APPLY_FAILED"
        assert exc_info.value.params == {"errorCode": "INTERNAL"}
        async with session_factory() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT status, error_code, result_json FROM agent_proposals WHERE id = :id"
                    ),
                    {"id": proposal_id},
                )
            ).one()
        assert tuple(row) == ("FAILED", "INTERNAL", None)
        assert await table_count(session_factory, "SELECT count(*) FROM courses") == 0
        assert await table_count(session_factory, "SELECT count(*) FROM agent_operations") == 0


# ---------------------------------------------------------------------------
# 查询与清理 API


@pytest.mark.anyio
async def test_list_runs_filter_and_pagination(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        async with session_factory() as session:
            assert await RunHistoryService.list_runs(session) == []
        await seed_run(session_factory, "r1", "COMPLETED")
        await seed_run(session_factory, "r2", "RUNNING")
        async with session_factory() as session:
            all_runs = await RunHistoryService.list_runs(session)
            assert [run["id"] for run in all_runs] == ["r1", "r2"]
            completed = await RunHistoryService.list_runs(session, status="COMPLETED")
            assert [run["id"] for run in completed] == ["r1"]
            assert completed[0]["auth_mode"] == "REQUEST_APPROVAL"
            assert completed[0]["plan"] is None
            paged = await RunHistoryService.list_runs(session, limit=1, offset=1)
            assert [run["id"] for run in paged] == ["r2"]


@pytest.mark.anyio
async def test_run_detail_with_operations(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_run(session_factory, "r1", "COMPLETED")
        await seed_step_operation(session_factory, "o1", "SUCCEEDED", run_id="r1")
        await seed_step_operation(session_factory, "o2", "FAILED", run_id="r1")
        async with session_factory() as session:
            detail = await RunHistoryService.get_run_detail(session, "r1")
        assert detail["id"] == "r1"
        assert [op["id"] for op in detail["operations"]] == ["o1", "o2"]
        assert detail["operations"][0]["action"] == "create_course"
        assert detail["operations"][0]["payload"] == {}
        with pytest.raises(CodedHTTPException) as exc_info:
            async with session_factory() as session:
                await RunHistoryService.get_run_detail(session, "missing")
        assert exc_info.value.code == "AGENT_RUN_NOT_FOUND"


@pytest.mark.anyio
async def test_list_operations_and_activity(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_step_operation(session_factory, "o1", "SUCCEEDED")
        await seed_step_operation(session_factory, "o2", "PLANNED")
        async with session_factory() as session:
            ops = await RunHistoryService.list_operations(session)
            assert [op["id"] for op in ops] == ["o1", "o2"]
            assert ops[0]["run_id"] is None
            assert ops[0]["level"] == "L1"
            succeeded = await RunHistoryService.list_operations(session, status="SUCCEEDED")
            assert [op["id"] for op in succeeded] == ["o1"]
            # activity 本票无写入者：空态。
            assert await RunHistoryService.list_activity(session) == []


@pytest.mark.anyio
async def test_delete_terminal_run_cascades_operations_keeps_proposals(
    tmp_path: Path,
) -> None:
    """终态 run 删除：run＋其 operations 级联消失；提案（审批事实）永不删。"""
    async with bare_db(tmp_path) as session_factory:
        proposal_id = await create_course_proposal(session_factory)
        async with session_factory() as session:
            await ProposalService.confirm(session, proposal_id)
        await seed_run(session_factory, "r1", "COMPLETED")
        await seed_step_operation(session_factory, "o1", "SUCCEEDED", run_id="r1")
        async with session_factory() as session:
            await RunHistoryService.delete_run_history(session, "r1")
        assert await table_count(session_factory, "SELECT count(*) FROM agent_runs") == 0
        assert (
            await table_count(
                session_factory,
                "SELECT count(*) FROM agent_operations WHERE run_id IS NOT NULL",
            )
            == 0
        )
        # 单步 operation（确认回写）与提案不受 run 清理影响。
        assert await table_count(session_factory, "SELECT count(*) FROM agent_operations") == 1
        assert await table_count(session_factory, "SELECT count(*) FROM agent_proposals") == 1


@pytest.mark.anyio
async def test_delete_active_or_missing_run_rejected(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_run(session_factory, "r1", "RUNNING")
        await seed_run(session_factory, "r2", "WAITING_USER")
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as running:
                await RunHistoryService.delete_run_history(session, "r1")
            assert running.value.code == "AGENT_RUN_NOT_FINISHED"
            assert running.value.status_code == 409
            with pytest.raises(CodedHTTPException) as waiting:
                await RunHistoryService.delete_run_history(session, "r2")
            assert waiting.value.code == "AGENT_RUN_NOT_FINISHED"
            with pytest.raises(CodedHTTPException) as missing:
                await RunHistoryService.delete_run_history(session, "missing")
            assert missing.value.code == "AGENT_RUN_NOT_FOUND"
        assert await table_count(session_factory, "SELECT count(*) FROM agent_runs") == 2


@pytest.mark.anyio
async def test_purge_finished_keeps_active_and_proposals(tmp_path: Path) -> None:
    """批量清理已结束：终态 runs（级联）＋终态单步 operations 删除，活动保留。"""
    async with bare_db(tmp_path) as session_factory:
        proposal_id = await create_course_proposal(session_factory)
        async with session_factory() as session:
            await ProposalService.confirm(session, proposal_id)
        # 终态 run ×2（各 1 条 operation）＋活动 run ×1（1 条 operation）。
        await seed_run(session_factory, "r1", "COMPLETED")
        await seed_run(session_factory, "r2", "CANCELLED")
        await seed_run(session_factory, "r3", "RUNNING")
        await seed_step_operation(session_factory, "o-r1", "SUCCEEDED", run_id="r1")
        await seed_step_operation(session_factory, "o-r2", "SKIPPED", run_id="r2")
        await seed_step_operation(session_factory, "o-r3", "PLANNED", run_id="r3")
        # 终态单步 ×1（确认回写）＋活动单步 PLANNED ×1。
        await seed_step_operation(session_factory, "o-step", "PLANNED")

        async with session_factory() as session:
            result = await RunHistoryService.purge_finished(session)
        assert result == {"runs_deleted": 2, "operations_deleted": 3}
        assert await table_count(session_factory, "SELECT count(*) FROM agent_runs") == 1
        assert await table_count(session_factory, "SELECT count(*) FROM agent_operations") == 2
        # 提案审批事实永不删。
        assert await table_count(session_factory, "SELECT count(*) FROM agent_proposals") == 1
        # 幂等：再次清理无事可做。
        async with session_factory() as session:
            again = await RunHistoryService.purge_finished(session)
        assert again == {"runs_deleted": 0, "operations_deleted": 0}
