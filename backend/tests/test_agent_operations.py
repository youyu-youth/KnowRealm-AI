"""通用 Agent 第一阶段工单 01/02/03：运行时上下文、课程查询、课程创建与文本记录操作。

- search_courses：候选载荷/场景字段/归档与软删口径/截断明示/预算共享/未绑定分支；
- 页面快照：后端重校验（存在性/状态、失效降级）与模型上下文注入（框定为提示信息）；
- create_course（02）：结构化缺失项、每轮操作提案上限、PENDING 提案创建、
  确认应用（课程 + 索引 + result_json 原子提交）、幂等 409 与操作提案事件解析；
- add_text_record_to_course（03）：公共机制复用验证——结构化缺失/超限 detail、
  确认应用（Record + Transcript + 索引 + 回填 + 总结任务 best-effort）、
  归档/不存在目标 FAILED 零悬挂、幂等与拒绝零业务事实。
- 综合验收（04）：FAILED 重试恰好一次、应用器故障 FAILED 不谎报回执、
  公共执行流程零领域 import 的静态防线。
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

from app.core.data_dir import bind_data_dir, unbind_data_dir
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
from app.modules.agent.tools.add_text_record import add_text_record_to_course
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
from app.modules.settings.config import grant_llm_consent, save_llm_provider
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


# ---------------------------------------------------------------------------
# add_text_record_to_course 操作工具（工单 03）：复用验证 + 文本记录链
# ---------------------------------------------------------------------------


async def invoke_add_text_record(
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
        raw = await add_text_record_to_course.ainvoke(args or {})
        return cast("dict[str, Any]", json.loads(raw))
    finally:
        reset_agent_runtime_context(token)


COURSE_ID = "d0000000-0000-4000-8000-000000000101"


@pytest.mark.anyio
async def test_add_text_record_unbound_returns_structured_error() -> None:
    raw = await add_text_record_to_course.ainvoke({"content": "笔记"})
    payload = dict(json.loads(raw))
    assert payload["ok"] is False
    assert payload["error"] == "AGENT_CONTEXT_UNBOUND"
    assert payload["proposals"] == []


def test_add_text_record_signature_matches_registered_payload_schema() -> None:
    """薄工具参数面与注册项 payload schema 同源的漂移防线（对齐 02 先例）。"""
    from app.modules.agent.schemas import TextRecordAddPayload

    args_schema = cast("type[BaseModel]", add_text_record_to_course.args_schema)
    assert set(args_schema.model_fields) == set(TextRecordAddPayload.model_fields)
    for name, payload_field in TextRecordAddPayload.model_fields.items():
        tool_field = args_schema.model_fields[name]
        annotation = payload_field.annotation
        assert annotation is not None
        assert tool_field.annotation == (annotation | None)
        assert tool_field.default is None
        assert not tool_field.is_required()


@pytest.mark.anyio
async def test_add_text_record_missing_required_lists_missing_fields(
    tmp_path: Path,
) -> None:
    """缺必填：结构化缺失项（模型转述追问），零提案、零记录。"""
    async with bare_db(tmp_path) as session_factory:
        payload = await invoke_add_text_record(session_factory, {"content": "笔记"})
        assert payload["ok"] is False
        assert payload["missing"] == ["course_id"]
        assert payload["proposals"] == []
        assert await table_count(session_factory, "SELECT count(*) FROM agent_proposals") == 0


@pytest.mark.anyio
async def test_add_text_record_oversized_content_reports_detail(tmp_path: Path) -> None:
    """正文超 1 MiB：结构化 detail 由模型转述替代路径，零提案。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory, COURSE_ID, "Python 学习")
        payload = await invoke_add_text_record(
            session_factory,
            {"course_id": COURSE_ID, "content": "x" * (1024 * 1024 + 1)},
        )
        assert payload["ok"] is False
        assert "1 MiB" in payload["detail"]
        assert payload["proposals"] == []
        assert await table_count(session_factory, "SELECT count(*) FROM agent_proposals") == 0


@pytest.mark.anyio
async def test_add_text_record_rejects_unknown_payload_keys(tmp_path: Path) -> None:
    """TEXT_RECORD_ADD 判别 payload 未知键拒绝（经提案创建侧执法，对齐 02 先例）。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory, COURSE_ID, "Python 学习")
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc_info:
                await ProposalService.create(
                    session,
                    ProposalCreateRequest(
                        proposal_type=ProposalType.TEXT_RECORD_ADD,
                        payload={
                            "course_id": COURSE_ID,
                            "content": "笔记",
                            "title": "自定义标题",
                        },
                    ),
                )
        assert exc_info.value.code == "PROPOSAL_PAYLOAD_INVALID"


@pytest.mark.anyio
async def test_add_text_record_success_creates_pending_proposal_without_record(
    tmp_path: Path,
) -> None:
    """调用成功 = PENDING 提案（payload 固化目标课程），确认前零记录。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory, COURSE_ID, "Python 学习")
        payload = await invoke_add_text_record(
            session_factory,
            {"course_id": COURSE_ID, "content": "傅里叶级数展开要点"},
        )
        assert payload["ok"] is True
        [proposal] = payload["proposals"]
        assert proposal["action"] == "add_text_record_to_course"
        assert proposal["status"] == "PENDING"
        assert proposal["payload"] == {"course_id": COURSE_ID, "content": "傅里叶级数展开要点"}
        assert await table_count(session_factory, "SELECT count(*) FROM records") == 0


@pytest.mark.anyio
async def test_text_record_add_confirm_applies_writes_result_and_is_idempotent(
    tmp_path: Path,
) -> None:
    """确认 → Record(SUMMARY_PENDING) + Transcript + 搜索索引 + APPLIED + result_json
    原子提交（provider 未配置 → 总结未触发，(None, None)）；双确认 409 零重复。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory, COURSE_ID, "Python 学习")
        async with session_factory() as session:
            proposal = await ProposalService.create(
                session,
                ProposalCreateRequest(
                    proposal_type=ProposalType.TEXT_RECORD_ADD,
                    payload={"course_id": COURSE_ID, "content": "首行标题\n正文第二行"},
                    session_id="sess-1",
                ),
            )
        assert await table_count(session_factory, "SELECT count(*) FROM records") == 0
        async with session_factory() as session:
            applied = await ProposalService.confirm(session, proposal.id)
        assert applied.status.value == "APPLIED"
        assert applied.result is not None
        record_id = applied.result["record_id"]
        assert isinstance(record_id, str)
        assert applied.result["summary_job_id"] is None
        assert applied.result["summary_error_code"] is None
        async with session_factory() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT course_id, capture_type, title, status FROM records WHERE id = :id"
                    ),
                    {"id": record_id},
                )
            ).one()
        assert tuple(row) == (COURSE_ID, "PASTE", "首行标题", "SUMMARY_PENDING")
        transcripts = await table_count(
            session_factory,
            f"SELECT count(*) FROM transcripts WHERE record_id = '{record_id}'",
        )
        assert transcripts == 1
        indexed = await table_count(
            session_factory,
            "SELECT count(*) FROM search_index WHERE entity_type = 'record'"
            f" AND entity_id = '{record_id}'",
        )
        assert indexed == 1
        backfilled = await table_count(
            session_factory,
            "SELECT count(*) FROM processing_jobs WHERE job_type = 'LIBRARY_BACKFILL'",
        )
        assert backfilled == 1
        rows = await proposal_rows(session_factory)
        assert json.loads(rows[0][3] or "{}") == {
            "record_id": record_id,
            "summary_job_id": None,
            "summary_error_code": None,
        }
        # 幂等：APPLIED 终态双确认 409，不重复建记录。
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc_info:
                await ProposalService.confirm(session, proposal.id)
        assert exc_info.value.status_code == 409
        assert await table_count(session_factory, "SELECT count(*) FROM records") == 1


@pytest.mark.anyio
async def test_text_record_add_confirm_with_provider_submits_summary_job(
    tmp_path: Path,
) -> None:
    """provider 已配置并同意：确认事务内 best-effort 提交总结任务，result_json
    回写真实 job id；记录与 job 同事务原子提交。"""
    applied = None
    async with bare_db(tmp_path) as session_factory:
        (tmp_path / "config").mkdir(exist_ok=True)
        save_llm_provider(
            tmp_path,
            base_url="https://api.example.com",
            api_key="sk-test",
            model="test-model",
            clear_api_key=False,
        )
        grant_llm_consent(tmp_path)
        bind_data_dir(tmp_path)
        try:
            await seed_course(session_factory, COURSE_ID, "Python 学习")
            async with session_factory() as session:
                proposal = await ProposalService.create(
                    session,
                    ProposalCreateRequest(
                        proposal_type=ProposalType.TEXT_RECORD_ADD,
                        payload={"course_id": COURSE_ID, "content": "要点笔记"},
                        session_id="sess-1",
                    ),
                )
            async with session_factory() as session:
                applied = await ProposalService.confirm(session, proposal.id)
        finally:
            unbind_data_dir()
    assert applied is not None
    assert applied.status.value == "APPLIED"
    assert applied.result is not None
    job_id = applied.result["summary_job_id"]
    assert isinstance(job_id, str)
    assert applied.result["summary_error_code"] is None


@pytest.mark.anyio
async def test_text_record_add_confirm_missing_course_fails_without_dangling_record(
    tmp_path: Path,
) -> None:
    """目标课程不存在：确认失败 → 提案 FAILED + 稳定错误码，零悬挂记录。"""
    async with bare_db(tmp_path) as session_factory:
        async with session_factory() as session:
            proposal = await ProposalService.create(
                session,
                ProposalCreateRequest(
                    proposal_type=ProposalType.TEXT_RECORD_ADD,
                    payload={"course_id": COURSE_ID, "content": "笔记"},
                    session_id="sess-1",
                ),
            )
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc_info:
                await ProposalService.confirm(session, proposal.id)
        assert exc_info.value.code == "PROPOSAL_APPLY_FAILED"
        assert exc_info.value.params == {"errorCode": "COURSE_NOT_FOUND"}
        assert await table_count(session_factory, "SELECT count(*) FROM records") == 0
        assert await table_count(session_factory, "SELECT count(*) FROM transcripts") == 0
        rows = await proposal_rows(session_factory)
        assert rows[0][2] == "FAILED"
        async with session_factory() as session:
            failed_code = (
                await session.execute(
                    text("SELECT error_code FROM agent_proposals WHERE id = :id"),
                    {"id": proposal.id},
                )
            ).scalar_one()
        assert failed_code == "COURSE_NOT_FOUND"


@pytest.mark.anyio
async def test_text_record_add_confirm_archived_course_fails(tmp_path: Path) -> None:
    """目标课程归档：沿用「归档课程不能接受新资料」语义 → FAILED、零记录。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory, COURSE_ID, "Python 学习")
        async with session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE courses SET status = 'ARCHIVED' WHERE id = :id"),
                {"id": COURSE_ID},
            )
        async with session_factory() as session:
            proposal = await ProposalService.create(
                session,
                ProposalCreateRequest(
                    proposal_type=ProposalType.TEXT_RECORD_ADD,
                    payload={"course_id": COURSE_ID, "content": "笔记"},
                    session_id="sess-1",
                ),
            )
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc_info:
                await ProposalService.confirm(session, proposal.id)
        assert exc_info.value.params == {"errorCode": "COURSE_ARCHIVED"}
        assert await table_count(session_factory, "SELECT count(*) FROM records") == 0


@pytest.mark.anyio
async def test_text_record_add_reject_keeps_no_business_fact(tmp_path: Path) -> None:
    """拒绝：零业务事实；REJECTED 终态再确认 409。"""
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory, COURSE_ID, "Python 学习")
        async with session_factory() as session:
            proposal = await ProposalService.create(
                session,
                ProposalCreateRequest(
                    proposal_type=ProposalType.TEXT_RECORD_ADD,
                    payload={"course_id": COURSE_ID, "content": "笔记"},
                    session_id="sess-1",
                ),
            )
        async with session_factory() as session:
            rejected = await ProposalService.reject(session, proposal.id)
        assert rejected.status.value == "REJECTED"
        assert await table_count(session_factory, "SELECT count(*) FROM records") == 0
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc_info:
                await ProposalService.confirm(session, proposal.id)
        assert exc_info.value.status_code == 409


@pytest.mark.anyio
async def test_text_record_add_summary_flush_failure_isolated_by_savepoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """job 写入的数据库级失败（flush 炸、session 进 rollback-only）经 SAVEPOINT
    隔离（03 review 修复）：记录与 APPLIED 回执照常提交、result 如实记总结
    提交失败——不得吞错返回指向不存在记录的半成功回执。"""
    from app.modules.jobs.models import ProcessingJob
    from app.modules.summary import service as summary_service

    def bogus_status_job(record_id: str, *, input_json: str, now: datetime) -> ProcessingJob:
        job = summary_service._new_summary_job(  # pyright: ignore[reportPrivateUsage]
            record_id, input_json=input_json, now=now
        )
        job.status = "BOGUS"  # 违反 processing_jobs.status CHECK → flush 必炸
        return job

    monkeypatch.setattr(summary_service, "_new_summary_job", bogus_status_job)

    applied = None
    async with bare_db(tmp_path) as session_factory:
        (tmp_path / "config").mkdir(exist_ok=True)
        save_llm_provider(
            tmp_path,
            base_url="https://api.example.com",
            api_key="sk-test",
            model="test-model",
            clear_api_key=False,
        )
        grant_llm_consent(tmp_path)
        bind_data_dir(tmp_path)
        try:
            await seed_course(session_factory, COURSE_ID, "Python 学习")
            async with session_factory() as session:
                proposal = await ProposalService.create(
                    session,
                    ProposalCreateRequest(
                        proposal_type=ProposalType.TEXT_RECORD_ADD,
                        payload={"course_id": COURSE_ID, "content": "要点笔记"},
                        session_id="sess-1",
                    ),
                )
            async with session_factory() as session:
                applied = await ProposalService.confirm(session, proposal.id)
        finally:
            unbind_data_dir()
        # 库内事实：记录真实存在（非半成功回执）、无 SUMMARY job 行、回执记失败码。
        assert await table_count(session_factory, "SELECT count(*) FROM records") == 1
        assert (
            await table_count(
                session_factory,
                "SELECT count(*) FROM processing_jobs WHERE job_type = 'SUMMARY'",
            )
            == 0
        )
        rows = await proposal_rows(session_factory)
        receipt = json.loads(rows[0][3] or "{}")
        assert receipt["summary_job_id"] is None
        assert receipt["summary_error_code"] == "TEXT_RECORD_ADD_SUMMARY_ENQUEUE_FAILED"
    assert applied is not None
    assert applied.status.value == "APPLIED"
    assert applied.result is not None
    assert isinstance(applied.result["record_id"], str)


@pytest.mark.anyio
async def test_text_record_add_summary_coded_failure_keeps_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """总结提交的业务性失败（带码异常，不损坏 session）：记录幸存、result 记
    总结提交失败错误码（best-effort 语义保持）。"""
    from app.modules.summary.service import SummaryService

    async def failing_enqueue(*args: Any, **kwargs: Any) -> None:
        raise CodedHTTPException(
            code="TRANSCRIPT_NOT_READY", status_code=409, detail="Transcript 尚未生成"
        )

    monkeypatch.setattr(SummaryService, "_enqueue", failing_enqueue)

    applied = None
    async with bare_db(tmp_path) as session_factory:
        (tmp_path / "config").mkdir(exist_ok=True)
        save_llm_provider(
            tmp_path,
            base_url="https://api.example.com",
            api_key="sk-test",
            model="test-model",
            clear_api_key=False,
        )
        grant_llm_consent(tmp_path)
        bind_data_dir(tmp_path)
        try:
            await seed_course(session_factory, COURSE_ID, "Python 学习")
            async with session_factory() as session:
                proposal = await ProposalService.create(
                    session,
                    ProposalCreateRequest(
                        proposal_type=ProposalType.TEXT_RECORD_ADD,
                        payload={"course_id": COURSE_ID, "content": "要点笔记"},
                        session_id="sess-1",
                    ),
                )
            async with session_factory() as session:
                applied = await ProposalService.confirm(session, proposal.id)
        finally:
            unbind_data_dir()
        assert await table_count(session_factory, "SELECT count(*) FROM records") == 1
        rows = await proposal_rows(session_factory)
        receipt = json.loads(rows[0][3] or "{}")
        assert receipt["summary_job_id"] is None
        assert receipt["summary_error_code"] == "TEXT_RECORD_ADD_SUMMARY_ENQUEUE_FAILED"
    assert applied is not None
    assert applied.status.value == "APPLIED"


# ---------------------------------------------------------------------------
# 单步可靠性综合验收（工单 04）：失败重试、应用器故障回执、公共流程扩展性防线
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_text_record_add_failed_confirm_retry_applies_exactly_once(
    tmp_path: Path,
) -> None:
    """确认失败（落 FAILED）后重试 → 恰好一条记录、一次 APPLIED、终态 409。

    「确认请求超时/失败后重试不重复创建」的 FAILED 分支；已 APPLIED 分支由
    幂等 409 与并发双确认测试覆盖（工单 04 验收：目标幂等）。
    """
    async with bare_db(tmp_path) as session_factory:
        await seed_course(session_factory, COURSE_ID, "Python 学习")
        async with session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE courses SET status = 'ARCHIVED' WHERE id = :id"),
                {"id": COURSE_ID},
            )
        async with session_factory() as session:
            proposal = await ProposalService.create(
                session,
                ProposalCreateRequest(
                    proposal_type=ProposalType.TEXT_RECORD_ADD,
                    payload={"course_id": COURSE_ID, "content": "要点笔记"},
                    session_id="sess-1",
                ),
            )
        # 第一次确认：目标已归档 → 422 + FAILED，记录零产生。
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as first:
                await ProposalService.confirm(session, proposal.id)
        assert first.value.params == {"errorCode": "COURSE_ARCHIVED"}
        assert await table_count(session_factory, "SELECT count(*) FROM records") == 0
        # 目标恢复后重试确认：APPLIED、恰好一条记录（不重复创建）。
        async with session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE courses SET status = 'ACTIVE' WHERE id = :id"),
                {"id": COURSE_ID},
            )
        async with session_factory() as session:
            retried = await ProposalService.confirm(session, proposal.id)
        assert retried.status.value == "APPLIED"
        assert retried.result is not None
        record_id = retried.result["record_id"]
        assert await table_count(session_factory, "SELECT count(*) FROM records") == 1
        assert (
            await table_count(
                session_factory,
                f"SELECT count(*) FROM records WHERE id = '{record_id}'",
            )
            == 1
        )
        # 终态后再确认 409，记录仍恰好一条。
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as third:
                await ProposalService.confirm(session, proposal.id)
        assert third.value.status_code == 409
        assert await table_count(session_factory, "SELECT count(*) FROM records") == 1


@pytest.mark.anyio
async def test_course_create_applier_failure_marks_failed_without_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """应用器异常 → 提案 FAILED + 稳定错误码，result_json 恒 NULL（回执只在
    APPLIED 时写入，失败不谎报成功）、零课程（工单 04 验收：一致性）。"""
    from app.modules.course.service import CourseService

    async def failing_create_core(*args: Any, **kwargs: Any) -> None:
        raise CodedHTTPException(
            code="TEST_COURSE_CREATE_FAILURE", status_code=503, detail="注入的应用器故障"
        )

    monkeypatch.setattr(CourseService, "create_core", failing_create_core)

    async with bare_db(tmp_path) as session_factory:
        async with session_factory() as session:
            proposal = await ProposalService.create(
                session,
                ProposalCreateRequest(
                    proposal_type=ProposalType.COURSE_CREATE,
                    payload={
                        "name": "故障课",
                        "learning_context": "INTEREST",
                        "depth": "BEGINNER",
                    },
                    session_id="sess-1",
                ),
            )
        async with session_factory() as session:
            with pytest.raises(CodedHTTPException) as exc_info:
                await ProposalService.confirm(session, proposal.id)
        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "PROPOSAL_APPLY_FAILED"
        assert exc_info.value.params == {"errorCode": "TEST_COURSE_CREATE_FAILURE"}
        assert await table_count(session_factory, "SELECT count(*) FROM courses") == 0
        rows = await proposal_rows(session_factory)
        assert rows[0][2] == "FAILED"
        assert rows[0][3] is None
        async with session_factory() as session:
            failed_code = (
                await session.execute(
                    text("SELECT error_code FROM agent_proposals WHERE id = :id"),
                    {"id": proposal.id},
                )
            ).scalar_one()
        assert failed_code == "TEST_COURSE_CREATE_FAILURE"


def test_operations_common_flow_imports_no_domain_modules() -> None:
    """公共执行流程无领域专属分支的静态防线（工单 04 验收：扩展性）。

    操作注册表与提案框架（registry / operations.__init__ / library.proposals）
    不得 import 业务领域模块——领域接入只发生在动作模块（course_create /
    text_record_add 的应用器）与提案枚举值注册，第三个动作接入时公共流程
    零改动（用例佐证：03 接入时 registry/proposals 零改动）。领域名集合从
    app/modules 目录动态枚举，未来模块增减自动适应；相对导入（from ..course
    …）按首段同样判领域。第二阶段 01 票起 runs 子包（模型 / 服务 / 查询 /
    清理）同受防线覆盖。
    """
    import ast
    import importlib

    from app.modules.agent.operations import registry

    allowed_domains = {"agent", "library"}
    # registry.__file__ 的 parents：[operations, agent, modules]——parents[2] 即域根目录。
    modules_root = Path(registry.__file__ or ".").parents[2]
    domain_names = (
        {entry.name for entry in modules_root.iterdir() if entry.is_dir()}
        - allowed_domains
        - {"__pycache__"}
    )

    def is_domain(name: str) -> bool:
        # 绝对导入按 app.modules.<域> 判；裸名/相对形态按首段判。
        parts = name.split(".")
        if parts[0] == "app":
            parts = parts[2:] if parts[1:2] == ["modules"] else []
        return bool(parts) and parts[0] in domain_names

    modules = [
        registry,
        importlib.import_module("app.modules.agent.operations"),
        importlib.import_module("app.modules.library.proposals"),
        importlib.import_module("app.modules.agent.runs.models"),
        importlib.import_module("app.modules.agent.runs.schemas"),
        importlib.import_module("app.modules.agent.runs.service"),
        importlib.import_module("app.modules.agent.runs.routes"),
    ]
    for module in modules:
        source = Path(cast(str, module.__file__)).read_text(encoding="utf-8")
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
        domain = {name for name in imported if is_domain(name)}
        assert not domain, f"{module.__name__} 引入了领域模块：{domain}"
