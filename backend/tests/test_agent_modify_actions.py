"""通用 Agent 第二阶段工单 03：修改与归档动作（执行前快照机制）。

- update_course：快照固化（提交时同事务）、确认应用（updated_at 变化 +
  operation 行快照与 before/after 回执）、预览后手动改对象 → 确认失效
  （OPERATION_SNAPSHOT_STALE，不覆盖新修改）；
- archive / restore_course：归档写路径（状态 + updated_at）、幂等守卫；
- update / archive / restore_library_item：复用 lifecycle 核心的同款链路；
- 直执行继承：AUTO_APPROVE 档 L1 动作自动直执行（注册表零改动验证）；
- ORGANIZE 纪律：propose 固化快照 + apply 重验与 before 进结果投影。

updated_at 纪律防线（spec 决策 12 显式不变量）融进各用例：seed 钉死过去
固定时刻，操作后断言 updated_at 已前进。
"""

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
from app.modules.agent.tools.archive_course import archive_course, restore_course
from app.modules.agent.tools.archive_library_item import (
    archive_library_item,
    restore_library_item,
)
from app.modules.agent.tools.update_course import update_course
from app.modules.agent.tools.update_library_item import update_library_item
from app.modules.library.proposals import ProposalService
from app.shared.errors import CodedHTTPException

NOW = "2026-09-21T08:00:00.000000Z"
COURSE_ID = "c0000000-0000-4000-8000-000000000001"
COURSE_OTHER = "c0000000-0000-4000-8000-000000000002"
ITEM_ID = "a0000000-0000-4000-8000-00000000000a"
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
    name: str = "Python 学习",
    status: str = "ACTIVE",
) -> None:
    await run_sql(
        "INSERT INTO courses (id, name, learning_context, depth, status, created_at, "
        "updated_at) VALUES (:id, :name, 'INTEREST', 'INTERMEDIATE', :status, :now, :now)",
        {"id": course_id, "name": name, "status": status, "now": NOW},
        session_factory,
    )


async def seed_item(
    session_factory: async_sessionmaker[AsyncSession],
    item_id: str = ITEM_ID,
    *,
    title: str = "生命周期条目",
    course_id: str | None = None,
    status: str = "ACTIVE",
) -> None:
    await run_sql(
        "INSERT INTO library_items (id, course_id, source_type, title, content_hash, "
        "metadata_json, status, created_at, updated_at) "
        "VALUES (:id, :course_id, 'TEXT', :title, :hash, '{}', :status, :now, :now)",
        {
            "id": item_id,
            "course_id": course_id,
            "title": title,
            "hash": f"hash-{item_id[-4:]}",
            "status": status,
            "now": NOW,
        },
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
            session_id="sess-modify",
            auth_mode=auth_mode,
            budget=ToolCallBudget(),
        )
    )
    try:
        raw = await tool.ainvoke(args)
        return dict(json.loads(raw))
    finally:
        reset_agent_runtime_context(token)


async def scalar(
    session_factory: async_sessionmaker[AsyncSession], sql: str
) -> Any:
    async with session_factory() as session:
        return (await session.execute(text(sql))).scalar_one()


async def row_one(
    session_factory: async_sessionmaker[AsyncSession], sql: str
) -> tuple[Any, ...]:
    async with session_factory() as session:
        return tuple(
            (await session.execute(text(sql))).one(),
        )


async def proposal_row(
    session_factory: async_sessionmaker[AsyncSession], proposal_id: str
) -> tuple[str, str | None, dict[str, Any] | None]:
    """提案行 (status, error_code, snapshot)。"""
    async with session_factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT status, error_code, snapshot_json FROM agent_proposals"
                    " WHERE id = :id"
                ),
                {"id": proposal_id},
            )
        ).one()
    snapshot = None
    if row[2] is not None:
        value: object = json.loads(row[2])
        snapshot = cast(dict[str, Any], value)
    return (cast(str, row[0]), row[1], snapshot)


async def operation_row(
    session_factory: async_sessionmaker[AsyncSession], proposal_id: str
) -> dict[str, Any] | None:
    async with session_factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT action, status, snapshot_json, result_json, target_type, "
                    "target_id FROM agent_operations WHERE proposal_id = :id"
                ),
                {"id": proposal_id},
            )
        ).first()
    if row is None:
        return None
    return {
        "action": row[0],
        "status": row[1],
        "snapshot": json.loads(row[2]) if row[2] else None,
        "result": json.loads(row[3]) if row[3] else None,
        "target_type": row[4],
        "target_id": row[5],
    }


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# update_course：快照固化与确认应用
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_update_course_proposal_freezes_snapshot(tmp_path: Path) -> None:
    """提交时同事务固化快照：updated_at（微秒）+ before 值 + 目标定位进提案行。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        payload = await invoke_tool(
            update_course,
            session_factory,
            {"course_id": COURSE_ID, "name": "Python 进阶"},
        )
        assert payload["ok"] is True
        proposal = payload["proposals"][0]
        assert proposal["action"] == "update_course"
        assert proposal["status"] == "PENDING"
        # 创建不改业务事实：课程名未变（updated_at 纪律锚点也在）。
        assert await scalar(
            session_factory, f"SELECT name FROM courses WHERE id = '{COURSE_ID}'"
        ) == "Python 学习"
        status, error_code, snapshot = await proposal_row(
            session_factory, proposal["proposal_id"]
        )
        assert status == "PENDING"
        assert error_code is None
        assert snapshot is not None
        assert snapshot["name"] == "Python 学习"
        assert snapshot["status"] == "ACTIVE"
        assert snapshot["learning_context"] == "INTEREST"
        # 微秒精度 ISO 快照（ISODateTime 往返后 naive、零微秒省略）。
        assert str(snapshot["updated_at"]).startswith("2026-09-21T08:00:00")


@pytest.mark.anyio
async def test_update_course_confirm_applies_with_before_after_receipt(
    tmp_path: Path,
) -> None:
    """确认应用：课程改名生效、updated_at 前进（纪律防线）、operation 行携带
    快照与 before/after 结果回执。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        payload = await invoke_tool(
            update_course,
            session_factory,
            {"course_id": COURSE_ID, "name": "Python 进阶"},
        )
        proposal_id = payload["proposals"][0]["proposal_id"]
        async with session_factory() as session:
            confirmed = await ProposalService.confirm(session, proposal_id)
        assert confirmed.status.value == "APPLIED"
        assert await scalar(
            session_factory, f"SELECT name FROM courses WHERE id = '{COURSE_ID}'"
        ) == "Python 进阶"
        # updated_at 纪律：写路径必须维护 updated_at（seed 钉死过去时刻）。
        updated_at = await scalar(
            session_factory, f"SELECT updated_at FROM courses WHERE id = '{COURSE_ID}'"
        )
        assert str(updated_at) != NOW
        # 结果投影（提案侧缓存）与 operation 行同值。
        assert confirmed.result is not None
        assert confirmed.result["before"] == {"name": "Python 学习"}
        assert confirmed.result["after"] == {"name": "Python 进阶"}
        operation = await operation_row(session_factory, proposal_id)
        assert operation is not None
        assert operation["action"] == "update_course"
        assert operation["status"] == "SUCCEEDED"
        assert operation["snapshot"] is not None
        assert operation["snapshot"]["name"] == "Python 学习"
        assert operation["result"]["after"] == {"name": "Python 进阶"}
        assert (operation["target_type"], operation["target_id"]) == (
            "course",
            COURSE_ID,
        )


@pytest.mark.anyio
async def test_update_course_stale_snapshot_fails_without_overwriting(
    tmp_path: Path,
) -> None:
    """预览后手动改过同一对象：确认失效（稳定错误码），不覆盖新修改。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        payload = await invoke_tool(
            update_course,
            session_factory,
            {"course_id": COURSE_ID, "name": "Python 进阶"},
        )
        proposal_id = payload["proposals"][0]["proposal_id"]
        # 用户在页面手动改名（旧值已变化）。
        await run_sql(
            "UPDATE courses SET name = :name, updated_at = '2026-09-22T09:00:00.000000Z' "
            "WHERE id = :id",
            {"name": "手动改的名", "id": COURSE_ID},
            session_factory,
        )
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc_info:
                await ProposalService.confirm(session, proposal_id)
        assert exc_info.value.code == "PROPOSAL_APPLY_FAILED"
        assert exc_info.value.params == {"errorCode": "OPERATION_SNAPSHOT_STALE"}
        status, error_code, _ = await proposal_row(session_factory, proposal_id)
        assert (status, error_code) == ("FAILED", "OPERATION_SNAPSHOT_STALE")
        # 新修改不被覆盖、operation 不落（未发生）。
        assert await scalar(
            session_factory, f"SELECT name FROM courses WHERE id = '{COURSE_ID}'"
        ) == "手动改的名"
        assert await operation_row(session_factory, proposal_id) is None


@pytest.mark.anyio
async def test_update_course_unknown_target_structured_error(tmp_path: Path) -> None:
    """目标不存在：提交时结构化拒绝（快照读取失败），零提案落库。"""
    async with bare_db(tmp_path) as session_factory:
        payload = await invoke_tool(
            update_course,
            session_factory,
            {"course_id": UNKNOWN_ID, "name": "X"},
        )
        assert payload["ok"] is False
        assert payload["error"] == "COURSE_NOT_FOUND"
        assert await scalar(
            session_factory, "SELECT count(*) FROM agent_proposals"
        ) == 0


@pytest.mark.anyio
async def test_update_course_blank_name_rejected_before_proposal(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        payload = await invoke_tool(
            update_course,
            session_factory,
            {"course_id": COURSE_ID, "name": "   "},
        )
        assert payload["ok"] is False
        assert payload["missing"] == ["name"]
        assert payload["proposals"] == []
        assert await scalar(session_factory, "SELECT count(*) FROM agent_proposals") == 0


# ---------------------------------------------------------------------------
# archive / restore_course：归档写路径
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_archive_course_confirm_flips_status(tmp_path: Path) -> None:
    """归档确认：状态翻转 + updated_at 前进；operation 快照固化归档前 ACTIVE。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        payload = await invoke_tool(
            archive_course, session_factory, {"course_id": COURSE_ID}
        )
        assert payload["ok"] is True
        proposal_id = payload["proposals"][0]["proposal_id"]
        _, _, snapshot = await proposal_row(session_factory, proposal_id)
        assert snapshot is not None and snapshot["status"] == "ACTIVE"
        async with session_factory() as session:
            await ProposalService.confirm(session, proposal_id)
        assert await scalar(
            session_factory, f"SELECT status FROM courses WHERE id = '{COURSE_ID}'"
        ) == "ARCHIVED"
        updated_at = await scalar(
            session_factory, f"SELECT updated_at FROM courses WHERE id = '{COURSE_ID}'"
        )
        assert str(updated_at) != NOW


@pytest.mark.anyio
async def test_archive_course_repeat_marks_failed(tmp_path: Path) -> None:
    """重复归档：领域幂等守卫拒绝（稳定错误码 → 提案 FAILED 可重试）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory, status="ARCHIVED")
        payload = await invoke_tool(
            archive_course, session_factory, {"course_id": COURSE_ID}
        )
        proposal_id = payload["proposals"][0]["proposal_id"]
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc_info:
                await ProposalService.confirm(session, proposal_id)
        assert exc_info.value.params == {"errorCode": "COURSE_ALREADY_ARCHIVED"}
        status, error_code, _ = await proposal_row(session_factory, proposal_id)
        assert (status, error_code) == ("FAILED", "COURSE_ALREADY_ARCHIVED")


@pytest.mark.anyio
async def test_restore_course_confirm_returns_active(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory, status="ARCHIVED")
        payload = await invoke_tool(
            restore_course, session_factory, {"course_id": COURSE_ID}
        )
        proposal_id = payload["proposals"][0]["proposal_id"]
        async with session_factory() as session:
            await ProposalService.confirm(session, proposal_id)
        assert await scalar(
            session_factory, f"SELECT status FROM courses WHERE id = '{COURSE_ID}'"
        ) == "ACTIVE"
        operation = await operation_row(session_factory, proposal_id)
        assert operation is not None
        result = operation["result"]
        assert result["course_id"] == COURSE_ID
        assert result["status"] == "ACTIVE"
        # 执行后版本戳（undo 版本重验用）随 result 固化。
        assert result["after_updated_at"] is not None


# ---------------------------------------------------------------------------
# update / archive / restore_library_item
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_update_library_item_confirm_renames_and_recategorizes(
    tmp_path: Path,
) -> None:
    """条目改名 + 归类：before/after 回执（title 与 course_id）、updated_at 前进。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        await seed_course(session_factory, COURSE_OTHER, name="目标课程")
        await seed_item(session_factory)
        payload = await invoke_tool(
            update_library_item,
            session_factory,
            {
                "item_id": ITEM_ID,
                "title": "新标题",
                "course_id": COURSE_OTHER,
            },
        )
        assert payload["ok"] is True
        proposal_id = payload["proposals"][0]["proposal_id"]
        async with session_factory() as session:
            confirmed = await ProposalService.confirm(session, proposal_id)
        title, course_id, updated_at = await row_one(
            session_factory,
            f"SELECT title, course_id, updated_at FROM library_items"
            f" WHERE id = '{ITEM_ID}'",
        )
        assert title == "新标题"
        assert course_id == COURSE_OTHER
        assert str(updated_at) != NOW
        assert confirmed.result is not None
        assert confirmed.result["before"] == {"title": "生命周期条目", "course_id": None}
        assert confirmed.result["after"] == {
            "title": "新标题",
            "course_id": COURSE_OTHER,
        }


@pytest.mark.anyio
async def test_update_library_item_stale_snapshot_fails(tmp_path: Path) -> None:
    """条目快照失效：预览后手动改名 → 确认失效（稳定错误码）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_item(session_factory)
        payload = await invoke_tool(
            update_library_item,
            session_factory,
            {"item_id": ITEM_ID, "title": "新标题"},
        )
        proposal_id = payload["proposals"][0]["proposal_id"]
        await run_sql(
            "UPDATE library_items SET title = :title, updated_at = "
            "'2026-09-22T10:00:00.000000Z' WHERE id = :id",
            {"title": "页面手改", "id": ITEM_ID},
            session_factory,
        )
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc_info:
                await ProposalService.confirm(session, proposal_id)
        assert exc_info.value.params == {"errorCode": "OPERATION_SNAPSHOT_STALE"}
        assert await scalar(
            session_factory, f"SELECT title FROM library_items WHERE id = '{ITEM_ID}'"
        ) == "页面手改"


@pytest.mark.anyio
async def test_archive_and_restore_library_item(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_item(session_factory)
        payload = await invoke_tool(
            archive_library_item, session_factory, {"item_id": ITEM_ID}
        )
        proposal_id = payload["proposals"][0]["proposal_id"]
        async with session_factory() as session:
            await ProposalService.confirm(session, proposal_id)
        assert await scalar(
            session_factory, f"SELECT status FROM library_items WHERE id = '{ITEM_ID}'"
        ) == "ARCHIVED"
        # 恢复：状态回到 ACTIVE + updated_at 前进。
        payload = await invoke_tool(
            restore_library_item, session_factory, {"item_id": ITEM_ID}
        )
        proposal_id = payload["proposals"][0]["proposal_id"]
        async with session_factory() as session:
            await ProposalService.confirm(session, proposal_id)
        status, updated_at = await row_one(
            session_factory,
            f"SELECT status, updated_at FROM library_items WHERE id = '{ITEM_ID}'",
        )
        assert status == "ACTIVE"
        assert str(updated_at) != NOW


@pytest.mark.anyio
async def test_archive_library_item_repeat_marks_failed(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_item(session_factory, status="ARCHIVED")
        payload = await invoke_tool(
            archive_library_item, session_factory, {"item_id": ITEM_ID}
        )
        proposal_id = payload["proposals"][0]["proposal_id"]
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc_info:
                await ProposalService.confirm(session, proposal_id)
        assert exc_info.value.params == {"errorCode": "LIBRARY_ITEM_ALREADY_ARCHIVED"}


# ---------------------------------------------------------------------------
# 直执行继承（工单 03：注册表零改动验证）
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool", "args", "target_type", "target_id", "initial_status"),
    [
        (
            update_course,
            {"course_id": COURSE_ID, "name": "自动档改名"},
            "course",
            COURSE_ID,
            "ACTIVE",
        ),
        (archive_course, {"course_id": COURSE_ID}, "course", COURSE_ID, "ACTIVE"),
        (restore_course, {"course_id": COURSE_ID}, "course", COURSE_ID, "ARCHIVED"),
        (
            update_library_item,
            {"item_id": ITEM_ID, "title": "自动档改名"},
            "library_item",
            ITEM_ID,
            "ACTIVE",
        ),
        (archive_library_item, {"item_id": ITEM_ID}, "library_item", ITEM_ID, "ACTIVE"),
        (restore_library_item, {"item_id": ITEM_ID}, "library_item", ITEM_ID, "ARCHIVED"),
    ],
)
async def test_direct_execution_records_target(
    tmp_path: Path,
    tool: Any,
    args: dict[str, Any],
    target_type: str,
    target_id: str,
    initial_status: str,
) -> None:
    async with bare_db(tmp_path) as session_factory:
        if target_type == "course":
            await seed_course(session_factory, status=initial_status)
        else:
            await seed_item(session_factory, status=initial_status)
        payload = await invoke_tool(tool, session_factory, args, auth_mode=AuthMode.AUTO_APPROVE)
        assert payload["ok"] is True
        assert await row_one(
            session_factory, "SELECT target_type, target_id FROM agent_operations"
        ) == (target_type, target_id)


@pytest.mark.anyio
async def test_failed_direct_execution_records_target(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory, status="ARCHIVED")
        payload = await invoke_tool(
            archive_course,
            session_factory,
            {"course_id": COURSE_ID},
            auth_mode=AuthMode.AUTO_APPROVE,
        )
        assert payload["error"] == "COURSE_ALREADY_ARCHIVED"
        assert await row_one(
            session_factory, "SELECT status, target_type, target_id FROM agent_operations"
        ) == ("FAILED", "course", COURSE_ID)


@pytest.mark.anyio
async def test_modify_actions_direct_execute_on_auto_approve(tmp_path: Path) -> None:
    """AUTO_APPROVE 档 L1 修改动作自动直执行：零提案、业务生效、operation 行
    携带执行前快照与授权依据——分流按注册表 level 声明继承，执行端零改动。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        payload = await invoke_tool(
            update_course,
            session_factory,
            {"course_id": COURSE_ID, "name": "自动档改名"},
            auth_mode=AuthMode.AUTO_APPROVE,
        )
        assert payload["ok"] is True
        executed = payload["executed"]
        assert executed["action"] == "update_course"
        assert executed["level"] == "L1"
        assert executed["auth_mode"] == "AUTO_APPROVE"
        assert await scalar(
            session_factory, f"SELECT name FROM courses WHERE id = '{COURSE_ID}'"
        ) == "自动档改名"
        assert await scalar(
            session_factory, "SELECT count(*) FROM agent_proposals"
        ) == 0
        async with session_factory() as session:
            op = (
                await session.execute(
                    text(
                        "SELECT status, snapshot_json, authorization_json FROM "
                        "agent_operations WHERE action = 'update_course'"
                    )
                )
            ).one()
        assert op[0] == "SUCCEEDED"
        snapshot = json.loads(op[1])
        assert snapshot["name"] == "Python 学习"
        authorization = json.loads(op[2])
        assert authorization["auth_mode"] == "AUTO_APPROVE"
        assert authorization["trigger"] == "AUTO_EXECUTED"


@pytest.mark.anyio
async def test_modify_actions_proposal_on_request_approval_kept(tmp_path: Path) -> None:
    """默认档行为零变化：修改动作照旧落提案等确认（与第一阶段一致）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory)
        payload = await invoke_tool(
            update_course,
            session_factory,
            {"course_id": COURSE_ID, "name": "默认档改名"},
        )
        assert payload["ok"] is True
        assert "proposals" in payload and "executed" not in payload
        assert await scalar(
            session_factory, f"SELECT name FROM courses WHERE id = '{COURSE_ID}'"
        ) == "Python 学习"
