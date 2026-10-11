"""ChatTurn 安全恢复与幂等（票 02）验收：T07～T10、T12、T14、T22 与幂等框架单元。

公开 API + 真实 JobRunner（双 CHAT_TURN 槽）+ 迁移后临时 SQLite；模型用可控
替身，数据库写入 / 领取 / 业务回执 / 效果行不以 mock 替代。崩溃窗口经测试
接缝（prepare_effect / finalize_completed 的调用侧包裹）确定性构造「业务已
提交、checkpoint 未保存」「多结果第三项后」「图完成后、assistant 提交前」
三个故障窗口（规格验收证据要求）。T07 与 T12 见 test_chat_turns.py 的
test_startup_recovery_resumes_running_turn / test_interrupted_turn_resume_and_cancel。
"""

import asyncio
import json
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.db.engine import create_database
from app.db.migrations import run_migrations
from app.main import create_app
from app.modules.agent.runtime import (
    AgentRuntimeContext,
    bind_agent_runtime_context,
    reset_agent_runtime_context,
)
from app.modules.agent.turns.effects import (
    EffectExecutionError,
    ToolCallIdentity,
    bind_tool_call_identity,
    complete_effect,
    prepare_effect,
    reset_tool_call_identity,
)
from app.modules.settings.config import grant_llm_consent, save_llm_provider
from tests.test_chat_turns import (
    STUB_REPLY,
    TOKEN,
    GatedReply,
    StubChatModel,
    StubReply,
    ToolCallReply,
    create_session,
    db_rows,
    snapshot,
    submit,
    wait_running_progress,
    wait_terminal,
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@asynccontextmanager
async def recovery_app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    replies: list[StubReply] | None = None,
    patches: Callable[[pytest.MonkeyPatch], None] | None = None,
    provider: tuple[str, str, str] | None = None,
    consent: bool = True,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient, list[list[Any]]], None]:
    """provider=(base_url, api_key, model)：覆盖缺省 stub 供应商（T14 换配置）；
    consent=False 跳过外发同意授予（密钥轮换使指纹失配的现场）。"""
    captured: list[list[Any]] = []
    queue: list[StubReply] = list(replies) if replies is not None else [list(STUB_REPLY)]

    class _StubChatOpenAI(StubChatModel):
        pass

    _StubChatOpenAI.captured = captured
    _StubChatOpenAI.replies = queue
    monkeypatch.setattr("app.modules.llm.service.ChatOpenAI", _StubChatOpenAI)
    base_url, api_key, model = provider or (
        "https://stub.example.com/v1",
        "sk-test",
        "stub-chat-model",
    )
    save_llm_provider(
        tmp_path,
        base_url=base_url,
        api_key=api_key,
        model=model,
        clear_api_key=False,
    )
    # 外发同意按当前供应商授予（恢复重验前置，票 02 规格 §12）。
    if consent:
        grant_llm_consent(tmp_path)
    if patches is not None:
        patches(monkeypatch)
    app = create_app(data_dir=tmp_path, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client, captured


async def wait_stable_status(
    client: httpx.AsyncClient, turn_id: str, statuses: tuple[str, ...], timeout: float = 15.0
) -> dict[str, Any]:
    for _ in range(int(timeout / 0.1)):
        body = await snapshot(client, turn_id)
        if body["status"] in statuses:
            return body
        await asyncio.sleep(0.1)
    pytest.fail(f"轮次未达期望状态 {statuses}: {turn_id}")


# ---------------------------------------------------------------------------
# 幂等框架单元：登记 / 复用 / 指纹冲突 / 来源键唯一（迁移库直验）。


@pytest.mark.anyio
async def test_effect_prepare_complete_and_fingerprint_conflict(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    _engine, session_factory = create_database(db_path)
    from app.modules.agent.models import ChatMessage, ChatSession
    from app.modules.agent.turns.models import ChatTurn

    async with session_factory() as session, session.begin():
        chat = ChatSession(id=str(uuid4()), mode="ASK", scope="FREE")
        session.add(chat)
        await session.flush()
        user = ChatMessage(id=str(uuid4()), session_id=chat.id, role="USER", content="q")
        session.add(user)
        await session.flush()
        turn = ChatTurn(
            id=str(uuid4()),
            session_id=chat.id,
            user_message_id=user.id,
            request_id="req-eff-0001",
            request_fingerprint="f",
            status="QUEUED",
        )
        session.add(turn)
    runtime = AgentRuntimeContext(
        session_factory=session_factory, session_id=chat.id, turn_id=turn.id, turn_claim_token="c1"
    )
    token = bind_tool_call_identity(
        ToolCallIdentity(namespace=f"chat-turn-{turn.id}", logical_call_id="call-1")
    )
    try:
        # 首次：登记 PLANNED，可执行；非轮次路径的行为由调用方回退直执行。
        preparation = await prepare_effect(runtime, "propose_memory", ["a"])
        assert preparation is not None and preparation.replay is None
        async with session_factory() as session, session.begin():
            await complete_effect(
                session, runtime, "propose_memory", ["a"], result={"ok": True, "proposal_id": "p1"}
            )
        # 重放：命中已成功项，复用原结构化结果（对象 ID 稳定）。
        replay = await prepare_effect(runtime, "propose_memory", ["a"])
        assert replay is not None
        assert replay.replay == {"ok": True, "proposal_id": "p1"}
        # 同身份参数变化：拒绝执行。
        with pytest.raises(EffectExecutionError) as excinfo:
            await prepare_effect(runtime, "propose_memory", ["b"])
        assert excinfo.value.code == "EFFECT_FINGERPRINT_CONFLICT"
        # 多结果逐项：effect_index 区分来源键（第 1 项已成功，第 2 项可执行）。
        second = await prepare_effect(runtime, "propose_ingest", (1, "u1", "t1"), effect_index=1)
        assert second is not None and second.replay is None
    finally:
        reset_tool_call_identity(token)
    async with aiosqlite.connect(db_path) as connection:
        rows = await (
            await connection.execute(
                "SELECT effect_index, status FROM chat_turn_tool_effects ORDER BY effect_index"
            )
        ).fetchall()
    assert rows == [(0, "SUCCEEDED"), (1, "PLANNED")]
    await _engine.dispose()


# ---------------------------------------------------------------------------
# T08：本地业务提交后、调用结果／checkpoint 保存前崩溃 → 复用业务结果。
# 图恢复对 pending 工具调用的重放调度由 LangGraph checkpoint 语义保证（T07
# 集成路径证明图恢复续跑）；本用例在工具接缝验证同 identity 重放的复用行为：
# 效果行已提交（同事务业务）后，重放直接返回原结构化结果，不再写业务。


@dataclass
class _TurnSeed:
    session_id: str
    turn_id: str


async def _seed_turn(session_factory: Any) -> _TurnSeed:
    from app.modules.agent.models import ChatMessage, ChatSession
    from app.modules.agent.turns.models import ChatTurn

    async with session_factory() as session, session.begin():
        chat = ChatSession(id=str(uuid4()), mode="RESEARCH", scope="ALL")
        session.add(chat)
        await session.flush()
        user = ChatMessage(id=str(uuid4()), session_id=chat.id, role="USER", content="q")
        session.add(user)
        await session.flush()
        turn = ChatTurn(
            id=str(uuid4()),
            session_id=chat.id,
            user_message_id=user.id,
            request_id=f"req-{uuid4()}",
            request_fingerprint="f",
            status="RUNNING",
            claim_token="claim-test",
        )
        session.add(turn)
    return _TurnSeed(session_id=chat.id, turn_id=turn.id)


def _runtime_for(session_factory: Any, seed: _TurnSeed) -> AgentRuntimeContext:
    return AgentRuntimeContext(
        session_factory=session_factory,
        session_id=seed.session_id,
        mode="RESEARCH",
        scope="ALL",
        turn_id=seed.turn_id,
        turn_claim_token="claim-test",
    )


@pytest.mark.anyio
async def test_t08_business_committed_before_checkpoint_reuses_result(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    _engine, session_factory = create_database(db_path)
    seed = await _seed_turn(session_factory)
    from app.modules.agent.tools.propose_memory import propose_memory

    identity_token = bind_agent_runtime_context(_runtime_for(session_factory, seed))
    tool_token = bind_tool_call_identity(
        ToolCallIdentity(namespace=f"chat-turn-{seed.turn_id}", logical_call_id="call-m1")
    )
    try:
        # 首次执行（业务+效果行同事务提交＝「checkpoint 保存前」的业务事实）。
        first = json.loads(await propose_memory.ainvoke({"items": ["先看例题"]}))
        assert first["ok"] is True
        # 图恢复重放（同 identity）：复用原结构化结果，不再写业务。
        replayed = json.loads(await propose_memory.ainvoke({"items": ["先看例题"]}))
        assert replayed == first
        assert replayed["proposal_id"] == first["proposal_id"]
    finally:
        reset_tool_call_identity(tool_token)
        reset_agent_runtime_context(identity_token)
    proposals = await db_rows(
        db_path.parent, "SELECT COUNT(*) FROM agent_proposals WHERE proposal_type = 'MEMORY'"
    )
    assert proposals[0][0] == 1
    effects = await db_rows(
        db_path.parent,
        "SELECT status FROM chat_turn_tool_effects WHERE turn_id = ?",
        (seed.turn_id,),
    )
    assert effects == [("SUCCEEDED",)]
    await _engine.dispose()


# ---------------------------------------------------------------------------
# T09：五项工具第三项提交后崩溃 → 只补后两项，五项身份稳定。
# 崩溃现场＝前 3 项效果行已 SUCCEEDED（同事务业务）；恢复重放整工具调用。


@pytest.mark.anyio
async def test_t09_multi_effect_third_committed_only_completes_rest(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "knowrealm.db"
    await run_migrations(db_path)
    _engine, session_factory = create_database(db_path)
    seed = await _seed_turn(session_factory)
    from app.modules.agent.tools.propose_ingest import (
        PROPOSE_INGEST_TOOL_NAME,
        propose_ingest,
    )
    from app.modules.library.proposals import ProposalService
    from app.modules.library.schemas import ProposalCreateRequest, ProposalType

    sources = [{"url": f"https://s{i}.example.com", "title": f"来源{i}"} for i in range(5)]
    runtime = _runtime_for(session_factory, seed)
    identity_token = bind_agent_runtime_context(runtime)
    tool_token = bind_tool_call_identity(
        ToolCallIdentity(namespace=f"chat-turn-{seed.turn_id}", logical_call_id="call-i1")
    )
    try:
        # 崩溃现场：前 3 项已真实提交（业务+效果行同事务 SUCCEEDED），后 2 项
        # 未达（效果行 PLANNED 计划固定）。
        for index in range(3):
            effect_args = (index, sources[index]["url"], sources[index]["title"])
            preparation = await prepare_effect(
                runtime, PROPOSE_INGEST_TOOL_NAME, effect_args, effect_index=index
            )
            assert preparation is not None and preparation.replay is None
            async with session_factory() as session, session.begin():
                proposal = await ProposalService.create_core(
                    session,
                    ProposalCreateRequest(
                        proposal_type=ProposalType.RESEARCH_INGEST,
                        payload={
                            "url": sources[index]["url"],
                            "title": sources[index]["title"],
                            "course_id": None,
                        },
                        session_id=seed.session_id,
                    ),
                )
                await complete_effect(
                    session,
                    runtime,
                    PROPOSE_INGEST_TOOL_NAME,
                    effect_args,
                    effect_index=index,
                    result={"proposal_id": proposal.id},
                )
        # 恢复重放：同一逻辑调用整体重放——前 3 项命中复用原提案 ID，只补
        # 后 2 项；返回包含原五项身份的完整结果。
        payload = json.loads(await propose_ingest.ainvoke({"sources": sources}))
        assert payload["ok"] is True
        assert len(payload["proposals"]) == 5
        assert [entry["url"] for entry in payload["proposals"]] == [
            f"https://s{i}.example.com" for i in range(5)
        ]
        # 更晚崩溃后的再次重放：全部命中，五项身份与对象不变。
        replayed = json.loads(await propose_ingest.ainvoke({"sources": sources}))
        assert replayed == payload
    finally:
        reset_tool_call_identity(tool_token)
        reset_agent_runtime_context(identity_token)
    proposals = await db_rows(
        db_path.parent,
        "SELECT json_extract(payload_json, '$.url') FROM agent_proposals"
        " WHERE proposal_type = 'RESEARCH_INGEST'"
        " ORDER BY json_extract(payload_json, '$.url')",
    )
    assert [row[0] for row in proposals] == [f"https://s{i}.example.com" for i in range(5)]
    effects = await db_rows(
        db_path.parent,
        "SELECT effect_index, status FROM chat_turn_tool_effects WHERE turn_id = ?"
        " ORDER BY effect_index",
        (seed.turn_id,),
    )
    assert [row[0] for row in effects] == [0, 1, 2, 3, 4]
    assert all(row[1] == "SUCCEEDED" for row in effects)
    await _engine.dispose()


# ---------------------------------------------------------------------------
# T10：图已完成、最终消息未提交时崩溃 → 仅补写消息与终态，模型调用不增加。
# 崩溃现场构造：保留 checkpoint（patch adelete_thread 为 no-op）正常完成一轮，
# 再回退业务侧（assistant / 终态 / done 事件）＝「图完成、业务未提交」。


@pytest.mark.anyio
async def test_t10_graph_done_assistant_missing_backfills_without_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _keep_checkpoint(mp: pytest.MonkeyPatch) -> None:
        async def _noop_delete_thread(self: Any, _thread_id: str) -> None:
            return None

        mp.setattr(
            "langgraph.checkpoint.sqlite.aio.AsyncSqliteSaver.adelete_thread",
            _noop_delete_thread,
        )

    async with recovery_app(tmp_path, monkeypatch, patches=_keep_checkpoint) as (
        _app,
        client,
        _captured,
    ):
        session_id = await create_session(client)
        submitted = await submit(client, session_id, "图完成问题", request_id="req-t10-0001")
        turn_id = str(submitted.json()["id"])
        final = await wait_terminal(client, turn_id)
        assert final["status"] == "COMPLETED"
        # 回退业务侧＝图完成与业务提交之间的崩溃窗口（checkpoint 完整保留）。
        async with aiosqlite.connect(tmp_path / "knowrealm.db") as connection:
            await connection.execute(
                "DELETE FROM chat_messages WHERE session_id = ? AND role = 'ASSISTANT'",
                (session_id,),
            )
            await connection.execute(
                "UPDATE chat_turns SET status = 'INTERRUPTED', final_message_id = NULL,"
                " finished_at = NULL, last_seq = 0 WHERE id = ?",
                (turn_id,),
            )
            await connection.execute("DELETE FROM chat_turn_events WHERE turn_id = ?", (turn_id,))
            await connection.execute(
                "INSERT INTO processing_jobs (id, job_type, status, progress, attempts,"
                " max_attempts, input_json, created_at, updated_at)"
                " VALUES (?, 'CHAT_TURN', 'PENDING', 0, 0, 1, ?, '2026-10-10T00:00:00Z',"
                " '2026-10-10T00:00:00Z')",
                (f"job-t10-{uuid4()}", json.dumps({"turn_id": turn_id}, separators=(",", ":"))),
            )
            await connection.commit()

    async with recovery_app(tmp_path, monkeypatch) as (_app2, client2, captured2):
        resumed = await client2.post(f"/api/chat-turns/{turn_id}/resume", json={})
        assert resumed.status_code == 200
        final = await wait_terminal(client2, turn_id)
        assert final["status"] == "COMPLETED"
        assert final["output_text"] == "回答完成了"
        # 补写路径不调用模型：重启实例模型零调用（模型调用次数不增加）。
        assert captured2 == []
        assistants = await db_rows(
            tmp_path,
            "SELECT COUNT(*) FROM chat_messages WHERE session_id = ? AND role = 'ASSISTANT'",
            (session_id,),
        )
        assert assistants[0][0] == 1


# ---------------------------------------------------------------------------
# T14：供应商身份变化 → 保留输出等待；恢复原配置后 resume 继续。


@pytest.mark.anyio
async def test_t14_provider_change_waits_then_resumes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = asyncio.Event()
    replies: list[StubReply] = [GatedReply(prefix=("崩溃前",), release=gate)]
    async with recovery_app(tmp_path, monkeypatch, replies=replies) as (_app, client, _captured):
        session_id = await create_session(client)
        submitted = await submit(client, session_id, "供应商问题", request_id="req-t14-0001")
        turn_id = str(submitted.json()["id"])
        await wait_running_progress(client, turn_id, min_seq=1)

    # 崩溃后更换供应商（不同 base_url / model）再重启：恢复条件重验拦截。
    async with recovery_app(
        tmp_path,
        monkeypatch,
        provider=("https://other.example.com/v1", "sk-other", "other-model"),
    ) as (_app2, client2, _captured2):
        state = await wait_stable_status(client2, turn_id, ("WAITING_USER",))
        assert state["waiting_reason"]["kind"] == "PROVIDER_CHANGED"
        assert state["output_text"] == "崩溃前"
        # 条件未恢复：resume 明确拒绝（不静默换服务继续出网）。
        denied = await client2.post(f"/api/chat-turns/{turn_id}/resume", json={})
        assert denied.status_code == 409

    # 恢复原配置后 resume：重新排队并续跑完成（原轮次身份不变）。
    async with recovery_app(tmp_path, monkeypatch) as (_app3, client3, _captured3):
        resumed = await client3.post(f"/api/chat-turns/{turn_id}/resume", json={})
        assert resumed.status_code == 200
        final = await wait_terminal(client3, turn_id)
        assert final["status"] == "COMPLETED"
        turns = await db_rows(
            tmp_path, "SELECT COUNT(*) FROM chat_turns WHERE session_id = ?", (session_id,)
        )
        assert turns[0][0] == 1


# ---------------------------------------------------------------------------
# T14 补充：同服务换密钥使外发同意失效——无记忆轮次恢复同样重验同意
# （规格 §12「密钥或地址变化导致同意失效时，先重新确认」，codex 审查 P1）。


@pytest.mark.anyio
async def test_t14_api_key_rotation_blocks_resume_until_reconsent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = asyncio.Event()
    replies: list[StubReply] = [GatedReply(prefix=("崩溃前",), release=gate)]
    async with recovery_app(tmp_path, monkeypatch, replies=replies) as (_app, client, _captured):
        session_id = await create_session(client)
        submitted = await submit(client, session_id, "换密钥问题", request_id="req-t14b-0001")
        turn_id = str(submitted.json()["id"])
        await wait_running_progress(client, turn_id, min_seq=1)

    # 崩溃后同地址同模型换密钥、不重新授予同意：地址/模型比对放行，同意
    # 指纹失配必须拦截（凭据不落盘，密钥变化只能经同意指纹检测）。
    async with recovery_app(
        tmp_path,
        monkeypatch,
        provider=("https://stub.example.com/v1", "sk-rotated", "stub-chat-model"),
        consent=False,
    ) as (_app2, client2, _captured2):
        state = await wait_stable_status(client2, turn_id, ("WAITING_USER",))
        assert state["waiting_reason"]["kind"] == "OUTBOUND_CONSENT_REVOKED"
        assert state["output_text"] == "崩溃前"
        # 条件未恢复（同意仍指向旧密钥指纹）：resume 明确拒绝。
        denied = await client2.post(f"/api/chat-turns/{turn_id}/resume", json={})
        assert denied.status_code == 409

    # 重新授予同意（新密钥指纹）后 resume：重新排队并续跑完成。
    async with recovery_app(
        tmp_path,
        monkeypatch,
        provider=("https://stub.example.com/v1", "sk-rotated", "stub-chat-model"),
    ) as (_app3, client3, _captured3):
        resumed = await client3.post(f"/api/chat-turns/{turn_id}/resume", json={})
        assert resumed.status_code == 200
        final = await wait_terminal(client3, turn_id)
        assert final["status"] == "COMPLETED"
        turns = await db_rows(
            tmp_path, "SELECT COUNT(*) FROM chat_turns WHERE session_id = ?", (session_id,)
        )
        assert turns[0][0] == 1


# ---------------------------------------------------------------------------
# T22：预算跨恢复累计——已消耗的检索调用次数不因重启重置。


@pytest.mark.anyio
async def test_t22_budget_accumulates_across_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = asyncio.Event()
    replies: list[StubReply] = [GatedReply(prefix=("崩溃前",), release=gate)]
    async with recovery_app(tmp_path, monkeypatch, replies=replies) as (_app, client, _captured):
        session_id = await create_session(client, scope="ALL")
        submitted = await submit(client, session_id, "预算问题", request_id="req-t22-0001")
        turn_id = str(submitted.json()["id"])
        await wait_running_progress(client, turn_id, min_seq=1)
        # 直插 6 条 tool_call 事件＝首轮已把共享检索预算用满（真实事件形状）；
        # last_seq 同步推进（执行侧续跑的 seq 分配以此为准）。
        async with aiosqlite.connect(tmp_path / "knowrealm.db") as connection:
            for seq in range(2, 8):
                payload = json.dumps(
                    {"tool": "search_library", "query": "q", "tool_call_id": f"call-b{seq}"},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                await connection.execute(
                    "INSERT INTO chat_turn_events (turn_id, seq, attempt, output_revision,"
                    " type, tool_call_id, payload_json, created_at)"
                    " VALUES (?, ?, 1, 1, 'tool_call', ?, ?,"
                    " '2026-10-10T00:00:00Z')",
                    (turn_id, seq, f"call-b{seq}", payload),
                )
            await connection.execute("UPDATE chat_turns SET last_seq = 7 WHERE id = ?", (turn_id,))
            await connection.commit()

    async with recovery_app(
        tmp_path,
        monkeypatch,
        replies=[
            ToolCallReply(tool="search_library", args={"query": "再查一次"}, call_id="call-l1"),
            list(STUB_REPLY),
        ],
    ) as (_app2, client2, captured2):
        final = await wait_terminal(client2, turn_id)
        assert final["status"] == "COMPLETED"
        # 预算已恢复累计：续跑后的新检索被拒——预算上限载荷（message 提示）
        # 作为 ToolMessage 进入模型输入（事件载荷只投影 hits/ok，message 在
        # 模型侧可观察），不因重启重置为 0。
        tool_texts = [
            str(getattr(message, "content", ""))
            for messages in captured2
            for message in messages
            if type(message).__name__ == "ToolMessage"
        ]
        assert any("上限" in text for text in tool_texts), f"续跑后的检索未被预算拒绝: {tool_texts}"
