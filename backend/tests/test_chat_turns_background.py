"""票 03：真实图/JobRunner/领域 worker/SQLite，只有模型与网络用替身。"""

import asyncio
import json
import sqlite3
import subprocess
import sys
import time
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from langchain_core.messages import ToolMessage
from langchain_core.outputs import ChatGenerationChunk
from sqlalchemy import text
from test_agent_run_waiting import bare_db, invoke_plan
from test_chat_turns import (
    StubChatModel,
    StubReply,
    ToolCallReply,
    create_session,
    drain_events,
    snapshot,
    submit,
    turns_app,
    wait_terminal,
)
from test_chat_turns_recovery import _seed_turn  # pyright: ignore[reportPrivateUsage]
from test_server_process import wait_for_sidecar

from app.modules.capture.web_clip import ClipContent, WebClipError
from app.modules.settings.config import grant_llm_consent, save_llm_provider


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


PLAN = [{"action": "ingest_library_item", "url": "https://example.com/background"}]


@pytest.mark.anyio
async def test_cancel_before_preflight_wait_cannot_leave_active_turn(
    tmp_path: Path,
) -> None:
    from app.modules.agent.turns.schemas import ChatTurnWaitingKind
    from app.modules.agent.turns.service import ChatTurnService

    async with bare_db(tmp_path) as session_factory:
        seed = await _seed_turn(session_factory)
        async with session_factory() as session, session.begin():
            await session.execute(text("UPDATE chat_turns SET cancel_requested=1"))
        assert await ChatTurnService.finalize_waiting(
            session_factory=session_factory,
            turn_id=seed.turn_id,
            claim_token="claim-test",
            kind=ChatTurnWaitingKind.PROVIDER_CHANGED,
            detail="供应商变更",
        )
        saved = await ChatTurnService.get_snapshot(session_factory, seed.turn_id)
        assert saved is not None and saved.status == "CANCELLED"


@pytest.mark.anyio
async def test_t18_completed_answer_leaves_run_under_existing_control(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = asyncio.Event()
    fetched = asyncio.Event()

    async def fetch(_self: object, url: str) -> ClipContent:
        fetched.set()
        await release.wait()
        return ClipContent(text="独立任务成果。" * 40, title="独立", metadata={"url": url})

    monkeypatch.setattr("app.modules.capture.web_clip.WebClipAdapter.fetch_and_extract", fetch)
    async with turns_app(
        tmp_path,
        monkeypatch,
        replies=[
            ToolCallReply("plan_batch_operations", {"items": PLAN}),
            ["已创建任务"],
        ],
    ) as (_, client, _):
        session_id = await create_session(client)
        turn_id = (
            await submit(
                client,
                session_id,
                "导入资料",
                request_id="independent-run-001",
                auth_mode="FULL_ACCESS",
            )
        ).json()["id"]
        completed = await wait_terminal(client, turn_id)
        await asyncio.wait_for(fetched.wait(), 5)
        task = completed["background_tasks"][0]
        assert task["control_scope"] == "INDEPENDENT"
        assert (await client.post(f"/api/chat-turns/{turn_id}/cancel")).status_code == 200
        run_id = task["target_id"]
        assert not (await client.get(f"/api/agent/runs/{run_id}")).json()["cancel_requested"]
        assert (await client.post(f"/api/agent/runs/{run_id}/cancel")).status_code == 200
        assert (await snapshot(client, turn_id))["status"] == "COMPLETED"
        release.set()


def install_wait_model(monkeypatch: pytest.MonkeyPatch, model: type[StubChatModel]) -> None:
    class WaitingModel(model):
        async def _astream(
            self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
        ) -> AsyncIterator[ChatGenerationChunk]:
            pending = type(self).replies[0]
            if isinstance(pending, ToolCallReply) and pending.tool == "wait_for_task":
                previous = next(m for m in reversed(messages) if isinstance(m, ToolMessage))
                body = json.loads(str(previous.content))
                run_id = body["run"]["run_id"]
                type(self).replies[0] = ToolCallReply(
                    "wait_for_task", {"target_type": "RUN", "target_id": run_id}, "wait-call"
                )
            async for chunk in super()._astream(messages, stop, run_manager, **kwargs):
                yield chunk

    monkeypatch.setattr("app.modules.llm.service.ChatOpenAI", WaitingModel)


async def wait_status(client: httpx.AsyncClient, turn_id: str, status: str) -> dict[str, Any]:
    body: dict[str, Any] = {}
    for _ in range(150):
        body = await snapshot(client, turn_id)
        if body["status"] == status:
            return body
        assert body["status"] not in ("FAILED", "CANCELLED"), body
        await asyncio.sleep(0.1)
    pytest.fail(f"未达到 {status}: {body}")


@pytest.mark.anyio
@pytest.mark.parametrize("restart", [False, True])
async def test_wait_resume_preserves_proposals_and_execution_anchors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, restart: bool
) -> None:
    from app.modules.llm import service as llm_service

    release = asyncio.Event()

    async def fetch(_self: object, url: str) -> ClipContent:
        await release.wait()
        return ClipContent(text="后台正文。" * 40, title="资料", metadata={"url": url})

    monkeypatch.setattr("app.modules.capture.web_clip.WebClipAdapter.fetch_and_extract", fetch)
    continuation: list[StubReply] = [
        ToolCallReply("propose_memory", {"items": ["等待前的偏好"]}, "memory-before"),
        ToolCallReply("propose_memory", {"items": ["接续后的偏好"]}, "memory-after"),
        ToolCallReply(
            "create_course",
            {"name": "接续后的课程", "learning_context": "INTEREST", "depth": "BEGINNER"},
            "course-after",
        ),
        ["结果已完成"],
    ]
    async with AsyncExitStack() as stack:
        app, client, captured = await stack.enter_async_context(
            turns_app(
                tmp_path,
                monkeypatch,
                replies=[
                    ToolCallReply(
                        "create_course",
                        {
                            "name": "等待前的课程",
                            "learning_context": "INTEREST",
                            "depth": "BEGINNER",
                        },
                        "course-before",
                    ),
                    ToolCallReply("propose_memory", {"items": ["等待前的偏好"]}, "memory-before"),
                    ToolCallReply(
                        "propose_ingest",
                        {"sources": [{"url": "https://example.com/proposal", "title": "候选资料"}]},
                        "research-before",
                    ),
                    ToolCallReply("plan_batch_operations", {"items": PLAN}, "plan-call"),
                    ToolCallReply("wait_for_task", {}),
                    *continuation,
                ],
            )
        )
        install_wait_model(monkeypatch, cast(type[StubChatModel], llm_service.ChatOpenAI))
        session_id = await create_session(client, mode="RESEARCH", scope="ALL")
        turn_id = (
            await submit(
                client,
                session_id,
                "创建并等待",
                request_id="wait-references-001",
                auth_mode="FULL_ACCESS",
            )
        ).json()["id"]
        await wait_status(client, turn_id, "WAITING_JOB")
        before = [
            json.loads(str(message.content))
            for message in captured[-1]
            if isinstance(message, ToolMessage)
        ]
        execution_id = before[0]["executed"]["operation_id"]
        memory_id = before[1]["proposal_id"]
        research_id = before[2]["proposals"][0]["proposal_id"]
        if restart:
            await stack.aclose()
            app, client, captured = await stack.enter_async_context(
                turns_app(tmp_path, monkeypatch, replies=continuation)
            )
        release.set()
        assert (await wait_terminal(client, turn_id))["status"] == "COMPLETED"
        done = (await drain_events(client, turn_id))[-1][1]
        assert [entry["proposal_id"] for entry in done["memory_proposals"]][0] == memory_id
        assert len(done["memory_proposals"]) == 2
        assert done["research_proposals"] == [
            {"proposal_id": research_id, "url": "https://example.com/proposal", "title": "候选资料"}
        ]
        execution_ids = [entry["operation_id"] for entry in done["executed_operations"]]
        assert execution_ids[0] == execution_id
        assert len(execution_ids) == 1
        # 请求档未设置会话覆盖，接续按当前全局档收紧，新操作仍走确认卡。
        assert len(done["operation_proposals"]) == 1
        messages = (await client.get(f"/api/chat-sessions/{session_id}/messages")).json()
        assistant = next(message for message in messages if message["role"] == "ASSISTANT")
        user = next(message for message in messages if message["role"] == "USER")
        assert assistant["executed_operation_ids"] == execution_ids
        assert user["turn"]["result"]["memory_proposals"] == done["memory_proposals"]
        assert user["turn"]["result"]["research_proposals"] == done["research_proposals"]
        async with app.state.session_factory() as session:
            assert await session.scalar(text("SELECT COUNT(*) FROM chat_turn_waits")) == 1
            assert await session.scalar(text("SELECT COUNT(*) FROM library_items")) == 1
            assert await session.scalar(text("SELECT COUNT(*) FROM courses")) == 1
            assert await session.scalar(text("SELECT COUNT(*) FROM agent_proposals")) == 4


@pytest.mark.anyio
@pytest.mark.parametrize("source_failed", [False, True])
async def test_t16_wait_releases_slot_and_resumes_original_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source_failed: bool
) -> None:
    from app.modules.llm import service as llm_service

    release = asyncio.Event()
    fetched = asyncio.Event()

    async def fetch(_self: object, url: str) -> ClipContent:
        fetched.set()
        await release.wait()
        if source_failed:
            raise WebClipError("WEB_FETCH_UNREACHABLE", "来源访问失败")
        return ClipContent(text="后台真实写回正文。" * 20, title="后台资料", metadata={"url": url})

    monkeypatch.setattr("app.modules.capture.web_clip.WebClipAdapter.fetch_and_extract", fetch)
    async with turns_app(
        tmp_path,
        monkeypatch,
        replies=[
            ToolCallReply("plan_batch_operations", {"items": PLAN}),
            ToolCallReply("wait_for_task", {}),
            ["会话 B 完成"],
            ["来源失败" if source_failed else "后台结果已完成"],
        ],
    ) as (app, client, captured):
        install_wait_model(monkeypatch, cast(type[StubChatModel], llm_service.ChatOpenAI))
        session_id = await create_session(client)
        turn_id = (
            await submit(
                client,
                session_id,
                "导入并等待结果",
                request_id="wait-result-001",
                auth_mode="FULL_ACCESS",
            )
        ).json()["id"]
        waiting = await wait_status(client, turn_id, "WAITING_JOB")
        await asyncio.wait_for(fetched.wait(), 5)
        assert waiting["background_tasks"][0]["control_scope"] == "EXCLUSIVE"
        # T21：真实迁移库执行 CHECK 和稳定逻辑调用唯一约束。
        with sqlite3.connect(tmp_path / "knowrealm.db") as connection:
            for sql in (
                "UPDATE chat_turn_runs SET control_scope='INVALID'",
                "UPDATE chat_turn_runs SET cancel_requested=2",
                "INSERT INTO chat_turn_runs SELECT * FROM chat_turn_runs",
                "UPDATE chat_turn_waits SET target_type='INVALID'",
                "INSERT INTO chat_turn_waits SELECT 'duplicate', turn_id, namespace,"
                " logical_call_id, target_type, target_id, source_operation_id,"
                " interrupt_id, result_json, created_at FROM chat_turn_waits",
                "UPDATE chat_turns SET compacted_seq=-1",
            ):
                with pytest.raises(sqlite3.IntegrityError):
                    connection.execute(sql)
            connection.rollback()
        assert (
            await submit(client, session_id, "另一问", request_id="wait-result-002")
        ).status_code == 409
        assert (await client.post(f"/api/chat-turns/{turn_id}/compact")).status_code == 409
        # 等待不占两个执行槽，另一会话公开受理与生成可推进。
        other = await create_session(client)
        other_turn = (await submit(client, other, "你好", request_id="wait-result-003")).json()[
            "id"
        ]
        assert (await wait_terminal(client, other_turn))["status"] == "COMPLETED"
        release.set()
        completed = await wait_terminal(client, turn_id)
        assert completed["status"] == "COMPLETED"
        assert completed["output_text"] == ("来源失败" if source_failed else "后台结果已完成")
        assert completed["attempt"] == 2
        messages = captured[-1]
        result = next(m for m in reversed(messages) if isinstance(m, ToolMessage))
        payload = json.loads(str(result.content))
        assert payload["ok"] is (not source_failed)
        assert payload["operations"][0]["result"]["awaited_job_id"]
        if source_failed:
            assert payload["operations"][0]["error_code"] == "AGENT_RUN_WAITING_JOB_FAILED"
            assert payload["operations"][0]["background_error_code"] == "WEB_FETCH_UNREACHABLE"
        else:
            assert payload["operations"][0]["background_result"]["title"] == "后台资料"
        async with app.state.session_factory() as session:
            counts = (
                await session.execute(
                    text(
                        "SELECT (SELECT COUNT(*) FROM library_items),"
                        " (SELECT COUNT(*) FROM transcripts),"
                        " (SELECT COUNT(*) FROM chat_turn_waits),"
                        " (SELECT COUNT(*) FROM agent_operations)"
                    )
                )
            ).one()
        assert tuple(counts) == ((1, 0, 1, 1) if source_failed else (1, 1, 1, 1))


@pytest.mark.anyio
async def test_t19_history_preserves_active_dependencies_then_releases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.llm import service as llm_service

    release = asyncio.Event()

    async def fetch(_self: object, url: str) -> ClipContent:
        await release.wait()
        return ClipContent(text="受保护成果。" * 40, title="保护", metadata={"url": url})

    monkeypatch.setattr("app.modules.capture.web_clip.WebClipAdapter.fetch_and_extract", fetch)
    async with turns_app(
        tmp_path,
        monkeypatch,
        replies=[
            ToolCallReply(
                "create_course",
                {"name": "保护课", "learning_context": "INTEREST", "depth": "BEGINNER"},
                "course-call",
            ),
            ToolCallReply("plan_batch_operations", {"items": PLAN}, "plan-call"),
            ToolCallReply("wait_for_task", {}),
        ],
    ) as (app, client, _):
        install_wait_model(monkeypatch, cast(type[StubChatModel], llm_service.ChatOpenAI))
        session_id = await create_session(client)
        turn_id = (
            await submit(
                client,
                session_id,
                "创建并等待",
                request_id="history-wait-001",
                auth_mode="FULL_ACCESS",
            )
        ).json()["id"]
        waiting = await wait_status(client, turn_id, "WAITING_JOB")
        run_id = waiting["background_tasks"][0]["target_id"]
        save_llm_provider(
            tmp_path,
            base_url="https://stub.example.com/v1",
            api_key="sk-test",
            model="changed-model",
            clear_api_key=False,
        )
        release.set()
        await wait_status(client, turn_id, "WAITING_USER")
        assert (await client.get(f"/api/agent/runs/{run_id}")).json()["status"] == "COMPLETED"
        assert (await client.delete(f"/api/agent/runs/{run_id}")).status_code == 409
        assert (await client.post("/api/agent/runs/purge-finished")).json() == {
            "runs_deleted": 0,
            "operations_deleted": 0,
        }
        async with app.state.session_factory() as session:
            assert await session.scalar(text("SELECT COUNT(*) FROM agent_operations")) == 2
            assert await session.scalar(text("SELECT COUNT(*) FROM chat_turn_waits")) == 1
        assert (await client.post(f"/api/chat-turns/{turn_id}/cancel")).status_code == 200
        purges = await asyncio.gather(
            client.post("/api/agent/runs/purge-finished"),
            client.post("/api/agent/runs/purge-finished"),
        )
        assert sorted(
            (p.json()["runs_deleted"], p.json()["operations_deleted"]) for p in purges
        ) == [(0, 0), (1, 2)]
        async with app.state.session_factory() as session:
            assert await session.scalar(text("SELECT COUNT(*) FROM courses")) == 1
            assert await session.scalar(text("SELECT COUNT(*) FROM library_items")) == 1


@pytest.mark.anyio
async def test_t18_cancel_exclusive_run_keeps_committed_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.llm import service as llm_service

    release = asyncio.Event()
    fetched = asyncio.Event()

    async def fetch(_self: object, url: str) -> ClipContent:
        fetched.set()
        await release.wait()
        return ClipContent(text="已提交成果保留。" * 20, title="保留", metadata={"url": url})

    monkeypatch.setattr("app.modules.capture.web_clip.WebClipAdapter.fetch_and_extract", fetch)
    async with turns_app(
        tmp_path,
        monkeypatch,
        replies=[
            ToolCallReply("plan_batch_operations", {"items": PLAN}),
            ToolCallReply("wait_for_task", {}),
        ],
    ) as (app, client, captured):
        install_wait_model(monkeypatch, cast(type[StubChatModel], llm_service.ChatOpenAI))
        session_id = await create_session(client)
        turn_id = (
            await submit(
                client,
                session_id,
                "导入并等待",
                request_id="wait-cancel-001",
                auth_mode="FULL_ACCESS",
            )
        ).json()["id"]
        waiting = await wait_status(client, turn_id, "WAITING_JOB")
        await asyncio.wait_for(fetched.wait(), 5)
        run_id = waiting["background_tasks"][0]["target_id"]
        stopped = await client.post(f"/api/chat-turns/{turn_id}/cancel")
        assert stopped.json()["turn"]["status"] == "CANCELLED"
        run: dict[str, Any] = {}
        for _ in range(100):
            run = (await client.get(f"/api/agent/runs/{run_id}")).json()
            if run["status"] == "CANCELLED":
                break
            await asyncio.sleep(0.1)
        assert run["status"] == "CANCELLED" and run["cancel_requested"]
        release.set()
        status = None
        for _ in range(100):
            async with app.state.session_factory() as session:
                status = await session.scalar(
                    text("SELECT status FROM processing_jobs WHERE job_type='WEB_FETCH'")
                )
            if status == "SUCCEEDED":
                break
            await asyncio.sleep(0.1)
        assert status == "SUCCEEDED"
        assert (await snapshot(client, turn_id))["status"] == "CANCELLED"
        assert len(captured) == 2  # 取消轮次不消费成功结果、不调用后续模型。


@pytest.mark.anyio
async def test_t20_compaction_old_cursor_resets_authoritative_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with turns_app(tmp_path, monkeypatch) as (app, client, _):
        session_id = await create_session(client)
        turn_id = (await submit(client, session_id, "你好", request_id="compact-turn-001")).json()[
            "id"
        ]
        before = await wait_terminal(client, turn_id)
        compact = await client.post(f"/api/chat-turns/{turn_id}/compact")
        assert compact.status_code == 200
        saved = compact.json()
        assert saved["compacted_seq"] == before["last_seq"]
        assert saved["output_text"] == before["output_text"]
        assert saved["process"] == before["process"]
        events = await drain_events(client, turn_id)
        reset = next(body for kind, body in events if kind == "status" and body["phase"] == "reset")
        assert reset["snapshot"] == saved
        history = (await client.get(f"/api/chat-sessions/{session_id}/messages")).json()
        assert len([item for item in history if item["role"] in ("USER", "ASSISTANT")]) == 2
        async with app.state.session_factory() as session:
            assert await session.scalar(text("SELECT COUNT(*) FROM chat_turn_events")) == 0
        assert (await client.post(f"/api/chat-turns/{turn_id}/compact")).json() == saved


@pytest.mark.anyio
@pytest.mark.parametrize("target_type", ["RUN", "JOB"])
async def test_t18_shared_wait_cancel_leaves_original_task_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target_type: str
) -> None:
    from app.modules.agent.runs.schemas import AuthMode

    release = asyncio.Event()
    fetched = asyncio.Event()

    async def fetch(_self: object, url: str) -> ClipContent:
        fetched.set()
        await release.wait()
        return ClipContent(text="共享成果。" * 30, title="共享", metadata={"url": url})

    monkeypatch.setattr("app.modules.capture.web_clip.WebClipAdapter.fetch_and_extract", fetch)
    async with turns_app(tmp_path, monkeypatch, replies=[]) as (app, client, captured):
        from app.modules.llm import service as llm_service

        session_id = await create_session(client)
        source = await invoke_plan(
            app.state.session_factory, PLAN, auth_mode=AuthMode.FULL_ACCESS, session_id=session_id
        )
        run_id = source["run"]["run_id"]
        await asyncio.wait_for(fetched.wait(), 5)
        async with app.state.session_factory() as session:
            job_id = await session.scalar(
                text("SELECT id FROM processing_jobs WHERE job_type='WEB_FETCH'")
            )
        model = cast(type[StubChatModel], llm_service.ChatOpenAI)
        model.replies.append(
            ToolCallReply(
                "wait_for_task",
                {
                    "target_type": target_type,
                    "target_id": run_id if target_type == "RUN" else job_id,
                },
            )
        )
        turn_id = (await submit(client, session_id, "等结果", request_id="shared-wait-001")).json()[
            "id"
        ]
        waiting = await wait_status(client, turn_id, "WAITING_JOB")
        assert all(task["control_scope"] == "SHARED" for task in waiting["background_tasks"])
        assert (await client.post(f"/api/chat-turns/{turn_id}/cancel")).status_code == 200
        run = (await client.get(f"/api/agent/runs/{run_id}")).json()
        assert not run["cancel_requested"] and run["status"] == "WAITING_JOB"
        release.set()
        for _ in range(100):
            run = (await client.get(f"/api/agent/runs/{run_id}")).json()
            if run["status"] == "COMPLETED":
                break
            await asyncio.sleep(0.1)
        assert run["status"] == "COMPLETED"
        assert (await snapshot(client, turn_id))["status"] == "CANCELLED"
        assert len(captured) == 1


def test_t17_killed_source_worker_recovers_original_job_and_turn(tmp_path: Path) -> None:
    ffmpeg = (
        Path(__file__).resolve().parents[2]
        / "apps/desktop/src-tauri/binaries/ffmpeg-x86_64-pc-windows-msvc.exe"
    )
    if not ffmpeg.is_file():
        pytest.skip("随包 ffmpeg 未准备（进程启动参数要求）")
    save_llm_provider(
        tmp_path,
        base_url="https://stub.example.com/v1",
        api_key="sk-test",
        model="stub-chat-model",
        clear_api_key=False,
    )
    grant_llm_consent(tmp_path)

    def start() -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).with_name("sidecar_chat_wait_fixture.py")),
                "--port",
                "0",
                "--token=test-launch-token",
                "--data-dir",
                str(tmp_path),
                "--ffmpeg",
                str(ffmpeg),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def row(sql: str) -> tuple[Any, ...]:
        with sqlite3.connect(tmp_path / "knowrealm.db") as connection:
            result = connection.execute(sql).fetchone()
            assert result is not None
            return tuple(result)

    process = start()
    try:
        base_url, _ = wait_for_sidecar(process, "test-launch-token")
        with httpx.Client(
            base_url=base_url, trust_env=False, headers={"X-KnowRealm-Token": "test-launch-token"}
        ) as client:
            waiting: dict[str, Any] = {}
            session_id = client.post("/api/chat-sessions", json={}).json()["id"]
            turn_id = client.post(
                f"/api/chat-sessions/{session_id}/turns",
                json={
                    "content": "导入并等待",
                    "auth_mode": "FULL_ACCESS",
                    "request_id": "process-wait-001",
                },
            ).json()["id"]
            for _ in range(150):
                waiting = client.get(f"/api/chat-turns/{turn_id}").json()
                if (
                    waiting["status"] == "WAITING_JOB"
                    and row(
                        "SELECT (SELECT status FROM processing_jobs WHERE job_type='WEB_FETCH')"
                    )[0]
                    == "RUNNING"
                ):
                    break
                time.sleep(0.1)
            assert waiting["status"] == "WAITING_JOB"
            original = row(
                "SELECT id, record_id, attempts FROM processing_jobs WHERE job_type='WEB_FETCH'"
            )
            assert original[2] == 1
        process.kill()
        process.communicate(timeout=10)
        assert row("SELECT status FROM processing_jobs WHERE job_type='WEB_FETCH'") == ("RUNNING",)
        (tmp_path / "release-fetch").touch()
        process = start()
        base_url, _ = wait_for_sidecar(process, "test-launch-token")
        with httpx.Client(
            base_url=base_url, trust_env=False, headers={"X-KnowRealm-Token": "test-launch-token"}
        ) as client:
            completed: dict[str, Any] = {}
            for _ in range(300):
                completed = client.get(f"/api/chat-turns/{turn_id}").json()
                if completed["status"] in ("COMPLETED", "FAILED"):
                    break
                time.sleep(0.1)
            assert completed["status"] == "COMPLETED", completed
            assert completed["output_text"] == "原任务恢复完成"
            assert completed["attempt"] == 2
        restored = row(
            "SELECT id, record_id, attempts, status FROM processing_jobs WHERE job_type='WEB_FETCH'"
        )
        assert restored == (*original[:2], 2, "SUCCEEDED")
        assert row("SELECT COUNT(*) FROM transcripts") == (1,)
        assert row("SELECT COUNT(*) FROM library_items") == (1,)
        assert row("SELECT COUNT(*) FROM chat_turn_waits") == (1,)
        assert row("SELECT COUNT(*) FROM agent_operations") == (1,)
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)
