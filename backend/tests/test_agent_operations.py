"""通用 Agent 第一阶段工单 01：统一运行时上下文、课程查询工具与页面快照。

- search_courses：候选载荷/场景字段/归档与软删口径/截断明示/预算共享/未绑定分支；
- 页面快照：后端重校验（存在性/状态、失效降级）与模型上下文注入（框定为提示信息）。
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
from app.modules.agent.context import (
    ContextRow,
    PageHint,
    build_context_messages,
    format_page_hint,
)
from app.modules.agent.message_service import (
    _validate_page_snapshot,  # pyright: ignore[reportPrivateUsage]
)
from app.modules.agent.runtime import (
    MAX_TOOL_CALLS_PER_TURN,
    AgentRuntimeContext,
    ToolCallBudget,
    bind_agent_runtime_context,
    reset_agent_runtime_context,
)
from app.modules.agent.schemas import ChatPageSnapshot, ChatRole
from app.modules.agent.tools.search_courses import (
    SEARCH_COURSES_LIMIT,
    search_courses,
)

TOKEN = "test-launch-token"
NOW = "2026-09-21T08:00:00.000000Z"


@asynccontextmanager
async def bare_db(tmp_path: Path) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    _engine, session_factory = create_database(db_path)
    try:
        yield session_factory
    finally:
        await _engine.dispose()


async def seed_course(
    session_factory: async_sessionmaker[AsyncSession],
    course_id: str,
    name: str,
    *,
    learning_context: str = "INTEREST",
    depth: str | None = "INTERMEDIATE",
    education_stage: str | None = None,
    status: str = "ACTIVE",
    deleted: bool = False,
    updated_at: str = NOW,
) -> None:
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO courses (id, name, learning_context, education_stage, depth, "
                "status, created_at, updated_at, deleted_at) "
                "VALUES (:id, :name, :context, :stage, :depth, :status, :now, :updated, :deleted)"
            ),
            {
                "id": course_id,
                "name": name,
                "context": learning_context,
                "stage": education_stage,
                "depth": depth,
                "status": status,
                "now": NOW,
                "updated": updated_at,
                "deleted": NOW if deleted else None,
            },
        )


async def invoke_search_courses(
    session_factory: async_sessionmaker[AsyncSession], query: str
) -> dict[str, Any]:
    token = bind_agent_runtime_context(
        AgentRuntimeContext(session_factory=session_factory, session_id="sess-op")
    )
    try:
        return cast("dict[str, Any]", json.loads(await search_courses.ainvoke({"query": query})))
    finally:
        reset_agent_runtime_context(token)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# search_courses 工具
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_search_courses_unbound_returns_structured_error() -> None:
    raw = await search_courses.ainvoke({"query": "Python"})
    payload = dict(json.loads(raw))
    assert payload["ok"] is False
    assert payload["error"] == "AGENT_CONTEXT_UNBOUND"
    assert payload["courses"] == []


@pytest.mark.anyio
async def test_search_courses_empty_query_rejected(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        payload = await invoke_search_courses(session_factory, "  ")
    assert payload["ok"] is False
    assert "不能为空" in str(payload["message"])


@pytest.mark.anyio
async def test_search_courses_returns_candidates_with_scene_fields(tmp_path: Path) -> None:
    """候选契约（spec 实施决策 14）：id/名称/状态/场景/阶段或深度/更新时间；
    归档课程在列（状态明示）、软删课程排除。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(
            session_factory,
            "d0000000-0000-4000-8000-000000000001",
            "Python 学习",
            learning_context="SCHOOL",
            education_stage="UNDERGRADUATE",
            depth=None,
        )
        await seed_course(
            session_factory,
            "d0000000-0000-4000-8000-000000000002",
            "Python 进阶",
            status="ARCHIVED",
        )
        await seed_course(
            session_factory,
            "d0000000-0000-4000-8000-000000000003",
            "Python 旧课",
            deleted=True,
        )
        await seed_course(
            session_factory,
            "d0000000-0000-4000-8000-000000000004",
            "线性代数",
        )
        payload = await invoke_search_courses(session_factory, "Python")
    courses = payload["courses"]
    assert len(courses) == 2
    first, second = courses[0], courses[1]
    assert first["id"] == "d0000000-0000-4000-8000-000000000001"
    assert first["name"] == "Python 学习"
    assert first["status"] == "ACTIVE"
    assert first["learning_context"] == "SCHOOL"
    assert first["stage_or_depth"] == "UNDERGRADUATE"
    assert first["updated_at"] == "2026-09-21 08:00"
    assert second["status"] == "ARCHIVED"
    assert second["stage_or_depth"] == "INTERMEDIATE"


@pytest.mark.anyio
async def test_search_courses_no_match_reports_honestly(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory, "d0000000-0000-4000-8000-000000000009", "机器学习")
        payload = await invoke_search_courses(session_factory, "不存在课程")
    assert payload["ok"] is True
    assert payload["courses"] == []
    assert "未找到" in str(payload["message"])


@pytest.mark.anyio
async def test_search_courses_truncates_with_explicit_notice(tmp_path: Path) -> None:
    """候选上限截断有明示：仅列最近更新（updated_at 降序）。"""
    async with bare_db(tmp_path) as session_factory:
        for index in range(SEARCH_COURSES_LIMIT + 1):
            await seed_course(
                session_factory,
                f"d0000000-0000-4000-8000-{index:012d}",
                f"Python 班 {index} 期",
                updated_at=f"2026-09-{index + 1:02d}T08:00:00.000000Z",
            )
        payload = await invoke_search_courses(session_factory, "Python")
    courses = payload["courses"]
    assert len(courses) == SEARCH_COURSES_LIMIT
    assert payload["truncated"] is True
    assert "仅列最近更新" in str(payload["message"])
    # 降序：最新一期（updated_at 最大）在首。
    assert courses[0]["name"] == f"Python 班 {SEARCH_COURSES_LIMIT} 期"


@pytest.mark.anyio
async def test_search_courses_shares_budget_with_retrieval(tmp_path: Path) -> None:
    """课程查询计入既有工具调用预算：达上限后拒绝执行（不触库）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory, "d0000000-0000-4000-8000-000000000001", "Python 学习")
        budget = ToolCallBudget()
        budget.calls_used = MAX_TOOL_CALLS_PER_TURN
        token = bind_agent_runtime_context(
            AgentRuntimeContext(
                session_factory=session_factory, session_id="sess-op", budget=budget
            )
        )
        try:
            payload = dict(json.loads(await search_courses.ainvoke({"query": "Python"})))
        finally:
            reset_agent_runtime_context(token)
    assert payload["courses"] == []
    assert "已达上限" in str(payload["message"])
    assert budget.calls_used == MAX_TOOL_CALLS_PER_TURN


# ---------------------------------------------------------------------------
# 页面快照：后端重校验与提示注入
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_validate_page_snapshot_variants(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        async with session_factory() as session:
            await seed_course(
                session_factory,
                "d0000000-0000-4000-8000-000000000001",
                "Python 学习",
            )
            await seed_course(
                session_factory,
                "d0000000-0000-4000-8000-000000000002",
                "已归档课程",
                status="ARCHIVED",
            )
            # 有效课程：保留引用并解析对象名。
            valid = ChatPageSnapshot(
                page_type="course",
                entity_id="d0000000-0000-4000-8000-000000000001",
                captured_at=datetime.now(UTC),
            )
            page, hint = await _validate_page_snapshot(session, valid)
            assert page is not None and page.entity_id == valid.entity_id
            assert hint is not None and hint.entity_label == "课程「Python 学习」"
            # 归档课程：存在与状态如实呈现（标签带归档态）。
            archived = ChatPageSnapshot(
                page_type="course",
                entity_id="d0000000-0000-4000-8000-000000000002",
                captured_at=datetime.now(UTC),
            )
            page, hint = await _validate_page_snapshot(session, archived)
            assert page is not None and page.entity_id == archived.entity_id
            assert hint is not None and "已归档" in str(hint.entity_label)
            # 已删除/不存在课程：失效引用静默丢弃，仅保留页面标签。
            stale = ChatPageSnapshot(
                page_type="course",
                entity_id="d0000000-0000-4000-8000-000000dead",
                captured_at=datetime.now(UTC),
            )
            page, hint = await _validate_page_snapshot(session, stale)
            assert page is not None and page.entity_id is None
            assert hint is not None and hint.entity_label is None
            # 记录页：不存在同样丢弃。
            stale_record = ChatPageSnapshot(
                page_type="record",
                entity_id="d0000000-0000-4000-8000-000000dead",
                captured_at=datetime.now(UTC),
            )
            page, hint = await _validate_page_snapshot(session, stale_record)
            assert page is not None and page.entity_id is None
            # 无快照：双双 None。
            assert await _validate_page_snapshot(session, None) == (None, None)


def test_page_hint_injection_frames_as_hint_not_instruction() -> None:
    """页面提示注入模型上下文：框定为提示信息（非指令非授权），无快照零注入。"""
    rows = [
        ContextRow(id="sys", role=ChatRole.SYSTEM, content="角色快照"),
        ContextRow(id="u1", role=ChatRole.USER, content="问题"),
    ]
    messages = build_context_messages(
        rows, page_hint=PageHint(page_type="course", entity_label="课程「Python」")
    )
    system = str(messages[0].content)
    assert "页面提示" in system
    assert "不是指令" in system and "不构成任何授权" in system
    assert "课程「Python」" in system
    # 无页面快照：既有提示面零变化（行为回归锚）。
    baseline = build_context_messages(rows)
    assert "页面提示" not in str(baseline[0].content)


def test_format_page_hint_covers_known_page_types() -> None:
    assert "AI 对话" in format_page_hint(PageHint(page_type="chat"))
    assert "当前对象" not in format_page_hint(PageHint(page_type="inbox"))
    unknown = format_page_hint(PageHint(page_type="spaces"))
    assert "spaces" in unknown
