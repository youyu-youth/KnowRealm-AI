"""通用 Agent 第一阶段工单 01/02：统一运行时上下文、课程查询工具、页面快照与课程创建操作。

- search_courses：候选载荷/场景字段/归档与软删口径/截断明示/预算共享/未绑定分支；
- 页面快照：后端重校验（存在性/状态、失效降级）与模型上下文注入（框定为提示信息）；
- create_course（02）：结构化缺失项、每轮操作提案上限、PENDING 提案创建、
  确认应用（课程 + 索引 + result_json 原子提交）、幂等 409 与操作提案事件解析。
"""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from langchain_core.messages import ToolMessage
from pydantic import BaseModel
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
from app.modules.agent.graph import (
    ChatOperationProposalEvent,
    _operation_proposal_event,  # pyright: ignore[reportPrivateUsage]
)
from app.modules.agent.message_service import (
    _validate_page_snapshot,  # pyright: ignore[reportPrivateUsage]
)
from app.modules.agent.runtime import (
    MAX_OPERATION_PROPOSALS_PER_TURN,
    MAX_TOOL_CALLS_PER_TURN,
    AgentRuntimeContext,
    ToolCallBudget,
    bind_agent_runtime_context,
    reset_agent_runtime_context,
)
from app.modules.agent.schemas import ChatPageSnapshot, ChatRole
from app.modules.agent.tools.create_course import create_course
from app.modules.agent.tools.search_courses import (
    SEARCH_COURSES_LIMIT,
    search_courses,
)
from app.modules.library.proposals import ProposalService
from app.modules.library.schemas import (
    ProposalCreateRequest,
    ProposalListQuery,
    ProposalType,
)
from app.shared.errors import CodedHTTPException

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


# ---------------------------------------------------------------------------
# create_course 操作工具（工单 02）：公共提案入口、结构化缺失项与每轮上限
# ---------------------------------------------------------------------------


async def invoke_create_course(
    session_factory: async_sessionmaker[AsyncSession],
    args: dict[str, Any] | None = None,
    *,
    operations_created: int = 0,
) -> dict[str, Any]:
    token = bind_agent_runtime_context(
        AgentRuntimeContext(
            session_factory=session_factory,
            session_id="sess-op",
            budget=ToolCallBudget(operations_created=operations_created),
        )
    )
    try:
        raw = await create_course.ainvoke(args or {})
        return cast("dict[str, Any]", json.loads(raw))
    finally:
        reset_agent_runtime_context(token)


async def table_count(session_factory: async_sessionmaker[AsyncSession], sql: str) -> int:
    async with session_factory() as session:
        return int(cast(int, (await session.execute(text(sql))).scalar_one()))


async def proposal_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[tuple[str, str, str, str | None]]:
    """agent_proposals 全行 (id, proposal_type, status, result_json)，按创建时间序。"""
    async with session_factory() as session:
        return [
            (cast(str, row[0]), cast(str, row[1]), cast(str, row[2]), row[3])
            for row in (
                await session.execute(
                    text(
                        "SELECT id, proposal_type, status, result_json FROM agent_proposals"
                        " ORDER BY created_at, id"
                    )
                )
            ).all()
        ]


@pytest.mark.anyio
async def test_create_course_unbound_returns_structured_error() -> None:
    raw = await create_course.ainvoke({"name": "Python"})
    payload = dict(json.loads(raw))
    assert payload["ok"] is False
    assert payload["error"] == "AGENT_CONTEXT_UNBOUND"
    assert payload["proposals"] == []


def test_create_course_signature_matches_registered_payload_schema() -> None:
    """薄工具参数面与注册项 payload schema 同源的漂移防线（spec 决策 3「参数
    schema 来自注册项」的可验证表达）：字段集、类型与宽松可选性逐字段比对，
    任一侧字段增删或类型漂移即失败。"""
    from app.modules.agent.schemas import CourseCreatePayload

    # langchain 对 args_schema 的类型标注松散（实际是 pydantic 模型类）。
    args_schema = cast("type[BaseModel]", create_course.args_schema)
    assert set(args_schema.model_fields) == set(CourseCreatePayload.model_fields)
    for name, payload_field in CourseCreatePayload.model_fields.items():
        tool_field = args_schema.model_fields[name]
        # 宽松派生不变量：类型 = payload 字段类型 | None、默认 None 且非必填
        # （缺失项执法在提案创建侧，spec 决策 9）。
        annotation = payload_field.annotation
        assert annotation is not None
        assert tool_field.annotation == (annotation | None)
        assert tool_field.default is None
        assert not tool_field.is_required()


@pytest.mark.anyio
async def test_create_course_missing_required_lists_missing_fields(tmp_path: Path) -> None:
    """缺必填：工具返回结构化缺失项（模型转述追问），零提案、零课程。"""
    async with bare_db(tmp_path) as session_factory:
        payload = await invoke_create_course(session_factory)
        assert payload["ok"] is False
        assert "name" in payload["missing"]
        assert "learning_context" in payload["missing"]
        assert payload["proposals"] == []
        assert await table_count(session_factory, "SELECT count(*) FROM courses") == 0
        assert await table_count(session_factory, "SELECT count(*) FROM agent_proposals") == 0


@pytest.mark.anyio
async def test_create_course_school_missing_stage_reports_condition_detail(
    tmp_path: Path,
) -> None:
    """条件必填（学业场景须选阶段）：schema 层校验拦截并返回可转述说明。"""
    async with bare_db(tmp_path) as session_factory:
        payload = await invoke_create_course(
            session_factory,
            {"name": "高中数学", "learning_context": "SCHOOL"},
        )
        assert payload["ok"] is False
        assert payload["detail"] == "学业场景必须选择教育阶段"
        assert payload["proposals"] == []


@pytest.mark.anyio
async def test_create_course_interest_missing_depth_reports_condition_detail(
    tmp_path: Path,
) -> None:
    async with bare_db(tmp_path) as session_factory:
        payload = await invoke_create_course(
            session_factory,
            {"name": "吉他入门", "learning_context": "INTEREST"},
        )
        assert payload["ok"] is False
        assert payload["detail"] == "职业或兴趣场景必须选择学习深度"


@pytest.mark.anyio
async def test_create_course_success_creates_pending_proposal_without_course(
    tmp_path: Path,
) -> None:
    """齐全参数：创建 PENDING 提案（创建不改业务事实），课程未产生。"""
    async with bare_db(tmp_path) as session_factory:
        payload = await invoke_create_course(
            session_factory,
            {
                "name": "高中数学",
                "learning_context": "SCHOOL",
                "education_stage": "HIGH_SCHOOL",
                "course_type": "MAJOR",
                "description": "高一数学同步",
            },
        )
        assert payload["ok"] is True
        proposal = payload["proposals"][0]
        assert isinstance(proposal["proposal_id"], str)
        assert proposal["action"] == "create_course"
        assert proposal["status"] == "PENDING"
        # 学业场景归一化：depth 恒 None（与 HTTP 创建契约同源）。
        assert proposal["payload"] == {
            "name": "高中数学",
            "learning_context": "SCHOOL",
            "education_stage": "HIGH_SCHOOL",
            "depth": None,
            "course_type": "MAJOR",
            "description": "高一数学同步",
        }
        assert await table_count(session_factory, "SELECT count(*) FROM courses") == 0
        rows = await proposal_rows(session_factory)
        assert len(rows) == 1
        assert rows[0][1] == "COURSE_CREATE"
        assert rows[0][2] == "PENDING"


@pytest.mark.anyio
async def test_create_course_operation_limit_rejects_without_truncation(
    tmp_path: Path,
) -> None:
    """每轮操作提案上限：超限拒绝而非截断。"""
    async with bare_db(tmp_path) as session_factory:
        payload = await invoke_create_course(
            session_factory,
            {"name": "历史", "learning_context": "INTEREST", "depth": "BEGINNER"},
            operations_created=MAX_OPERATION_PROPOSALS_PER_TURN,
        )
        assert payload["ok"] is False
        assert payload["error"] == "OPERATION_PROPOSAL_LIMIT"
        assert payload["proposals"] == []
        assert await table_count(session_factory, "SELECT count(*) FROM agent_proposals") == 0


@pytest.mark.anyio
async def test_create_course_rejects_unknown_payload_keys(tmp_path: Path) -> None:
    """COURSE_CREATE 判别 payload 未知键拒绝（经提案创建侧执法）。"""
    async with bare_db(tmp_path) as session_factory:
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc_info:
                await ProposalService.create(
                    session,
                    ProposalCreateRequest(
                        proposal_type=ProposalType.COURSE_CREATE,
                        payload={
                            "name": "X",
                            "learning_context": "SCHOOL",
                            "education_stage": "HIGH_SCHOOL",
                            "malicious": "drop table",
                        },
                    ),
                )
        assert exc_info.value.code == "PROPOSAL_PAYLOAD_INVALID"


# ---------------------------------------------------------------------------
# COURSE_CREATE 确认与应用（工单 02）：操作回执、原子性与幂等
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_course_create_confirm_applies_writes_result_and_is_idempotent(
    tmp_path: Path,
) -> None:
    """确认 → 课程创建 + 搜索索引 + APPLIED + result_json 原子提交；双确认 409。"""
    async with bare_db(tmp_path) as session_factory:
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
                    session_id="sess-1",
                ),
            )
        # 未确认零创建。
        assert await table_count(session_factory, "SELECT count(*) FROM courses") == 0
        async with session_factory() as session:
            applied = await ProposalService.confirm(session, proposal.id)
        assert applied.status.value == "APPLIED"
        assert applied.result is not None
        course_id = applied.result["course_id"]
        assert isinstance(course_id, str)
        async with session_factory() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT name, learning_context, education_stage, depth"
                        " FROM courses WHERE id = :id"
                    ),
                    {"id": course_id},
                )
            ).one()
            assert tuple(row) == ("高中物理", "SCHOOL", "HIGH_SCHOOL", None)
        # 搜索索引同事务写入。
        indexed = await table_count(
            session_factory,
            "SELECT count(*) FROM search_index WHERE entity_type = 'course'"
            f" AND entity_id = '{course_id}'",
        )
        assert indexed == 1
        # 回执持久化（重启后可查明）。
        rows = await proposal_rows(session_factory)
        assert rows[0][2] == "APPLIED"
        assert json.loads(rows[0][3] or "{}") == {"course_id": course_id}
        # 幂等：APPLIED 终态双确认 409。
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc_info:
                await ProposalService.confirm(session, proposal.id)
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "PROPOSAL_ALREADY_DECIDED"


@pytest.mark.anyio
async def test_course_create_reject_keeps_no_business_fact(tmp_path: Path) -> None:
    """拒绝：零业务事实；REJECTED 终态再确认 409。"""
    async with bare_db(tmp_path) as session_factory:
        async with session_factory() as session:
            proposal = await ProposalService.create(
                session,
                ProposalCreateRequest(
                    proposal_type=ProposalType.COURSE_CREATE,
                    payload={
                        "name": "写作课",
                        "learning_context": "INTEREST",
                        "depth": "BEGINNER",
                    },
                ),
            )
        async with session_factory() as session:
            rejected = await ProposalService.reject(session, proposal.id)
        assert rejected.status.value == "REJECTED"
        assert await table_count(session_factory, "SELECT count(*) FROM courses") == 0
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc_info:
                await ProposalService.confirm(session, proposal.id)
        assert exc_info.value.status_code == 409


@pytest.mark.anyio
async def test_proposal_list_filters_by_session_across_statuses(tmp_path: Path) -> None:
    """列表按 session_id 过滤且不限状态（工单 02 review）：断线/重启后
    经既有提案查询恢复本会话全状态提案（含 APPLIED 回执 result）。"""
    async with bare_db(tmp_path) as session_factory:
        created: dict[str, str] = {}
        for session_key in ("sess-1", "sess-2"):
            async with session_factory() as session:
                proposal = await ProposalService.create(
                    session,
                    ProposalCreateRequest(
                        proposal_type=ProposalType.COURSE_CREATE,
                        payload={
                            "name": f"课程-{session_key}",
                            "learning_context": "SCHOOL",
                            "education_stage": "HIGH_SCHOOL",
                        },
                        session_id=session_key,
                    ),
                )
            created[session_key] = proposal.id
        async with session_factory() as session:
            await ProposalService.confirm(session, created["sess-1"])
        async with session_factory() as session:
            listing = await ProposalService.list_proposals(
                session, ProposalListQuery(session_id="sess-1")
            )
        assert [proposal.id for proposal in listing] == [created["sess-1"]]
        assert listing[0].status.value == "APPLIED"
        assert listing[0].result is not None
        assert isinstance(listing[0].result["course_id"], str)
        assert listing[0].session_id == "sess-1"


@pytest.mark.anyio
async def test_course_create_concurrent_confirm_creates_single_course(
    tmp_path: Path,
) -> None:
    """并发双确认（双击/重放的真实并发形态）：恰好一次执行、一门课程、一个 409。

    两个协程经各自独立连接真实并发（aiosqlite 线程），aclose 前的时序不
    确定——断言的是不变量：终态互斥、业务事实唯一、回执指向唯一课程。
    """
    import asyncio

    async with bare_db(tmp_path) as session_factory:
        async with session_factory() as session:
            proposal = await ProposalService.create(
                session,
                ProposalCreateRequest(
                    proposal_type=ProposalType.COURSE_CREATE,
                    payload={
                        "name": "并发物理",
                        "learning_context": "SCHOOL",
                        "education_stage": "HIGH_SCHOOL",
                    },
                ),
            )

        async def confirm_once() -> str:
            try:
                async with session_factory() as session:
                    applied = await ProposalService.confirm(session, proposal.id)
                return applied.status.value
            except CodedHTTPException as exc:
                return exc.code

        outcomes = sorted(await asyncio.gather(confirm_once(), confirm_once()))
        assert outcomes == ["APPLIED", "PROPOSAL_ALREADY_DECIDED"]
        # 业务事实唯一：无论竞态交错顺序，课程只创建一门。
        assert await table_count(session_factory, "SELECT count(*) FROM courses") == 1
        rows = await proposal_rows(session_factory)
        assert rows[0][2] == "APPLIED"
        course_id = json.loads(rows[0][3] or "{}")["course_id"]
        assert (
            await table_count(
                session_factory,
                f"SELECT count(*) FROM courses WHERE id = '{course_id}'",
            )
            == 1
        )


@pytest.mark.anyio
async def test_confirm_unknown_proposal_returns_404(tmp_path: Path) -> None:
    async with bare_db(tmp_path) as session_factory:
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc_info:
                await ProposalService.confirm(session, "nonexistent-proposal-id")
        assert exc_info.value.status_code == 404
        assert exc_info.value.code == "PROPOSAL_NOT_FOUND"


# ---------------------------------------------------------------------------
# 操作提案事件解析（工单 02）：done 载荷透传前端确认卡
# ---------------------------------------------------------------------------


def _tool_message(content: str) -> Any:
    return ToolMessage(content=content, tool_call_id="call-1", name="create_course")


def test_operation_proposal_event_narrows_payload_shape() -> None:
    body = json.dumps(
        {
            "ok": True,
            "proposals": [
                {
                    "proposal_id": "p1",
                    "action": "create_course",
                    "payload": {"name": "X", "learning_context": "SCHOOL"},
                    "status": "PENDING",
                },
                {"proposal_id": 3},
            ],
        },
        ensure_ascii=False,
    )
    event = _operation_proposal_event(_tool_message(body))
    assert isinstance(event, ChatOperationProposalEvent)
    assert event.proposals == (
        {
            "proposal_id": "p1",
            "action": "create_course",
            "payload": {"name": "X", "learning_context": "SCHOOL"},
        },
    )


def test_operation_proposal_event_ignores_failure_and_malformed() -> None:
    failure = json.dumps({"ok": False, "missing": ["name"], "proposals": []})
    assert _operation_proposal_event(_tool_message(failure)) is None
    assert _operation_proposal_event(_tool_message("not-json")) is None
    errored = ToolMessage(content="boom", tool_call_id="c2", name="create_course", status="error")
    assert _operation_proposal_event(errored) is None
