"""固定设置的公开 API、真实 SQLite/Worker 与模型替身验收。"""

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import ToolMessage
from sqlalchemy import text

from tests.test_chat_turns import (
    GatedReply,
    StubReply,
    ToolCallReply,
    create_session,
    submit,
    turns_app,
    wait_running_progress,
    wait_terminal,
)
from tests.test_chat_turns_recovery import recovery_app
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
async def test_pin_survives_long_history_and_unpin_changes_next_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replies: list[StubReply] = [["完成"] for _ in range(13)]
    async with turns_app(tmp_path, monkeypatch, replies=replies) as (_app, client, inputs):
        sid = await create_session(client)
        url = f"/api/chat-sessions/{sid}/context/pins"
        pinned = await client.post(
            url, json={"expected_version": 1, "mode": "TEXT", "content": "所有例子使用 Python"}
        )
        assert pinned.status_code == 200, pinned.text
        assert pinned.json()["version"] == 2
        pin_id = pinned.json()["pins"][0]["id"]
        for index in range(12):
            accepted = await submit(client, sid, f"继续第 {index} 轮", request_id=str(uuid4()))
            assert accepted.status_code == 202, accepted.text
            done = await wait_terminal(client, accepted.json()["id"])
            assert done["status"] == "COMPLETED", done
        assert all("所有例子使用 Python" in messages[0].text for messages in inputs)
        removed = await client.post(
            url, json={"expected_version": 2, "action": "REMOVE", "pin_id": pin_id}
        )
        assert removed.status_code == 200, removed.text
        accepted = await submit(client, sid, "下一轮", request_id=str(uuid4()))
        assert (await wait_terminal(client, accepted.json()["id"]))["status"] == "COMPLETED"
        assert "所有例子使用 Python" not in inputs[-1][0].text


@pytest.mark.anyio
async def test_pins_survive_compaction_without_entering_summary_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Any] = []
    summary_model(monkeypatch, calls)
    async with turns_app(tmp_path, monkeypatch) as (app, client, inputs):
        sid = await create_session(client)
        response = await client.post(
            f"/api/chat-sessions/{sid}/context/pins",
            json={
                "expected_version": 1,
                "mode": "TEXT",
                "content": "固定独立原文：答案使用 Python",
            },
        )
        assert response.status_code == 200
        await seed_history(app, sid, 16, 1000)
        await configure(client)
        accepted = await submit(client, sid, "继续", request_id=str(uuid4()))
        done = await wait_terminal(client, accepted.json()["id"])
        assert done["status"] == "COMPLETED", done
        assert calls and "固定独立原文：答案使用 Python" in inputs[-1][0].text
        assert all("固定独立原文" not in str(call) for call in calls)
        view = (await client.get(f"/api/chat-sessions/{sid}/context")).json()
        assert view["active_summary"] and view["actual_pins"][0]["injected"]


@pytest.mark.anyio
async def test_pin_overflow_blocks_answer_and_summary_without_losing_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Any] = []
    summary_model(monkeypatch, calls)
    async with turns_app(tmp_path, monkeypatch) as (app, client, inputs):
        sid = await create_session(client)
        for version in range(1, 5):
            response = await client.post(
                f"/api/chat-sessions/{sid}/context/pins",
                json={"expected_version": version, "mode": "TEXT", "content": "不可裁切" * 1500},
            )
            assert response.status_code == 200, response.text
        await seed_history(app, sid, 12, 500)
        await configure(client, 40000)
        accepted = await submit(client, sid, "不要删除这个问题", request_id=str(uuid4()))
        done = await wait_terminal(client, accepted.json()["id"])
        assert done["status"] == "FAILED" and done["error_code"] == "CONTEXT_PINS_TOO_LARGE"
        assert inputs == [] and calls == []
        view = (await client.get(f"/api/chat-sessions/{sid}/context")).json()
        assert len(view["pins"]) == 4 and view["next_error_code"] == "CONTEXT_PINS_TOO_LARGE"
        messages = (await client.get(f"/api/chat-sessions/{sid}/messages")).json()
        assert any(row["content"] == "不要删除这个问题" for row in messages)


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["REQUEST_APPROVAL", "AUTO_APPROVE", "FULL_ACCESS"])
async def test_agent_pin_three_modes_and_version_bound_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    async with turns_app(
        tmp_path,
        monkeypatch,
        replies=[
            ToolCallReply(
                "change_context_pin",
                {"expected_version": 1, "mode": "TEXT", "content": "只使用 Python"},
            ),
            ["已处理固定要求"],
        ],
    ) as (_app, client, _inputs):
        sid = await create_session(client)
        switched = await client.put("/api/agent/auth-mode", json={"to_mode": mode})
        assert switched.status_code == 200
        accepted = await submit(
            client, sid, "固定约束：只使用 Python", request_id=str(uuid4()), auth_mode=mode
        )
        done = await wait_terminal(client, accepted.json()["id"])
        assert done["status"] == "COMPLETED", done
        url = f"/api/chat-sessions/{sid}/context"
        view = (await client.get(url)).json()
        proposals = (await client.get(f"/api/proposals?session_id={sid}")).json()
        if mode == "REQUEST_APPROVAL":
            assert view["pins"] == [] and len(proposals) == 1
            confirmed = await client.post(f"/api/proposals/{proposals[0]['id']}/confirm")
            assert confirmed.status_code == 200, confirmed.text
            assert confirmed.json()["result"]["version"] == 2
        else:
            assert view["version"] == 2 and len(view["pins"]) == 1 and proposals == []
        view = (await client.get(url)).json()
        assert view["pins"][0]["content"] == "只使用 Python"
        assert view["actual_pins"] == [], "本轮工具新增设置不能回写本轮快照"


@pytest.mark.anyio
async def test_stale_proposal_and_concurrent_page_changes_do_not_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with turns_app(
        tmp_path,
        monkeypatch,
        replies=[
            ToolCallReply(
                "change_context_pin", {"expected_version": 1, "mode": "TEXT", "content": "Python"}
            ),
            ["待确认"],
        ],
    ) as (_app, client, _inputs):
        sid = await create_session(client)
        accepted = await submit(client, sid, "固定 Python", request_id=str(uuid4()))
        assert (await wait_terminal(client, accepted.json()["id"]))["status"] == "COMPLETED"
        proposal = (await client.get(f"/api/proposals?session_id={sid}")).json()[0]
        url = f"/api/chat-sessions/{sid}/context/pins"
        results = await asyncio.gather(
            *[
                client.post(url, json={"expected_version": 1, "mode": "TEXT", "content": value})
                for value in ("先写入", "竞争写入")
            ]
        )
        assert sorted(response.status_code for response in results) == [200, 409]
        confirmed = await client.post(f"/api/proposals/{proposal['id']}/confirm")
        assert confirmed.status_code == 422, confirmed.text
        assert confirmed.json()["params"]["errorCode"] == "CONTEXT_VERSION_CONFLICT"
        view = (await client.get(f"/api/chat-sessions/{sid}/context")).json()
        assert view["version"] == 2 and len(view["pins"]) == 1
        assert view["pins"][0]["content"] != "Python"


@pytest.mark.anyio
async def test_change_during_running_turn_preserves_frozen_pins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = asyncio.Event()
    async with turns_app(
        tmp_path, monkeypatch, replies=[GatedReply(("执行中",), release), ["下一轮"]]
    ) as (_app, client, inputs):
        sid = await create_session(client)
        url = f"/api/chat-sessions/{sid}/context/pins"
        pinned = (
            await client.post(
                url, json={"expected_version": 1, "mode": "TEXT", "content": "旧固定原文"}
            )
        ).json()
        accepted = await submit(client, sid, "继续", request_id=str(uuid4()))
        turn = accepted.json()["id"]
        await wait_running_progress(client, turn, 1)
        try:
            removed = await client.post(
                url,
                json={"expected_version": 2, "action": "REMOVE", "pin_id": pinned["pins"][0]["id"]},
            )
            assert removed.status_code == 200
        finally:
            release.set()
        assert (await wait_terminal(client, turn))["status"] == "COMPLETED"
        view = (await client.get(f"/api/chat-sessions/{sid}/context")).json()
        assert view["pins"] == [] and view["actual_pins"][0]["injected"]
        assert view["actual"][0]["context_version"] == 2 and view["version"] == 3
        accepted = await submit(client, sid, "下一轮", request_id=str(uuid4()))
        assert (await wait_terminal(client, accepted.json()["id"]))["status"] == "COMPLETED"
        assert "旧固定原文" in inputs[0][0].text and "旧固定原文" not in inputs[1][0].text


@pytest.mark.anyio
@pytest.mark.parametrize("mutation", ["version", "archive", "delete", "scope"])
async def test_source_changes_pause_snippets_and_never_expand_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
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
            ToolCallReply("get_context_settings", {}),
            ["当前回答"],
        ],
    ) as (app, client, inputs):
        await seed_full_corpus(app.state.session_factory)
        await seed_ref(app.state.session_factory, COURSE_AGENT, ITEM_ML_PAPER)
        sid = await create_session(client, scope="COURSE", course_id=COURSE_AGENT)
        source = (
            await client.post(
                f"/api/chat-sessions/{sid}/context/sources/read",
                json={"source_id": f"record:{REC_ML_PAPER}"},
            )
        ).json()
        url = f"/api/chat-sessions/{sid}/context/pins"
        body = {
            "expected_version": 1,
            "mode": "SNIPPET",
            "content": source["content"],
            "source_id": source["source"]["source_id"],
            "source_version": source["source"]["version"],
            "offset": 0,
        }
        pinned = await client.post(url, json=body)
        assert pinned.status_code == 200, pinned.text
        async with app.state.session_factory() as db, db.begin():
            if mutation == "version":
                await db.execute(
                    text(
                        "UPDATE transcripts SET source_version=source_version+1 WHERE record_id=:id"
                    ),
                    {"id": REC_ML_PAPER},
                )
            elif mutation == "archive":
                await db.execute(
                    text("UPDATE library_items SET status='ARCHIVED' WHERE id=:id"),
                    {"id": ITEM_ML_PAPER},
                )
            elif mutation == "delete":
                await db.execute(
                    text("UPDATE records SET deleted_at='2026-10-13T00:00:00Z' WHERE id=:id"),
                    {"id": REC_ML_PAPER},
                )
            else:
                await db.execute(
                    text(
                        "DELETE FROM course_shared_refs "
                        "WHERE course_id=:cid AND library_item_id=:iid"
                    ),
                    {"cid": COURSE_AGENT, "iid": ITEM_ML_PAPER},
                )
        view = (await client.get(f"/api/chat-sessions/{sid}/context")).json()
        assert view["pins"][0]["status"] == ("STALE" if mutation == "version" else "UNAVAILABLE")
        assert not view["pins"][0]["injected"]
        accepted = await submit(client, sid, "继续", request_id=str(uuid4()))
        assert (await wait_terminal(client, accepted.json()["id"]))["status"] == "COMPLETED"
        assert "用户固定上下文" not in inputs[-1][0].text
        settings = json.loads(
            next(
                m.text
                for m in inputs[-1]
                if isinstance(m, ToolMessage) and m.name == "get_context_settings"
            )
        )
        assert settings["pins"][0]["content"] == ""
        if mutation == "version":
            current = (
                await client.post(
                    f"/api/chat-sessions/{sid}/context/sources/read",
                    json={"source_id": source["source"]["source_id"]},
                )
            ).json()
            updated = await client.post(
                url,
                json={
                    **body,
                    "expected_version": 2,
                    "action": "UPDATE",
                    "pin_id": pinned.json()["pins"][0]["id"],
                    "source_version": current["source"]["version"],
                },
            )
            assert updated.status_code == 200 and updated.json()["pins"][0]["status"] == "VALID"
        other = await create_session(client)
        leaked = await client.post(f"/api/chat-sessions/{other}/context/pins", json=body)
        assert leaked.status_code in (404, 409)


@pytest.mark.anyio
async def test_recovered_turn_uses_original_pins_and_old_summary_cannot_replace_new_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with recovery_app(
        tmp_path,
        monkeypatch,
        replies=[
            GatedReply(("处理中",), asyncio.Event()),
        ],
    ) as (_app, client, _inputs):
        sid = await create_session(client)
        url = f"/api/chat-sessions/{sid}/context/pins"
        pinned = (
            await client.post(
                url, json={"expected_version": 1, "mode": "TEXT", "content": "原快照固定"}
            )
        ).json()
        turn = (await submit(client, sid, "继续", request_id=str(uuid4()))).json()["id"]
        await wait_running_progress(client, turn, 1)
        removed = await client.post(
            url, json={"expected_version": 2, "action": "REMOVE", "pin_id": pinned["pins"][0]["id"]}
        )
        assert removed.status_code == 200
    async with recovery_app(tmp_path, monkeypatch, replies=[["已恢复"]]) as (_app, client, inputs):
        assert (await wait_terminal(client, turn))["status"] == "COMPLETED"
        assert "原快照固定" in inputs[0][0].text
        view = (await client.get(f"/api/chat-sessions/{sid}/context")).json()
        assert view["version"] == 3 and view["pins"] == [] and view["actual_pins"][0]["injected"]


@pytest.mark.anyio
async def test_adjustable_material_yields_to_pins_in_preview_and_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_shared_refs import REC_ML_PAPER, seed_full_corpus

    async with turns_app(tmp_path, monkeypatch) as (app, client, inputs):
        await seed_full_corpus(app.state.session_factory)
        sid = await create_session(client, scope="RECORD", record_id=REC_ML_PAPER)
        await configure(client, 80000)
        url = f"/api/chat-sessions/{sid}/context"
        base = (await client.get(url)).json()["next_estimate"]
        target_size = max(800, int((base["usable_budget"] * 0.7 - base["input_tokens"]) / 1.5))
        material = "材" * target_size
        async with app.state.session_factory() as db, db.begin():
            await db.execute(
                text("UPDATE transcripts SET content=:content WHERE record_id=:id"),
                {"content": material, "id": REC_ML_PAPER},
            )
        before = (await client.get(url)).json()["next_estimate"]
        assert before["input_tokens"] < before["usable_budget"] * 0.8
        pin = "固定原文" * 1900
        for version in (1, 2):
            pinned = await client.post(
                f"{url}/pins", json={"expected_version": version, "mode": "TEXT", "content": pin}
            )
            assert pinned.status_code == 200
        preview = (await client.get(url)).json()
        assert preview["next_error_code"] is None, preview
        turn = (await submit(client, sid, "继续", request_id=str(uuid4()))).json()["id"]
        done = await wait_terminal(client, turn)
        assert done["status"] == "COMPLETED", done
        assert pin in inputs[0][0].text and material not in inputs[0][0].text


@pytest.mark.anyio
async def test_legacy_read_pin_tracks_underlying_source_and_object_uses_current_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
            ToolCallReply("read_context", {"source_id": f"record:{REC_ML_PAPER}"}),
            ["已读取"],
            ["下一轮"],
        ],
    ) as (app, client, inputs):
        await seed_full_corpus(app.state.session_factory)
        await seed_ref(app.state.session_factory, COURSE_AGENT, ITEM_ML_PAPER)
        sid = await create_session(client, scope="COURSE", course_id=COURSE_AGENT)
        url = f"/api/chat-sessions/{sid}/context"
        turn = (await submit(client, sid, "读原文", request_id=str(uuid4()))).json()["id"]
        assert (await wait_terminal(client, turn))["status"] == "COMPLETED"
        tool = next(
            m for m in inputs[-1] if isinstance(m, ToolMessage) and m.name == "read_context"
        )
        assert tool.id
        read = await client.post(f"{url}/sources/read", json={"source_id": f"message:{tool.id}"})
        assert read.status_code == 200, read.text
        original = read.json()
        pinned = await client.post(
            f"{url}/pins",
            json={
                "expected_version": 1,
                "mode": "SNIPPET",
                "source_id": original["source"]["source_id"],
                "source_version": original["source"]["version"],
                "content": original["content"],
            },
        )
        assert pinned.status_code == 200, pinned.text
        record = (
            await client.post(f"{url}/sources/read", json={"source_id": f"record:{REC_ML_PAPER}"})
        ).json()
        object_pin = await client.post(
            f"{url}/pins",
            json={
                "expected_version": 2,
                "mode": "OBJECT",
                "source_id": record["source"]["source_id"],
                "source_version": record["source"]["version"],
            },
        )
        assert object_pin.status_code == 200, object_pin.text
        async with app.state.session_factory() as db, db.begin():
            await db.execute(
                text(
                    "UPDATE transcripts SET source_version=source_version+1, "
                    "content='当前有效原文' WHERE record_id=:id"
                ),
                {"id": REC_ML_PAPER},
            )
        view = (await client.get(url)).json()
        assert view["pins"][0]["status"] == "STALE"
        assert (
            view["pins"][1]["status"] == "VALID"
            and view["pins"][1]["source_version"] != record["source"]["version"]
        )
        turn = (await submit(client, sid, "继续", request_id=str(uuid4()))).json()["id"]
        assert (await wait_terminal(client, turn))["status"] == "COMPLETED"
        assert "当前有效原文" in inputs[-1][0].text
        view = (await client.get(url)).json()
        assert not view["actual_pins"][0]["injected"] and view["actual_pins"][1]["injected"]


@pytest.mark.anyio
@pytest.mark.parametrize("cancel", [False, True])
async def test_late_compaction_cannot_overwrite_pin_version_or_cancelled_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cancel: bool
) -> None:
    gate = asyncio.Event()
    calls: list[Any] = []
    summary_model(monkeypatch, calls, gate)
    async with turns_app(tmp_path, monkeypatch) as (app, client, inputs):
        sid = await create_session(client)
        url = f"/api/chat-sessions/{sid}/context"
        pinned = (
            await client.post(
                f"{url}/pins", json={"expected_version": 1, "mode": "TEXT", "content": "原固定约束"}
            )
        ).json()
        await seed_history(app, sid, 16, 1000)
        await configure(client)
        turn = (await submit(client, sid, "继续", request_id=str(uuid4()))).json()["id"]
        try:
            await wait_summary_calls(calls, 1)
            if cancel:
                stopped = await client.post(f"/api/chat-turns/{turn}/cancel")
                assert stopped.status_code == 200, stopped.text
            else:
                removed = await client.post(
                    f"{url}/pins",
                    json={
                        "expected_version": 2,
                        "action": "REMOVE",
                        "pin_id": pinned["pins"][0]["id"],
                    },
                )
                assert removed.status_code == 200
        finally:
            gate.set()
        done = await wait_terminal(client, turn)
        assert done["status"] == ("CANCELLED" if cancel else "COMPLETED"), done
        view = (await client.get(url)).json()
        assert view["active_summary"] is None
        if cancel:
            assert view["compactions"][0]["completed_chunks"] == 0 and inputs == []
        else:
            assert view["version"] == 3 and view["pins"] == []
            assert view["compactions"][0]["status"] == "COMPLETED"
            assert "原固定约束" in inputs[-1][0].text


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["REQUEST_APPROVAL", "AUTO_APPROVE"])
async def test_pin_tool_history_and_receipts_cannot_reintroduce_stale_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    from langchain_core.messages import AIMessage, messages_to_dict

    from app.modules.agent.context_budget.retrieval import (
        validate_compaction_sources,
        validate_read_results,
    )
    from app.shared.errors import CodedHTTPException
    from tests.test_shared_refs import REC_ML_PAPER, seed_full_corpus

    args: dict[str, Any] = {"expected_version": 1, "mode": "SNIPPET"}
    async with turns_app(
        tmp_path,
        monkeypatch,
        replies=[
            ToolCallReply("change_context_pin", args),
            ["已提交"],
            ToolCallReply("get_context_settings", {}),
            ["已查看"],
            ["下一轮"],
        ],
    ) as (app, client, inputs):
        await seed_full_corpus(app.state.session_factory)
        sid = await create_session(client, scope="RECORD", record_id=REC_ML_PAPER)
        url = f"/api/chat-sessions/{sid}/context"
        source = (
            await client.post(f"{url}/sources/read", json={"source_id": f"record:{REC_ML_PAPER}"})
        ).json()
        args.update(
            content=source["content"],
            source_id=source["source"]["source_id"],
            source_version=source["source"]["version"],
        )
        assert (await client.put("/api/agent/auth-mode", json={"to_mode": mode})).status_code == 200
        turn = (
            await submit(client, sid, "固定这个资料片段", request_id=str(uuid4()), auth_mode=mode)
        ).json()["id"]
        assert (await wait_terminal(client, turn))["status"] == "COMPLETED"
        if mode == "REQUEST_APPROVAL":
            proposal = (await client.get(f"/api/proposals?session_id={sid}")).json()[0]
            assert (
                await client.post(f"/api/proposals/{proposal['id']}/confirm")
            ).status_code == 200
        turn = (
            await submit(client, sid, "查看固定设置", request_id=str(uuid4()), auth_mode=mode)
        ).json()["id"]
        assert (await wait_terminal(client, turn))["status"] == "COMPLETED"
        original = inputs[-1]
        tool = next(
            m for m in original if isinstance(m, ToolMessage) and m.name == "get_context_settings"
        )
        assert source["content"] in tool.text and tool.id
        read = (
            await client.post(f"{url}/sources/read", json={"source_id": f"message:{tool.id}"})
        ).json()
        pinned = await client.post(
            f"{url}/pins",
            json={
                "expected_version": 2,
                "mode": "SNIPPET",
                "content": read["content"],
                "source_id": read["source"]["source_id"],
                "source_version": read["source"]["version"],
            },
        )
        assert pinned.status_code == 200, pinned.text
        async with app.state.session_factory() as db, db.begin():
            await db.execute(
                text(
                    "UPDATE transcripts SET source_version=source_version+1, "
                    "content='新版材料原文' WHERE record_id=:id"
                ),
                {"id": REC_ML_PAPER},
            )
        rejected = await client.post(
            f"{url}/sources/read", json={"source_id": f"message:{tool.id}"}
        )
        assert rejected.status_code == 409 and rejected.json()["code"] == "CONTEXT_SOURCE_STALE"
        view = (await client.get(url)).json()
        assert all(pin["status"] == "STALE" for pin in view["pins"])
        call = next(m for m in original if isinstance(m, AIMessage) and m.tool_calls)
        duplicate = call.model_copy(
            update={
                "content": [{"type": "text", "text": source["content"]}],
                "additional_kwargs": {
                    "keep": "metadata",
                    "tool_calls": [{"function": {"arguments": json.dumps(args)}}],
                },
            }
        )
        projected_copy = await validate_read_results(app.state.session_factory, sid, [duplicate])
        assert source["content"] not in json.dumps(
            messages_to_dict(projected_copy), ensure_ascii=False
        )
        assert projected_copy[0].additional_kwargs == {"keep": "metadata"}
        async with app.state.session_factory() as db:
            with pytest.raises(CodedHTTPException) as failure:
                await validate_compaction_sources(
                    db,
                    sid,
                    json.dumps(
                        {
                            "sources": {
                                "captured": {
                                    "wire": json.dumps(
                                        messages_to_dict(original), ensure_ascii=False
                                    )
                                }
                            }
                        }
                    ),
                )
            assert failure.value.code == "CONTEXT_SOURCE_STALE"
        turn = (await submit(client, sid, "继续", request_id=str(uuid4()), auth_mode=mode)).json()[
            "id"
        ]
        assert (await wait_terminal(client, turn))["status"] == "COMPLETED"
        assert source["content"] not in str(messages_to_dict(inputs[-1]))
        projected = next(
            m for m in inputs[-1] if isinstance(m, ToolMessage) and m.name == "change_context_pin"
        )
        body = json.loads(projected.text)
        assert body["ok"] is True
        if mode == "AUTO_APPROVE":
            assert body["executed"]["operation_id"] and body["executed"]["result"]["version"] == 2
        assert any(isinstance(m, AIMessage) and m.tool_calls for m in inputs[-1])
        assert source["content"] in tool.text, "模型投影不能改写原请求或回执事实"
