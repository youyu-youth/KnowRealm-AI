"""05：公开操作、迁移 SQLite、Worker 与模型替身的会话过滤闭环。"""

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import ToolMessage, messages_to_dict
from sqlalchemy import text

from tests.test_chat_turns import ToolCallReply, create_session, submit, turns_app, wait_terminal
from tests.test_conversation_compaction import (
    configure,
    seed_history,
    summary_model,
    wait_summary_calls,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_exclusion_reset_and_explicit_history_keep_data_and_pins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with turns_app(tmp_path, monkeypatch, replies=[["完成"] for _ in range(6)]) as (
        _app,
        client,
        inputs,
    ):
        sid = await create_session(client)
        url = f"/api/chat-sessions/{sid}/context"
        first = (await submit(client, sid, "原轮独有秘密", request_id=str(uuid4()))).json()
        assert (await wait_terminal(client, first["id"]))["status"] == "COMPLETED"
        messages = (await client.get(f"/api/chat-sessions/{sid}/messages")).json()
        original = next(row for row in messages if row["content"] == "原轮独有秘密")
        source = (
            await client.post(
                f"{url}/sources/read", json={"source_id": f"message:{original['id']}"}
            )
        ).json()
        pinned = await client.post(
            f"{url}/pins",
            json={
                "expected_version": 1,
                "mode": "SNIPPET",
                "content": source["content"],
                "source_id": source["source"]["source_id"],
                "source_version": source["source"]["version"],
            },
        )
        assert pinned.status_code == 200, pinned.text
        excluded = await client.post(
            f"{url}/rules",
            json={"expected_version": 2, "action": "EXCLUDE_TURN", "turn_ids": [first["id"]]},
        )
        assert excluded.status_code == 200, excluded.text
        view = (await client.get(url)).json()
        assert view["pins"][0]["status"] == "EXCLUDED"
        read = await client.post(
            f"{url}/sources/read", json={"source_id": source["source"]["source_id"]}
        )
        assert read.json()["code"] == "CONTEXT_SOURCE_EXCLUDED"
        second = (await submit(client, sid, "排除后继续", request_id=str(uuid4()))).json()
        assert (await wait_terminal(client, second["id"]))["status"] == "COMPLETED"
        assert "原轮独有秘密" not in str(inputs[-1])
        reset = await client.post(f"{url}/rules", json={"expected_version": 3, "action": "RESET"})
        assert reset.status_code == 200 and reset.json()["segment"] == 2
        included = await client.post(
            f"{url}/rules",
            json={"expected_version": 4, "action": "INCLUDE_HISTORY", "turn_ids": [first["id"]]},
        )
        assert included.status_code == 200, included.text
        assert (
            await client.post(
                f"{url}/sources/read", json={"source_id": source["source"]["source_id"]}
            )
        ).status_code == 409
        restored = await client.post(
            f"{url}/rules",
            json={"expected_version": 5, "action": "RESTORE_TURN", "turn_ids": [first["id"]]},
        )
        assert restored.status_code == 200
        third = (await submit(client, sid, "明确纳入后继续", request_id=str(uuid4()))).json()
        assert (await wait_terminal(client, third["id"]))["status"] == "COMPLETED"
        assert "原轮独有秘密" in str(inputs[-1]) and "排除后继续" not in str(inputs[-1])
        assert (
            await client.post(
                f"{url}/sources/read", json={"source_id": source["source"]["source_id"]}
            )
        ).status_code == 200
        history = (await client.get(f"{url}/history")).json()
        assert {row["turn_id"] for row in history["turns"]} == {
            first["id"],
            second["id"],
            third["id"],
        }
        messages = (await client.get(f"/api/chat-sessions/{sid}/messages")).json()
        assert len(messages) == 7, "系统消息与三个完整往返仍保留"


@pytest.mark.anyio
async def test_reset_rejects_old_reads_and_illegal_or_missing_inclusion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with turns_app(tmp_path, monkeypatch, replies=[["首轮回答"], ["新段回答"]]) as (
        _app,
        client,
        inputs,
    ):
        sid = await create_session(client)
        other = await create_session(client)
        url = f"/api/chat-sessions/{sid}/context"
        first = (await submit(client, sid, "旧段唯一问题", request_id=str(uuid4()))).json()
        await wait_terminal(client, first["id"])
        source = (await client.post(f"{url}/sources/search", json={"query": "旧段唯一"})).json()[
            "sources"
        ][0]
        assert (
            await client.post(f"{url}/rules", json={"expected_version": 1, "action": "RESET"})
        ).status_code == 200
        assert (
            await client.post(f"{url}/sources/read", json={"source_id": source["source_id"]})
        ).status_code == 404
        assert (await client.post(f"{url}/sources/search", json={"query": "旧段唯一"})).json()[
            "sources"
        ] == []
        missing = await client.post(
            f"{url}/rules", json={"expected_version": 2, "action": "INCLUDE_HISTORY"}
        )
        assert missing.status_code == 422
        foreign = await client.post(
            f"/api/chat-sessions/{other}/context/rules",
            json={"expected_version": 1, "action": "INCLUDE_HISTORY", "turn_ids": [first["id"]]},
        )
        assert foreign.json()["code"] == "CONTEXT_HISTORY_RANGE_INVALID"
        second = (await submit(client, sid, "新段问题", request_id=str(uuid4()))).json()
        assert (await wait_terminal(client, second["id"]))["status"] == "COMPLETED"
        assert "旧段唯一问题" not in str(inputs[-1]) and "首轮回答" not in str(inputs[-1])
        invalid = await client.post(
            f"{url}/rules",
            json={"expected_version": 2, "action": "INCLUDE_HISTORY", "turn_ids": [second["id"]]},
        )
        assert invalid.status_code == 409


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["REQUEST_APPROVAL", "AUTO_APPROVE", "FULL_ACCESS"])
async def test_rule_operation_three_modes_and_stale_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    async with turns_app(
        tmp_path,
        monkeypatch,
        replies=[
            ToolCallReply("change_context_rules", {"action": "RESET", "expected_version": 1}),
            ["已处理"],
        ],
    ) as (_app, client, _inputs):
        sid = await create_session(client)
        await client.put("/api/agent/auth-mode", json={"to_mode": mode})
        turn = (
            await submit(client, sid, "重置上下文", request_id=str(uuid4()), auth_mode=mode)
        ).json()
        assert (await wait_terminal(client, turn["id"]))["status"] == "COMPLETED"
        view = (await client.get(f"/api/chat-sessions/{sid}/context")).json()
        proposals = (await client.get(f"/api/proposals?session_id={sid}")).json()
        if mode == "REQUEST_APPROVAL":
            assert view["segment"] == 1 and len(proposals) == 1
            assert proposals[0]["proposal_type"] == "OP_CONTEXT_RULES"
            changed = await client.post(
                f"/api/chat-sessions/{sid}/context/rules",
                json={"action": "RESET", "expected_version": 1},
            )
            assert changed.status_code == 200
            stale = await client.post(f"/api/proposals/{proposals[0]['id']}/confirm")
            assert (
                stale.status_code == 422
                and stale.json()["params"]["errorCode"] == "CONTEXT_VERSION_CONFLICT"
            ), stale.text
        else:
            assert view["segment"] == 2 and proposals == []
        assert view["actual_segment"] == 1 and view["actual_rules"] == {
            "excluded_turn_ids": [],
            "excluded_source_ids": [],
            "included_turn_ids": [],
        }


@pytest.mark.anyio
@pytest.mark.parametrize("action", ["RESET", "EXCLUDE_TURN"])
@pytest.mark.parametrize("cancel", [False, True])
async def test_late_summary_uses_original_snapshot_without_activating_new_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str, cancel: bool
) -> None:
    calls: list[Any] = []
    gate = asyncio.Event()
    summary_model(monkeypatch, calls, gate)
    async with turns_app(tmp_path, monkeypatch) as (app, client, inputs):
        sid = await create_session(client)
        await seed_history(app, sid, 16, 1000)
        await configure(client)
        turn = (await submit(client, sid, "继续", request_id=str(uuid4()))).json()["id"]
        await wait_summary_calls(calls, 1)
        history = (await client.get(f"/api/chat-sessions/{sid}/context/history")).json()
        old = next(row["turn_id"] for row in history["turns"] if row["turn_id"] != turn)
        body: dict[str, Any] = {"expected_version": 1, "action": action}
        if action == "EXCLUDE_TURN":
            body["turn_ids"] = [old]
        try:
            changed = await client.post(f"/api/chat-sessions/{sid}/context/rules", json=body)
            assert changed.status_code == 200, changed.text
            if cancel:
                stopped = await client.post(f"/api/chat-turns/{turn}/cancel")
                assert stopped.status_code == 200, stopped.text
        finally:
            gate.set()
        done = await wait_terminal(client, turn)
        assert done["status"] == ("CANCELLED" if cancel else "COMPLETED"), done
        view = (await client.get(f"/api/chat-sessions/{sid}/context")).json()
        assert view["version"] == 2 and view["active_summary"] is None
        assert view["actual_segment"] == 1
        if cancel:
            assert inputs == [] and view["compactions"][0]["completed_chunks"] == 0
        else:
            assert inputs
        async with app.state.session_factory() as session:
            stored = (
                await session.execute(
                    text("SELECT rules_json, segment FROM chat_context_inputs WHERE turn_id=:id"),
                    {"id": turn},
                )
            ).one()
            assert json.loads(stored.rules_json) == {} and stored.segment == 1


@pytest.mark.anyio
@pytest.mark.parametrize("memory_enabled", [False, True])
async def test_material_exclusion_filters_prompt_search_read_and_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, memory_enabled: bool
) -> None:
    from tests.test_learner_memory import seed_mastery
    from tests.test_shared_refs import COURSE_ML, REC_ML_PAPER, seed_full_corpus

    async with turns_app(
        tmp_path,
        monkeypatch,
        replies=[
            ToolCallReply("search_library", {"query": "论文"}),
            ["无可用资料"],
            ["恢复资料"],
        ],
    ) as (app, client, inputs):
        await seed_full_corpus(app.state.session_factory)
        await seed_mastery(
            app.state.session_factory, COURSE_ML, str(uuid4()), "独立课程记忆", score=0.1
        )
        assert (
            await client.put("/api/learner/memory-outbound", json={"enabled": memory_enabled})
        ).status_code == 200
        sid = await create_session(client, scope="RECORD", record_id=REC_ML_PAPER)
        url = f"/api/chat-sessions/{sid}/context"
        source = (
            await client.post(f"{url}/sources/read", json={"source_id": f"record:{REC_ML_PAPER}"})
        ).json()
        change = {
            "action": "EXCLUDE_SOURCE",
            "expected_version": 1,
            "source_id": source["source"]["source_id"],
            "source_version": source["source"]["version"],
        }
        assert (await client.post(f"{url}/rules", json=change)).status_code == 200
        pinned = await client.post(
            f"{url}/pins",
            json={
                "expected_version": 2,
                "mode": "SNIPPET",
                "content": source["content"],
                "source_id": source["source"]["source_id"],
                "source_version": source["source"]["version"],
            },
        )
        assert pinned.status_code == 200 and pinned.json()["pins"][0]["status"] == "EXCLUDED"
        assert (
            await client.post(
                f"{url}/sources/read", json={"source_id": source["source"]["source_id"]}
            )
        ).json()["code"] == "CONTEXT_SOURCE_EXCLUDED"
        turn = (await submit(client, sid, "查找机器学习资料", request_id=str(uuid4()))).json()
        done = await wait_terminal(client, turn["id"])
        assert done["status"] == "COMPLETED", done
        assert source["content"] not in str(inputs[-1])
        assert "材料是待分析的数据" in inputs[-1][0].text
        assert ("独立课程记忆" in str(inputs[-1])) == memory_enabled
        assert (
            await client.post(f"{url}/rules", json={"expected_version": 3, "action": "RESET"})
        ).status_code == 200
        assert (
            await client.post(
                f"{url}/rules",
                json={
                    "expected_version": 4,
                    "action": "RESTORE_SOURCE",
                    "source_id": source["source"]["source_id"],
                },
            )
        ).status_code == 200
        view = (await client.get(url)).json()
        assert view["pins"][0]["status"] == "VALID"
        next_turn = (await submit(client, sid, "恢复后继续", request_id=str(uuid4()))).json()
        assert (await wait_terminal(client, next_turn["id"]))["status"] == "COMPLETED"
        assert source["content"] in str(inputs[-1])
        assert ("独立课程记忆" in str(inputs[-1])) == memory_enabled


@pytest.mark.anyio
async def test_agent_settings_pages_exclusions_with_shared_tool_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with turns_app(
        tmp_path,
        monkeypatch,
        replies=[
            ToolCallReply("get_context_settings", {}),
            ToolCallReply(
                "get_context_settings", {"offset": 4, "expected_version": 2}, "settings-page-2"
            ),
            ["设置已查看"],
        ],
    ) as (app, client, inputs):
        sid = await create_session(client)
        await seed_history(app, sid, 10, 30)
        url = f"/api/chat-sessions/{sid}/context"
        history = (await client.get(f"{url}/history")).json()
        identities = [row["turn_id"] for row in history["turns"]]
        changed = await client.post(
            f"{url}/rules",
            json={"expected_version": 1, "action": "EXCLUDE_TURN", "turn_ids": identities},
        )
        assert changed.status_code == 200, changed.text
        turn = (await submit(client, sid, "查看完整排除设置", request_id=str(uuid4()))).json()
        done = await wait_terminal(client, turn["id"])
        assert done["status"] == "COMPLETED", done
        pages = [
            json.loads(message.text)
            for message in inputs[-1]
            if isinstance(message, ToolMessage) and message.name == "get_context_settings"
        ]
        assert len(pages) == 2 and [page.get("next_offset") for page in pages] == [4, 8], pages
        assert all(page["rule_counts"]["excluded_turn_ids"] == 10 for page in pages)
        assert (
            len({identity for page in pages for identity in page["rules"]["excluded_turn_ids"]})
            == 8
        )


@pytest.mark.anyio
async def test_legacy_history_rules_survive_restart_without_cancelling_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.agent.runs.models import AgentRun
    from tests.test_chat_turns_recovery import recovery_app

    async with turns_app(tmp_path, monkeypatch) as (app, client, _inputs):
        sid = await create_session(client)
        await seed_history(app, sid, 2, 40)
        url = f"/api/chat-sessions/{sid}/context"
        history = (await client.get(f"{url}/history")).json()
        chosen = history["turns"][0]["turn_id"]
        async with app.state.session_factory() as session, session.begin():
            run = AgentRun(
                session_id=sid,
                auth_mode="REQUEST_APPROVAL",
                status="WAITING_USER",
                waiting_reason="待确认业务操作",
            )
            session.add(run)
            await session.flush()
            run_id = run.id
        assert (
            await client.post(
                f"{url}/rules",
                json={"expected_version": 1, "action": "EXCLUDE_TURN", "turn_ids": [chosen]},
            )
        ).status_code == 200
        assert (
            await client.post(f"{url}/rules", json={"expected_version": 2, "action": "RESET"})
        ).status_code == 200
        assert (
            await client.post(
                f"{url}/rules",
                json={"expected_version": 3, "action": "INCLUDE_HISTORY", "turn_ids": [chosen]},
            )
        ).status_code == 200
    async with recovery_app(tmp_path, monkeypatch) as (app, client, inputs):
        view = (await client.get(url)).json()
        assert view["segment"] == 2 and view["rules"]["excluded_turn_ids"] == [chosen]
        assert (
            await client.post(
                f"{url}/rules",
                json={"expected_version": 4, "action": "RESTORE_TURN", "turn_ids": [chosen]},
            )
        ).status_code == 200
        turn = (await submit(client, sid, "新段恢复后", request_id=str(uuid4()))).json()
        done = await wait_terminal(client, turn["id"])
        assert done["status"] == "COMPLETED", done
        assert "USER-1:" in str(inputs[-1]) and "USER-0:" not in str(inputs[-1])
        async with app.state.session_factory() as session:
            saved = await session.get(AgentRun, run_id)
            assert saved and saved.status == "WAITING_USER" and not saved.cancel_requested
        assert "待确认业务操作" in inputs[-1][0].text


@pytest.mark.anyio
async def test_cached_asset_results_and_cited_answers_cannot_bypass_exclusion_or_source_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.agent.context_budget.retrieval import digest
    from tests.test_shared_refs import (
        COURSE_AGENT,
        ITEM_ML_PAPER,
        REC_ML_PAPER,
        seed_full_corpus,
        seed_ref,
    )

    async with turns_app(
        tmp_path,
        monkeypatch,
        replies=[
            ToolCallReply("search_library", {"query": "论文"}),
            ["有源旧回答"],
            ["新回答"],
        ],
    ) as (app, client, inputs):
        await seed_full_corpus(app.state.session_factory)
        await seed_ref(app.state.session_factory, COURSE_AGENT, ITEM_ML_PAPER)
        sid = await create_session(client, scope="COURSE", course_id=COURSE_AGENT)
        url = f"/api/chat-sessions/{sid}/context"
        original = (
            await client.post(f"{url}/sources/read", json={"source_id": f"record:{REC_ML_PAPER}"})
        ).json()
        accepted = (await submit(client, sid, "查找机器学习", request_id=str(uuid4()))).json()
        done = await wait_terminal(client, accepted["id"])
        assert done["status"] == "COMPLETED", done
        result = next(
            message
            for message in inputs[-1]
            if isinstance(message, ToolMessage) and message.name == "search_library"
        )
        raw = json.loads(result.text)
        assert raw["asset_matches"], raw
        identity = result.id or digest(json.dumps(messages_to_dict([result]), ensure_ascii=False))
        assert (
            await client.post(
                f"{url}/rules",
                json={
                    "expected_version": 1,
                    "action": "EXCLUDE_SOURCE",
                    "source_id": f"record:{REC_ML_PAPER}",
                    "source_version": original["source"]["version"],
                },
            )
        ).status_code == 200
        denied = await client.post(f"{url}/sources/read", json={"source_id": f"message:{identity}"})
        assert denied.status_code == 409 and denied.json()["code"] == "CONTEXT_SOURCE_EXCLUDED", (
            denied.text
        )
        # 模拟已持久、可追溯引用；随后来源改变，原回答与工具历史仍完整保存在数据库。
        messages = (await client.get(f"/api/chat-sessions/{sid}/messages")).json()
        answer = next(row for row in messages if row["content"] == "有源旧回答")
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE chat_messages SET citations_json=:citations WHERE id=:id"),
                {
                    "id": answer["id"],
                    "citations": json.dumps(
                        [
                            {
                                "record_id": REC_ML_PAPER,
                                "quote": original["content"][:20],
                                "source_version": original["source"]["version"],
                            }
                        ]
                    ),
                },
            )
            await session.execute(
                text("UPDATE transcripts SET source_version=source_version+1 WHERE record_id=:id"),
                {"id": REC_ML_PAPER},
            )
        assert (
            await client.post(
                f"{url}/rules",
                json={
                    "expected_version": 2,
                    "action": "RESTORE_SOURCE",
                    "source_id": f"record:{REC_ML_PAPER}",
                },
            )
        ).status_code == 200
        next_turn = (await submit(client, sid, "不要复用失效来源", request_id=str(uuid4()))).json()
        assert (await wait_terminal(client, next_turn["id"]))["status"] == "COMPLETED"
        assert "有源旧回答" not in str(inputs[-1])
        stored = (await client.get(f"/api/chat-sessions/{sid}/messages")).json()
        assert any(row["content"] == "有源旧回答" for row in stored)
