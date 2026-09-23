"""通用 Agent 第二阶段工单 02：三档授权与自动执行。

- 分流纯函数：三档 × 四级矩阵（默认档恒落提案、AUTO_APPROVE 仅 L1 直执行、
  FULL_ACCESS 全直执行）；
- 工具层直执行：L1 免确认真实建课（单事务 operation＋业务结果、授权依据
  authorization_json 回填档位/指令摘录/消息引用）、失败独立小事务落
  FAILED＋稳定错误码、非编码异常 INTERNAL、预算与提案同计、降档重检不
  沿用旧授权、记忆提案任何档位原确认规则不变；
- 审计 API：全局切换改 settings.json 偏离项＋写 activity（升档不自动执行
  积压提案）、会话切换仅写 activity、会话不存在 404；
- operations 会话过滤（授权依据列 JSON 投影）与直执行回执事件解析。
"""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi import FastAPI
from langchain_core.messages import ToolMessage
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import create_database
from app.db.migrations import run_migrations
from app.main import create_app
from app.modules.agent.graph import (
    _operation_execution_event,  # pyright: ignore[reportPrivateUsage]
)
from app.modules.agent.operations.registry import (
    OperationLevel,
    should_execute_directly,
)
from app.modules.agent.runs.schemas import AuthMode
from app.modules.agent.runs.service import RunHistoryService
from app.modules.agent.runtime import (
    MAX_OPERATION_PROPOSALS_PER_TURN,
    AgentRuntimeContext,
    bind_agent_runtime_context,
    reset_agent_runtime_context,
)
from app.modules.agent.tools.create_course import create_course
from app.modules.agent.tools.propose_memory import propose_memory
from app.modules.agent.tools.search_courses import search_courses
from app.modules.library.proposals import ProposalService
from app.modules.library.schemas import ProposalCreateRequest, ProposalType
from app.modules.settings.config import AGENT_DEFAULT_AUTH_MODE_KEY
from app.shared.errors import CodedHTTPException

TOKEN = "test-launch-token"


@pytest.mark.anyio
async def test_mid_stream_downgrade_constrains_current_turn(tmp_path: Path) -> None:
    """流式生成中途降档约束本轮后续提交（spec 用户故事 6，GPT review P1）：
    档位随 runtime 在受理时固化，中途切档经会话覆盖注册表传达——同一
    runtime 的下一次提交立即回落提案等确认。"""
    from app.modules.agent.auth_mode import (
        clear_session_auth_override,
        set_session_auth_override,
    )

    session_id = "sess-mid-downgrade"
    async with bare_db(tmp_path) as session_factory:
        try:
            auto_payload = await invoke_create_course(
                session_factory, auth_mode=AuthMode.AUTO_APPROVE, session_id=session_id
            )
            assert auto_payload["executed"] is not None
            # 模拟右栏中途切档（端点审计落定后写运行时覆盖）。
            set_session_auth_override(session_id, AuthMode.REQUEST_APPROVAL)
            downgraded_payload = await invoke_create_course(
                session_factory, auth_mode=AuthMode.AUTO_APPROVE, session_id=session_id
            )
        finally:
            clear_session_auth_override(session_id)

        assert downgraded_payload["ok"] is True
        assert downgraded_payload["proposals"][0]["status"] == "PENDING"
        # 本轮恰一次直执行（降档前），降档后零新增 operation。
        operations = await table_rows(session_factory, "SELECT status FROM agent_operations")
        assert len(operations) == 1 and operations[0][0] == "SUCCEEDED"
        assert len(await table_rows(session_factory, "SELECT * FROM courses")) == 1


@pytest.mark.anyio
async def test_mid_stream_upgrade_does_not_widen_current_turn(tmp_path: Path) -> None:
    """中途升档不放宽本轮（与「升档不自动执行既有动作序列」同一安全精神）：
    本轮起点默认档 → 流中切完全访问仍落提案；下一轮（请求携带新档）直执行。"""
    from app.modules.agent.auth_mode import (
        clear_session_auth_override,
        set_session_auth_override,
    )

    session_id = "sess-mid-upgrade"
    async with bare_db(tmp_path) as session_factory:
        try:
            set_session_auth_override(session_id, AuthMode.FULL_ACCESS)
            current_turn = await invoke_create_course(
                session_factory,
                auth_mode=AuthMode.REQUEST_APPROVAL,
                session_id=session_id,
            )
            next_turn = await invoke_create_course(
                session_factory, auth_mode=AuthMode.FULL_ACCESS, session_id=session_id
            )
        finally:
            clear_session_auth_override(session_id)

        assert current_turn["proposals"][0]["status"] == "PENDING"
        assert next_turn["executed"] is not None
        assert len(await table_rows(session_factory, "SELECT * FROM agent_operations")) == 1


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@asynccontextmanager
async def bare_db(tmp_path: Path) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    _engine, session_factory = create_database(db_path)
    try:
        yield session_factory
    finally:
        await _engine.dispose()


@asynccontextmanager
async def running_app(
    data_dir: Path,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient, async_sessionmaker[AsyncSession]]]:
    app = create_app(data_dir=data_dir, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client, app.state.session_factory


COURSE_ARGS = {
    "name": "自动化物理",
    "learning_context": "INTEREST",
    "depth": "BEGINNER",
}


async def invoke_create_course(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    auth_mode: AuthMode,
    session_id: str = "sess-auth",
    instruction: str = "帮我建一门物理课",
    budget_used: int = 0,
) -> dict[str, Any]:
    """绑定指定档位 runtime 直调 create_course 薄工具，返回解析后的 JSON 载荷。"""
    runtime = AgentRuntimeContext(
        session_factory=session_factory,
        session_id=session_id,
        auth_mode=auth_mode,
        instruction_excerpt=instruction,
        message_id="msg-auth",
    )
    runtime.budget.operations_created = budget_used
    token = bind_agent_runtime_context(runtime)
    try:
        return cast("dict[str, Any]", json.loads(await create_course.ainvoke(dict(COURSE_ARGS))))
    finally:
        reset_agent_runtime_context(token)


async def table_rows(session_factory: async_sessionmaker[AsyncSession], sql: str) -> list[Any]:
    async with session_factory() as session:
        return list(cast("Any", (await session.execute(text(sql))).all()))


# ---------------------------------------------------------------------------
# 分流纯函数（spec 决策 10；后续票新动作按注册表 level 自动继承本矩阵）


def test_should_execute_directly_matrix() -> None:
    assert not should_execute_directly(AuthMode.REQUEST_APPROVAL, OperationLevel.L1)
    assert not should_execute_directly(AuthMode.REQUEST_APPROVAL, OperationLevel.L2)
    assert not should_execute_directly(AuthMode.REQUEST_APPROVAL, OperationLevel.L3)
    # AUTO_APPROVE：仅 L1 直执行；L3（删除类）恒落提案逐项确认。
    assert should_execute_directly(AuthMode.AUTO_APPROVE, OperationLevel.L1)
    assert not should_execute_directly(AuthMode.AUTO_APPROVE, OperationLevel.L2)
    assert not should_execute_directly(AuthMode.AUTO_APPROVE, OperationLevel.L3)
    # FULL_ACCESS：除禁止项外全自动（禁止项任何档位不在注册面）。
    assert should_execute_directly(AuthMode.FULL_ACCESS, OperationLevel.L1)
    assert should_execute_directly(AuthMode.FULL_ACCESS, OperationLevel.L2)
    assert should_execute_directly(AuthMode.FULL_ACCESS, OperationLevel.L3)


# ---------------------------------------------------------------------------
# 工具层直执行（直调工具，绑定统一运行时上下文）


@pytest.mark.anyio
@pytest.mark.parametrize("mode", [AuthMode.AUTO_APPROVE, AuthMode.FULL_ACCESS])
async def test_auto_mode_l1_executes_directly(tmp_path: Path, mode: AuthMode) -> None:
    """自动档 L1 免确认直执行：真实建课＋单事务写 operation（授权依据回填），
    零提案行，工具载荷返回 executed 回执六键。"""
    async with bare_db(tmp_path) as session_factory:
        payload = await invoke_create_course(session_factory, auth_mode=mode)

        assert payload["ok"] is True
        executed = cast("dict[str, Any]", payload["executed"])
        assert executed["action"] == "create_course"
        assert executed["level"] == "L1"
        assert executed["auth_mode"] == mode.value
        assert executed["payload"]["name"] == "自动化物理"
        assert isinstance(executed["result"]["course_id"], str)

        courses = await table_rows(session_factory, "SELECT id, name FROM courses")
        assert len(courses) == 1
        assert courses[0][1] == "自动化物理"
        assert await table_rows(session_factory, "SELECT * FROM agent_proposals") == []
        operations = await table_rows(
            session_factory,
            "SELECT run_id, proposal_id, status, result_json, authorization_json"
            " FROM agent_operations",
        )
        assert len(operations) == 1
        op = operations[0]
        assert op[0] is None and op[1] is None
        assert op[2] == "SUCCEEDED"
        assert (
            cast("dict[str, Any]", json.loads(cast(str, op[3])))["course_id"]
            == executed["result"]["course_id"]
        )
        authorization = cast("dict[str, Any]", json.loads(cast(str, op[4])))
        assert authorization["auth_mode"] == mode.value
        assert authorization["trigger"] == "AUTO_EXECUTED"
        assert authorization["instruction_excerpt"] == "帮我建一门物理课"
        assert authorization["session_id"] == "sess-auth"
        assert authorization["message_id"] == "msg-auth"


@pytest.mark.anyio
async def test_request_approval_defaults_to_proposal(tmp_path: Path) -> None:
    """默认档零行为变更：落 PENDING 提案、零 operation、零课程。"""
    async with bare_db(tmp_path) as session_factory:
        payload = await invoke_create_course(session_factory, auth_mode=AuthMode.REQUEST_APPROVAL)

        assert payload["ok"] is True
        assert payload["proposals"][0]["status"] == "PENDING"
        assert await table_rows(session_factory, "SELECT * FROM agent_operations") == []
        assert await table_rows(session_factory, "SELECT * FROM courses") == []


@pytest.mark.anyio
async def test_direct_execution_failure_marks_failed_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """直执行失败：业务事务回滚（零课程），独立小事务落 FAILED operation＋
    稳定错误码，工具载荷 {ok: False, error} 供模型转述。"""
    from app.modules.course.service import CourseService

    async def failing_create_core(*args: Any, **kwargs: Any) -> None:
        raise CodedHTTPException(
            code="TEST_DIRECT_EXECUTION_FAILURE", status_code=503, detail="注入故障"
        )

    monkeypatch.setattr(CourseService, "create_core", failing_create_core)

    async with bare_db(tmp_path) as session_factory:
        payload = await invoke_create_course(session_factory, auth_mode=AuthMode.AUTO_APPROVE)

        assert payload["ok"] is False
        assert payload["error"] == "TEST_DIRECT_EXECUTION_FAILURE"
        assert await table_rows(session_factory, "SELECT * FROM courses") == []
        operations = await table_rows(
            session_factory,
            "SELECT status, result_json, error_code FROM agent_operations",
        )
        assert len(operations) == 1
        assert operations[0][0] == "FAILED"
        assert operations[0][1] is None
        assert operations[0][2] == "TEST_DIRECT_EXECUTION_FAILURE"


@pytest.mark.anyio
async def test_direct_execution_internal_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """非编码异常（bug / 环境故障）同样落 FAILED＋INTERNAL 稳定错误码，
    原子回滚＝未发生（诊断不断链）。"""
    from app.modules.course.service import CourseService

    async def crashing_create_core(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("注入的未编码故障")

    monkeypatch.setattr(CourseService, "create_core", crashing_create_core)

    async with bare_db(tmp_path) as session_factory:
        payload = await invoke_create_course(session_factory, auth_mode=AuthMode.FULL_ACCESS)

        assert payload["ok"] is False
        assert payload["error"] == "INTERNAL"
        operations = await table_rows(
            session_factory, "SELECT status, error_code FROM agent_operations"
        )
        assert operations[0] == ("FAILED", "INTERNAL")


@pytest.mark.anyio
async def test_direct_execution_shares_turn_budget(tmp_path: Path) -> None:
    """每轮操作类预算上限 5 不变：提案与直执行同计，超限拒绝不截断。"""
    async with bare_db(tmp_path) as session_factory:
        payload = await invoke_create_course(
            session_factory,
            auth_mode=AuthMode.AUTO_APPROVE,
            budget_used=MAX_OPERATION_PROPOSALS_PER_TURN,
        )

        assert payload["ok"] is False
        assert payload["error"] == "OPERATION_PROPOSAL_LIMIT"
        assert await table_rows(session_factory, "SELECT * FROM agent_operations") == []
        assert await table_rows(session_factory, "SELECT * FROM courses") == []


@pytest.mark.anyio
async def test_downgrade_rechecks_authorization_next_turn(tmp_path: Path) -> None:
    """降档后后续动作重新按新档位检查授权（不沿用旧自动授权）：自动档轮直执行
    后，默认档新轮同动作回落提案等确认。"""
    async with bare_db(tmp_path) as session_factory:
        auto_payload = await invoke_create_course(
            session_factory, auth_mode=AuthMode.AUTO_APPROVE, session_id="sess-turn1"
        )
        default_payload = await invoke_create_course(
            session_factory, auth_mode=AuthMode.REQUEST_APPROVAL, session_id="sess-turn2"
        )

        assert auto_payload["executed"] is not None
        assert default_payload["proposals"][0]["status"] == "PENDING"
        operations = await table_rows(session_factory, "SELECT status FROM agent_operations")
        assert len(operations) == 1 and operations[0][0] == "SUCCEEDED"
        assert len(await table_rows(session_factory, "SELECT * FROM courses")) == 1


@pytest.mark.anyio
async def test_memory_proposal_unchanged_under_auto_mode(tmp_path: Path) -> None:
    """长期 Memory 写入在任何档位走原确认规则（spec 用户故事 9）：AUTO_APPROVE
    下 propose_memory 仍落 PENDING 记忆提案，不经直执行。"""
    async with bare_db(tmp_path) as session_factory:
        runtime = AgentRuntimeContext(
            session_factory=session_factory,
            session_id="sess-memory",
            auth_mode=AuthMode.FULL_ACCESS,
        )
        token = bind_agent_runtime_context(runtime)
        try:
            payload = dict(
                cast(
                    "dict[str, Any]",
                    json.loads(await propose_memory.ainvoke({"items": ["先看例题"]})),
                )
            )
        finally:
            reset_agent_runtime_context(token)

        assert payload["ok"] is True
        assert payload["status"] == "PENDING"
        proposals = await table_rows(
            session_factory, "SELECT proposal_type, status FROM agent_proposals"
        )
        assert proposals[0] == ("MEMORY", "PENDING")
        assert await table_rows(session_factory, "SELECT * FROM agent_operations") == []


@pytest.mark.anyio
async def test_read_tools_unaffected_by_auto_mode(tmp_path: Path) -> None:
    """L0 读取恒自动（spec 决策 10）：自动档下检索类工具行为与默认档一致，
    不产生任何操作事实。"""
    async with bare_db(tmp_path) as session_factory:
        runtime = AgentRuntimeContext(
            session_factory=session_factory,
            session_id="sess-read",
            auth_mode=AuthMode.FULL_ACCESS,
        )
        token = bind_agent_runtime_context(runtime)
        try:
            payload = cast(
                "dict[str, Any]",
                json.loads(await search_courses.ainvoke({"query": "物理"})),
            )
        finally:
            reset_agent_runtime_context(token)

        assert payload["ok"] is True
        assert payload["courses"] == []
        assert await table_rows(session_factory, "SELECT * FROM agent_operations") == []
        assert await table_rows(session_factory, "SELECT * FROM agent_proposals") == []


# ---------------------------------------------------------------------------
# 直执行回执事件解析（graph 层，防御性收窄同提案事件口径）


def _tool_message(content: str) -> ToolMessage:
    return ToolMessage(content=content, name="create_course", tool_call_id="tc-1")


def test_operation_execution_event_parses_executed_payload() -> None:
    content = json.dumps(
        {
            "ok": True,
            "executed": {
                "operation_id": "op-1",
                "action": "create_course",
                "level": "L1",
                "auth_mode": "AUTO_APPROVE",
                "payload": {"name": "物理"},
                "result": {"course_id": "c-1"},
            },
        }
    )
    event = _operation_execution_event(_tool_message(content))
    assert event is not None
    assert event.executions[0]["operation_id"] == "op-1"
    assert event.executions[0]["auth_mode"] == "AUTO_APPROVE"


def test_operation_execution_event_drops_malformed_payload() -> None:
    # ok=False（直执行失败）与缺键形状均不产事件（失败经 tool_result 通道呈现）。
    assert _operation_execution_event(_tool_message('{"ok": false}')) is None
    assert (
        _operation_execution_event(
            _tool_message('{"ok": true, "executed": {"operation_id": "op-1"}}')
        )
        is None
    )
    assert _operation_execution_event(_tool_message("not json")) is None


# ---------------------------------------------------------------------------
# 审计 API：全局切换 / 会话切换 / operations 会话过滤


async def read_settings_json(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "config" / "settings.json"
    if not path.exists():
        return {}
    value: object = json.loads(path.read_text(encoding="utf-8"))
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


@pytest.mark.anyio
async def test_global_auth_mode_switch_writes_settings_and_activity(
    tmp_path: Path,
) -> None:
    """全局切换：settings.json 偏离项（默认档删键）＋activity 审计行；切 FULL_ACCESS
    不自动执行积压提案（升档只影响后续新提交）。"""
    data_dir = tmp_path / "KnowRealm"
    async with running_app(data_dir) as (_app, client, session_factory):
        initial = await client.get("/api/agent/auth-mode")
        assert initial.status_code == 200
        assert initial.json()["auth_mode"] == "REQUEST_APPROVAL"
        assert AGENT_DEFAULT_AUTH_MODE_KEY not in await read_settings_json(data_dir)

        # 积压提案：切档前创建 PENDING。
        async with session_factory() as session:
            backlog = await ProposalService.create(
                session,
                ProposalCreateRequest(
                    proposal_type=ProposalType.COURSE_CREATE,
                    payload=dict(COURSE_ARGS),
                    session_id="sess-backlog",
                ),
            )

        switched = await client.put(
            "/api/agent/auth-mode",
            json={"to_mode": "FULL_ACCESS"},
        )
        assert switched.status_code == 200
        assert switched.json()["auth_mode"] == "FULL_ACCESS"
        settings = await read_settings_json(data_dir)
        assert settings.get(AGENT_DEFAULT_AUTH_MODE_KEY) == "FULL_ACCESS"

        activities = await table_rows(
            session_factory,
            "SELECT activity_type, from_mode, to_mode, scope, session_id FROM agent_activity",
        )
        assert activities == [
            ("AUTH_MODE_SWITCH", "REQUEST_APPROVAL", "FULL_ACCESS", "GLOBAL", None)
        ]

        # 升档不自动执行积压提案：仍 PENDING、零 operation。
        rows = await table_rows(
            session_factory,
            f"SELECT status FROM agent_proposals WHERE id = '{backlog.id}'",
        )
        assert rows == [("PENDING",)]
        assert await table_rows(session_factory, "SELECT * FROM agent_operations") == []

        # 切回默认档：偏离键删除（settings.json 只存偏离项）＋第二条审计行
        # （from 由后端自读当前值 FULL_ACCESS）。
        reverted = await client.put(
            "/api/agent/auth-mode",
            json={"to_mode": "REQUEST_APPROVAL"},
        )
        assert reverted.status_code == 200
        assert AGENT_DEFAULT_AUTH_MODE_KEY not in await read_settings_json(data_dir)
        assert len(await table_rows(session_factory, "SELECT * FROM agent_activity")) == 2


@pytest.mark.anyio
async def test_session_auth_mode_switch_writes_activity_only(tmp_path: Path) -> None:
    """会话切换仅写 activity（scope=SESSION＋会话 id），不改全局默认；
    会话不存在拒绝写审计。"""
    data_dir = tmp_path / "KnowRealm"
    async with running_app(data_dir) as (_app, client, session_factory):
        async with session_factory() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO chat_sessions (id, mode, scope, created_at, updated_at)"
                    " VALUES ('sess-live', 'ASK', 'FREE', '2026-09-23T08:00:00.000000Z',"
                    " '2026-09-23T08:00:00.000000Z')"
                )
            )

        ok = await client.post(
            "/api/agent/auth-mode/sessions",
            json={
                "session_id": "sess-live",
                "from_mode": "REQUEST_APPROVAL",
                "to_mode": "AUTO_APPROVE",
            },
        )
        assert ok.status_code == 204
        assert AGENT_DEFAULT_AUTH_MODE_KEY not in await read_settings_json(data_dir)
        # 切档端点同步写运行时覆盖：在途流的后续提交立即按新档检查授权。
        from app.modules.agent.auth_mode import (
            clear_session_auth_override,
            effective_session_auth_mode,
        )

        try:
            # 覆盖已写入：同档起点下生效档＝to_mode（收紧语义由工具层
            # 升/降档用例单独断言）。
            assert (
                effective_session_auth_mode("sess-live", AuthMode.AUTO_APPROVE)
                == AuthMode.AUTO_APPROVE
            )
        finally:
            clear_session_auth_override("sess-live")
        activities = await table_rows(
            session_factory,
            "SELECT activity_type, from_mode, to_mode, scope, session_id FROM agent_activity",
        )
        assert activities == [
            ("AUTH_MODE_SWITCH", "REQUEST_APPROVAL", "AUTO_APPROVE", "SESSION", "sess-live")
        ]

        missing = await client.post(
            "/api/agent/auth-mode/sessions",
            json={
                "session_id": "sess-gone",
                "from_mode": "REQUEST_APPROVAL",
                "to_mode": "AUTO_APPROVE",
            },
        )
        assert missing.status_code == 404
        assert missing.json()["code"] == "CHAT_SESSION_NOT_FOUND"
        assert len(await table_rows(session_factory, "SELECT * FROM agent_activity")) == 1


@pytest.mark.anyio
async def test_list_operations_filters_by_session(tmp_path: Path) -> None:
    """operations 会话过滤（回执卡恢复链数据源）：授权依据列 JSON 投影命中，
    其他会话直执行与确认路径回写的行不串扰。"""
    async with bare_db(tmp_path) as session_factory:
        await invoke_create_course(
            session_factory, auth_mode=AuthMode.AUTO_APPROVE, session_id="sess-a"
        )
        await invoke_create_course(
            session_factory, auth_mode=AuthMode.FULL_ACCESS, session_id="sess-b"
        )

        async with session_factory() as session:
            scoped = await RunHistoryService.list_operations(session, session_id="sess-a")
            assert len(scoped) == 1
            assert scoped[0]["action"] == "create_course"
            assert cast("dict[str, Any]", scoped[0]["authorization"])["session_id"] == "sess-a"
            everything = await RunHistoryService.list_operations(session)
        assert len(everything) == 2
