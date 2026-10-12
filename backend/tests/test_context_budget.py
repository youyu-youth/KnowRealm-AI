"""公开提交/查看 + 真实迁移 SQLite/Worker；模型替身验证最终输入闸门。"""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from sqlalchemy import text

from app.modules.agent.context_budget.policy import estimate_input, policy_for
from app.modules.settings.config import LlmProviderConfig
from app.modules.settings.model_budget import ModelBudgetConfig, resolve_capability
from app.shared.errors import CodedHTTPException
from tests.test_chat_turns import (
    GatedReply,
    ToolCallReply,
    create_session,
    submit,
    turns_app,
    wait_running_progress,
    wait_terminal,
)
from tests.test_chat_turns_recovery import recovery_app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_capabilities_are_endpoint_bound_and_overrides_win() -> None:
    official = resolve_capability("https://api.openai.com/v1", "gpt-4.1", None)
    assert official.context_window == 1047576
    assert official.sources["context_window"].startswith("https://")
    custom = resolve_capability("https://private.example/v1", "gpt-4.1", None)
    assert custom.context_window is None
    with pytest.raises(CodedHTTPException, match="配置"):
        policy_for(LlmProviderConfig("https://private.example/v1", "key", "gpt-4.1"))
    override = resolve_capability(
        "https://api.openai.com/v1", "gpt-4.1", ModelBudgetConfig(context_window=20000)
    )
    assert override.context_window == 20000
    assert override.sources["context_window"] == "USER"


def test_complete_input_counts_tools_pairs_unicode_and_output_constraints() -> None:
    policy = policy_for(
        LlmProviderConfig(
            "https://private.example/v1",
            "key",
            "model",
            ModelBudgetConfig(input_limit=2000, context_window=3000, max_output=100),
        )
    )
    messages = [
        SystemMessage("规则"),
        HumanMessage("提问🙂"),
        AIMessage(
            content="", tool_calls=[{"name": "action", "args": {"target": "必须保留"}, "id": "c1"}]
        ),
        ToolMessage(content=json.dumps({"receipt": "原始回执"}), tool_call_id="c1"),
    ]
    result = estimate_input(
        policy,
        messages,
        [{"type": "function", "function": {"name": "action", "parameters": {"type": "object"}}}],
    )
    assert result.output_reserve == 100
    assert result.input_capacity == 2000
    assert result.safety_margin == 400 and result.usable_budget == 1600
    assert result.components["tools"] > 0 and result.components["protocol"] > 0
    assert result.input_tokens > estimate_input(policy, messages[:2], []).input_tokens
    assert messages[-1].content == json.dumps({"receipt": "原始回执"})


@pytest.mark.anyio
async def test_public_request_snapshot_and_next_estimate_are_distinct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with turns_app(tmp_path, monkeypatch) as (app, client, captured):
        session_id = await create_session(client)
        accepted = await submit(client, session_id, "问题", request_id="context-snapshot")
        assert accepted.status_code == 202
        completed = await wait_terminal(client, accepted.json()["id"])
        assert completed["status"] == "COMPLETED", completed
        view = (await client.get(f"/api/chat-sessions/{session_id}/context")).json()
        assert len(view["actual"]) == 1
        actual = view["actual"][0]
        assert actual["status"] == "COMPLETED" and actual["usage"] is None
        assert actual["estimate"]["tool_count"] > 0
        assert actual["estimate"]["message_count"] == len(captured[0])
        assert actual["estimate"]["components"]["system"] > 0
        estimate = await client.post(
            f"/api/chat-sessions/{session_id}/context/estimates", json={"content": "下一轮草稿"}
        )
        assert estimate.status_code == 200
        assert estimate.json()["actual"] == view["actual"]
        assert (
            estimate.json()["next_estimate"]["input_fingerprint"]
            != actual["estimate"]["input_fingerprint"]
        )
        other = await create_session(client)
        assert (await client.get(f"/api/chat-sessions/{other}/context")).json()["actual"] == []
        async with app.state.session_factory() as db:
            saved = (
                await db.execute(
                    text("SELECT messages_json FROM chat_context_inputs WHERE turn_id=:id"),
                    {"id": accepted.json()["id"]},
                )
            ).scalar_one()
            assert "问题" in saved and "api_key" not in saved


@pytest.mark.anyio
async def test_blocked_input_never_calls_model_and_keeps_user_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with turns_app(tmp_path, monkeypatch) as (_app, client, captured):
        session_id = await create_session(client)
        configured = await client.put(
            "/api/settings/providers/llm",
            json={
                "base_url": "https://stub.example.com/v1",
                "model": "stub-chat-model",
                "model_budget": {"context_window": 1000},
            },
        )
        assert configured.status_code == 200
        response = await submit(client, session_id, "不能丢失的提问", request_id="context-blocked")
        result = await wait_terminal(client, response.json()["id"])
        assert result["status"] == "FAILED"
        assert result["error_code"] == "MODEL_INPUT_BUDGET_EXCEEDED"
        assert captured == []
        view = (await client.get(f"/api/chat-sessions/{session_id}/context")).json()
        assert view["actual"][0]["status"] == "BLOCKED"
        history = (await client.get(f"/api/chat-sessions/{session_id}/messages")).json()
        assert any(message["content"] == "不能丢失的提问" for message in history)


@pytest.mark.anyio
async def test_every_model_call_accounts_for_same_turn_tool_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replies: list[Any] = [ToolCallReply("get_current_time", {}), ["完成"]]
    async with turns_app(tmp_path, monkeypatch, replies=replies) as (_app, client, captured):
        session_id = await create_session(client)
        response = await submit(client, session_id, "查看当前时间", request_id="context-tool-loop")
        result = await wait_terminal(client, response.json()["id"])
        assert result["status"] == "COMPLETED", result
        view = (await client.get(f"/api/chat-sessions/{session_id}/context")).json()
        assert len(view["actual"]) == len(captured) == 2
        first, second = [row["estimate"] for row in view["actual"]]
        assert second["input_tokens"] > first["input_tokens"]
        assert any(isinstance(message, ToolMessage) for message in captured[1])


@pytest.mark.anyio
async def test_restart_preserves_original_policy_and_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with recovery_app(
        tmp_path, monkeypatch, replies=[GatedReply(prefix=("部分回答",), release=asyncio.Event())]
    ) as (_app, client, _captured):
        sid = await create_session(client)
        turn_id = (await submit(client, sid, "原提问", request_id="context-restart")).json()["id"]
        await wait_running_progress(client, turn_id, 1)
        original = (await client.get(f"/api/chat-sessions/{sid}/context")).json()["actual"][0]
    async with recovery_app(tmp_path, monkeypatch, replies=[["恢复完成"]]) as (
        _app,
        client,
        captured,
    ):
        assert (await wait_terminal(client, turn_id))["status"] == "COMPLETED"
        result = (await client.get(f"/api/chat-sessions/{sid}/context")).json()
        assert result["actual"][0] == original
        assert len(result["actual"]) == 2 and len(captured) == 1
        replay = result["actual"][1]["estimate"]
        assert replay["policy"] == original["estimate"]["policy"]
        assert replay["input_fingerprint"] == original["estimate"]["input_fingerprint"]


@pytest.mark.anyio
async def test_provider_capability_updates_keep_bound_turn_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = asyncio.Event()
    async with turns_app(
        tmp_path, monkeypatch, replies=[GatedReply(prefix=("处理中",), release=release)]
    ) as (_app, client, captured):
        sid = await create_session(client)
        turn_id = (
            await submit(client, sid, "原提问", request_id="context-capability-change")
        ).json()["id"]
        await wait_running_progress(client, turn_id, 1)
        response = await client.put(
            "/api/settings/providers/llm",
            json={
                "base_url": "https://stub.example.com/v1",
                "model": "stub-chat-model",
                "model_budget": {"context_window": 1000, "answer_output": 200},
            },
        )
        assert response.status_code == 200
        release.set()
        assert (await wait_terminal(client, turn_id))["status"] == "COMPLETED"
        view = (await client.get(f"/api/chat-sessions/{sid}/context")).json()
        assert view["actual"][0]["estimate"]["policy"]["capability"]["context_window"] == 128000
        assert view["next_estimate"]["policy"]["capability"]["context_window"] == 1000
        assert len(captured) == 1
