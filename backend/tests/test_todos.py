import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.agents.llm import StructuredModelResult
from app.db.migrations import run_migrations
from app.main import create_app

TOKEN = "test-launch-token"

RECORD_ID = "11111111-1111-4111-8111-111111111111"
SUMMARY_ID = "33333333-3333-4333-8333-333333333333"
OTHER_RECORD_ID = "22222222-2222-4222-8222-222222222222"
OTHER_SUMMARY_ID = "44444444-4444-4444-8444-444444444444"
SUPERSEDED_SUMMARY_ID = "55555555-5555-4555-8555-555555555555"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@asynccontextmanager
async def running_todo_app(data_dir: Path) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(data_dir=data_dir, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client


class FakeTodoModel:
    def __init__(self, *outputs: object, blocked: bool = False) -> None:
        default_output = {
            "items": [
                {"content": "复习进程调度"},
                {"content": "完成课后调度题"},
                {"content": "整理调度算法对比"},
            ]
        }
        self.outputs = list(outputs) or [default_output]
        self.prompt = ""
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        if not blocked:
            self.release.set()

    async def generate(self, **kwargs: object) -> StructuredModelResult:
        self.prompt = cast(str, kwargs["prompt"])
        self.started.set()
        await self.release.wait()
        output = self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]
        return StructuredModelResult(output=output, token_usage={"total_tokens": 12})


async def configure_todo_generation(client: httpx.AsyncClient) -> None:
    provider = await client.put(
        "/api/settings/providers/llm",
        json={
            "base_url": "https://example.invalid/v1",
            "api_key": "secret",
            "model": "fake-model",
        },
    )
    consent = await client.post("/api/settings/external-processing-consents/llm")
    assert provider.status_code == 200
    assert consent.status_code == 200


async def wait_for_todo_job(client: httpx.AsyncClient, job_id: str) -> dict[str, object]:
    for _ in range(100):
        response = await client.get(f"/api/processing-jobs/{job_id}")
        payload = cast(dict[str, object], response.json())
        if payload["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return payload
        await __import__("asyncio").sleep(0.02)
    raise AssertionError("Todo 生成任务未结束")


@asynccontextmanager
async def running_generated_todo_app(
    data_dir: Path, model: FakeTodoModel
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(data_dir=data_dir, launch_token=TOKEN, todo_model=model)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client


async def seed_record(
    app: FastAPI,
    client: httpx.AsyncClient,
    *,
    record_id: str = RECORD_ID,
    summary_status: str | None = "CONFIRMED",
) -> None:
    course = await client.post(
        "/api/courses",
        json={
            "name": "操作系统",
            "learning_context": "SCHOOL",
            "education_stage": "UNDERGRADUATE",
        },
    )
    course_id = cast(str, course.json()["id"])
    now = "2026-08-25T12:00:00.000000Z"
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO records "
                "(id, course_id, capture_type, title, status, duration_ms, "
                "summary_confirmed_at, created_at, updated_at, deleted_at) "
                "VALUES (:id, :course_id, 'DOCUMENT_IMPORT', '进程调度', "
                "'COMPLETED', 0, :now, :now, :now, NULL)"
            ),
            {"id": record_id, "course_id": course_id, "now": now},
        )
        if summary_status is not None:
            await session.execute(
                text(
                    "INSERT INTO ai_summaries "
                    "(id, record_id, version_no, transcript_source_version, topic, abstract, "
                    "summary_json, status, model, prompt_version, token_usage_json, latency_ms, "
                    "user_feedback, confirmed_at, created_at, updated_at, deleted_at) "
                    "VALUES (:id, :record_id, 1, 1, '进程调度', :abstract, "
                    ":summary_json, :status, 'qwen-plus', 'summary-v1', '{}', 10, NULL, "
                    ":confirmed_at, :now, :now, NULL)"
                ),
                {
                    "id": SUMMARY_ID if record_id == RECORD_ID else OTHER_SUMMARY_ID,
                    "record_id": record_id,
                    "abstract": "总结介绍了调度策略。" * 50,
                    "summary_json": json.dumps(
                        {"sections": [{"heading": "调度", "points": ["调度器选择就绪进程。"]}]},
                        ensure_ascii=False,
                    ),
                    "status": summary_status,
                    "confirmed_at": now if summary_status == "CONFIRMED" else None,
                    "now": now,
                },
            )


async def create_todo(
    client: httpx.AsyncClient,
    content: str,
    *,
    record_id: str = RECORD_ID,
) -> httpx.Response:
    return await client.post(f"/api/records/{record_id}/todos", json={"content": content})


async def read_todos(client: httpx.AsyncClient, *, record_id: str = RECORD_ID) -> dict[str, object]:
    response = await client.get(f"/api/records/{record_id}/todos")
    assert response.status_code == 200, response.text
    return cast(dict[str, object], response.json())


def first_item(payload: dict[str, object]) -> dict[str, object]:
    items = cast(list[dict[str, object]], payload["items"])
    assert items
    return items[0]


@pytest.mark.anyio
async def test_generate_todo_candidates_persists_one_draft_batch(tmp_path: Path) -> None:
    model = FakeTodoModel()
    async with running_generated_todo_app(tmp_path, model) as (app, client):
        await seed_record(app, client)
        await configure_todo_generation(client)
        submitted = await client.post(f"/api/records/{RECORD_ID}/todo-jobs")
        assert submitted.status_code == 202, submitted.text
        job_id = cast(str, submitted.json()["job_id"])

        await wait_for_todo_job(client, job_id)
        payload = await read_todos(client)
        async with app.state.session_factory() as session:
            result_json = await session.scalar(
                text("SELECT result_json FROM processing_jobs WHERE id=:id"), {"id": job_id}
            )

    items = cast(list[dict[str, object]], payload["items"])
    assert [item["content"] for item in items] == [
        "复习进程调度",
        "完成课后调度题",
        "整理调度算法对比",
    ]
    assert all(item["batch_id"] == job_id for item in items)
    assert all(item["generation_status"] == "DRAFT" for item in items)
    assert payload["action_required"] == "ADOPT"
    assert json.loads(cast(str, result_json))["prompt_version"] == "todo_v1"
    assert "已确认总结" in model.prompt and "总结介绍了调度策略" in model.prompt


@pytest.mark.anyio
@pytest.mark.parametrize(
    "invalid_output",
    [
        {"items": [{"content": "只有一条"}]},
        {"items": [{"content": "第一条"}, {"content": "   "}, {"content": "第三条"}]},
    ],
)
async def test_invalid_output_retry_reuses_failed_todo_job(
    tmp_path: Path, invalid_output: object
) -> None:
    model = FakeTodoModel(invalid_output, FakeTodoModel().outputs[0])
    async with running_generated_todo_app(tmp_path, model) as (app, client):
        await seed_record(app, client)
        await configure_todo_generation(client)
        first = await client.post(f"/api/records/{RECORD_ID}/todo-jobs")
        first_id = cast(str, first.json()["job_id"])
        failed = await wait_for_todo_job(client, first_id)
        assert failed["status"] == "FAILED"
        assert failed["error_code"] == "LLM_OUTPUT_INVALID"
        assert (await read_todos(client))["action_required"] == "RETRY"

        retried = await client.post(f"/api/records/{RECORD_ID}/todo-jobs")
        assert retried.status_code == 202
        assert retried.json()["job_id"] == first_id
        assert (await wait_for_todo_job(client, first_id))["status"] == "SUCCEEDED"


@pytest.mark.anyio
async def test_failed_job_from_old_summary_is_not_retried(tmp_path: Path) -> None:
    model = FakeTodoModel({"items": [{"content": "只有一条"}]}, FakeTodoModel().outputs[0])
    async with running_generated_todo_app(tmp_path, model) as (app, client):
        await seed_record(app, client)
        await configure_todo_generation(client)
        first = await client.post(f"/api/records/{RECORD_ID}/todo-jobs")
        first_id = cast(str, first.json()["job_id"])
        assert (await wait_for_todo_job(client, first_id))["status"] == "FAILED"

        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE ai_summaries SET status='SUPERSEDED' WHERE id=:id"),
                {"id": SUMMARY_ID},
            )
            await session.execute(
                text(
                    "INSERT INTO ai_summaries "
                    "(id, record_id, version_no, transcript_source_version, topic, abstract, "
                    "summary_json, status, model, prompt_version, token_usage_json, latency_ms, "
                    "user_feedback, confirmed_at, created_at, updated_at, deleted_at) "
                    "SELECT :id, record_id, 2, transcript_source_version, topic, abstract, "
                    "summary_json, 'CONFIRMED', model, prompt_version, token_usage_json, "
                    "latency_ms, NULL, updated_at, created_at, updated_at, NULL "
                    "FROM ai_summaries WHERE id=:old_id"
                ),
                {"id": SUPERSEDED_SUMMARY_ID, "old_id": SUMMARY_ID},
            )

        assert (await read_todos(client))["action_required"] == "GENERATE"
        second = await client.post(f"/api/records/{RECORD_ID}/todo-jobs")
        second_id = cast(str, second.json()["job_id"])
        assert second_id != first_id
        assert (await wait_for_todo_job(client, second_id))["status"] == "SUCCEEDED"


@pytest.mark.anyio
async def test_running_todo_job_rejects_duplicate_submission(tmp_path: Path) -> None:
    model = FakeTodoModel(blocked=True)
    async with running_generated_todo_app(tmp_path, model) as (app, client):
        await seed_record(app, client)
        await configure_todo_generation(client)
        first = await client.post(f"/api/records/{RECORD_ID}/todo-jobs")
        first_id = cast(str, first.json()["job_id"])
        await asyncio.wait_for(model.started.wait(), timeout=2)
        duplicate = await client.post(f"/api/records/{RECORD_ID}/todo-jobs")
        model.release.set()
        finished = await wait_for_todo_job(client, first_id)

    assert duplicate.status_code == 409
    assert finished["status"] == "SUCCEEDED"


@pytest.mark.anyio
async def test_todo_generation_rejects_missing_prerequisites_and_archive(
    tmp_path: Path,
) -> None:
    model = FakeTodoModel()
    async with running_generated_todo_app(tmp_path, model) as (app, client):
        await seed_record(app, client, summary_status=None)
        await seed_record(app, client, record_id=OTHER_RECORD_ID)

        no_provider = await client.post(f"/api/records/{RECORD_ID}/todo-jobs")
        assert no_provider.status_code == 409
        await client.put(
            "/api/settings/providers/llm",
            json={
                "base_url": "https://example.invalid/v1",
                "api_key": "secret",
                "model": "fake-model",
            },
        )
        no_consent = await client.post(f"/api/records/{RECORD_ID}/todo-jobs")
        assert no_consent.status_code == 409
        await client.post("/api/settings/external-processing-consents/llm")
        no_summary = await client.post(f"/api/records/{RECORD_ID}/todo-jobs")
        assert no_summary.status_code == 409

        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE courses SET status='ARCHIVED' WHERE id="
                    "(SELECT course_id FROM records WHERE id=:record_id)"
                ),
                {"record_id": OTHER_RECORD_ID},
            )
        archived = await client.post(f"/api/records/{OTHER_RECORD_ID}/todo-jobs")
        assert archived.status_code == 409


@pytest.mark.anyio
async def test_prune_adopt_and_discard_todo_batches(tmp_path: Path) -> None:
    model = FakeTodoModel(
        {
            "items": [
                {"content": "复习进程调度"},
                {"content": "完成课后调度题"},
                {"content": "整理调度算法对比"},
                {"content": "画出调度时序图"},
            ]
        }
    )
    async with running_generated_todo_app(tmp_path, model) as (app, client):
        await seed_record(app, client)
        await configure_todo_generation(client)
        manual = await create_todo(client, "用户手工项")
        submitted = await client.post(f"/api/records/{RECORD_ID}/todo-jobs")
        batch_id = cast(str, submitted.json()["job_id"])
        await wait_for_todo_job(client, batch_id)
        draft = await read_todos(client)
        duplicate = await client.post(f"/api/records/{RECORD_ID}/todo-jobs")
        candidates = [
            item
            for item in cast(list[dict[str, object]], draft["items"])
            if item["generation_status"] == "DRAFT"
        ]
        edited = await client.patch(
            f"/api/records/{RECORD_ID}/todos/{candidates[0]['id']}",
            json={"content": "修剪后的建议"},
        )
        deleted = await client.delete(f"/api/records/{RECORD_ID}/todos/{candidates[1]['id']}")
        toggled = await client.post(
            f"/api/records/{RECORD_ID}/todos/{candidates[2]['id']}/toggles",
            json={"status": "DONE"},
        )
        adopted = await client.post(
            f"/api/records/{RECORD_ID}/todo-batches/{batch_id}/confirmations"
        )

        assert edited.status_code == 200
        assert deleted.status_code == 204
        assert toggled.status_code == 409
        assert duplicate.status_code == 409
        assert adopted.status_code == 200, adopted.text
        adopted_items = cast(list[dict[str, object]], adopted.json()["items"])
        assert any(item["id"] == manual.json()["id"] for item in adopted_items)
        assert [
            item["content"] for item in adopted_items if item["generation_status"] == "ACTIVE"
        ] == ["修剪后的建议", "整理调度算法对比", "画出调度时序图"]

        active = [item for item in adopted_items if item["generation_status"] == "ACTIVE"]
        edited_active = await client.patch(
            f"/api/records/{RECORD_ID}/todos/{active[0]['id']}",
            json={"content": "用户接管后的建议"},
        )
        toggled_active = await client.post(
            f"/api/records/{RECORD_ID}/todos/{active[1]['id']}/toggles",
            json={"status": "DONE"},
        )
        repeated_toggle = await client.post(
            f"/api/records/{RECORD_ID}/todos/{active[1]['id']}/toggles",
            json={"status": "DONE"},
        )
        assert edited_active.json()["generation_status"] is None
        assert toggled_active.json()["generation_status"] is None
        assert repeated_toggle.json()["generation_status"] is None

        second = await client.post(f"/api/records/{RECORD_ID}/todo-jobs")
        second_id = cast(str, second.json()["job_id"])
        await wait_for_todo_job(client, second_id)
        second_adopted = await client.post(
            f"/api/records/{RECORD_ID}/todo-batches/{second_id}/confirmations"
        )
        visible = cast(list[dict[str, object]], second_adopted.json()["items"])
        history = await client.get(
            f"/api/records/{RECORD_ID}/todos", params={"include": "superseded"}
        )
        assert not any(
            item.get("batch_id") == batch_id and item["generation_status"] == "ACTIVE"
            for item in visible
        )
        assert (
            len(
                [
                    item
                    for item in visible
                    if item.get("batch_id") == batch_id and item["generation_status"] is None
                ]
            )
            == 2
        )
        assert any(item["id"] == manual.json()["id"] for item in visible)
        assert any(
            item["batch_id"] == batch_id and item["generation_status"] == "SUPERSEDED"
            for item in history.json()["items"]
        )

        third = await client.post(f"/api/records/{RECORD_ID}/todo-jobs")
        third_id = cast(str, third.json()["job_id"])
        await wait_for_todo_job(client, third_id)
        discarded = await client.post(f"/api/records/{RECORD_ID}/todo-batches/{third_id}/discards")
        assert discarded.status_code == 200
        assert discarded.json()["action_required"] == "GENERATE"

        stale = await client.post(f"/api/records/{RECORD_ID}/todo-jobs")
        stale_id = cast(str, stale.json()["job_id"])
        await wait_for_todo_job(client, stale_id)
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE ai_summaries SET status='SUPERSEDED' WHERE id=:id"),
                {"id": SUMMARY_ID},
            )
        stale_adopt = await client.post(
            f"/api/records/{RECORD_ID}/todo-batches/{stale_id}/confirmations"
        )
        assert stale_adopt.status_code == 409
        assert stale_adopt.json()["blocked_reason"] == "SUMMARY_SUPERSEDED"
        assert (
            await client.post(f"/api/records/{RECORD_ID}/todo-batches/{stale_id}/discards")
        ).status_code == 200


@pytest.mark.anyio
async def test_todo_migration_creates_table(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"

    await run_migrations(db_path)

    async with aiosqlite.connect(db_path) as connection:
        version = await (await connection.execute("PRAGMA user_version")).fetchone()
        columns = {
            row[1]
            for row in await (await connection.execute("PRAGMA table_info(todo_items)")).fetchall()
        }
    assert version is not None and version[0] == 13
    assert columns == {
        "id",
        "record_id",
        "batch_id",
        "content",
        "status",
        "source",
        "generated_from_summary_id",
        "generation_status",
        "sort_order",
        "created_at",
        "updated_at",
        "deleted_at",
    }


@pytest.mark.anyio
async def test_manual_crud_roundtrip(tmp_path: Path) -> None:
    async with running_todo_app(tmp_path) as (app, client):
        missing = await client.get("/api/records/99999999-9999-4999-8999-999999999999/todos")
        assert missing.status_code == 404

        await seed_record(app, client, summary_status=None)
        created = await create_todo(client, "复习进程调度一节")
        assert created.status_code == 201, created.text
        body = cast(dict[str, object], created.json())
        todo_id = cast(str, body["id"])
        assert body["record_id"] == RECORD_ID
        assert body["content"] == "复习进程调度一节"
        assert body["status"] == "TODO"
        assert body["source"] == "MANUAL"
        assert body["batch_id"] is None
        assert body["generated_from_summary_id"] is None
        assert body["generation_status"] is None
        assert body["sort_order"] == 0

        payload = await read_todos(client)
        assert payload["items"] == [body]
        assert payload["action_required"] == "NONE"
        assert payload["active_job_id"] is None
        # 无总结只限制生成入口，不影响清单与手动操作
        assert payload["blocked_reason"] == "SUMMARY_NOT_CONFIRMED"

        edited = await client.patch(
            f"/api/records/{RECORD_ID}/todos/{todo_id}",
            json={"content": "复习进程调度并补作业"},
        )
        assert edited.status_code == 200
        assert cast(dict[str, object], edited.json())["content"] == "复习进程调度并补作业"

        deleted = await client.delete(f"/api/records/{RECORD_ID}/todos/{todo_id}")
        assert deleted.status_code == 204
        assert (await read_todos(client))["items"] == []

        again = await client.delete(f"/api/records/{RECORD_ID}/todos/{todo_id}")
        assert again.status_code == 404
        missing_edit = await client.patch(
            f"/api/records/{RECORD_ID}/todos/{todo_id}", json={"content": "已删"}
        )
        assert missing_edit.status_code == 404
        missing_toggle = await client.post(
            f"/api/records/{RECORD_ID}/todos/{todo_id}/toggles", json={"status": "DONE"}
        )
        assert missing_toggle.status_code == 404


@pytest.mark.anyio
async def test_content_validation_rejects_blank_and_overlong(tmp_path: Path) -> None:
    async with running_todo_app(tmp_path) as (app, client):
        await seed_record(app, client, summary_status=None)

        blank = await create_todo(client, "   ")
        assert blank.status_code == 422
        empty = await create_todo(client, "")
        assert empty.status_code == 422
        overlong = await create_todo(client, "长" * 501)
        assert overlong.status_code == 422
        boundary = await create_todo(client, "长" * 500)
        assert boundary.status_code == 201


@pytest.mark.anyio
async def test_toggle_is_idempotent_and_survives_restart(tmp_path: Path) -> None:
    async with running_todo_app(tmp_path) as (app, client):
        await seed_record(app, client, summary_status=None)
        created = await create_todo(client, "查参考资料")
        todo_id = cast(str, cast(dict[str, object], created.json())["id"])

        done = await client.post(
            f"/api/records/{RECORD_ID}/todos/{todo_id}/toggles", json={"status": "DONE"}
        )
        assert done.status_code == 200
        assert cast(dict[str, object], done.json())["status"] == "DONE"

        # 重复置同态幂等返回现状
        repeat = await client.post(
            f"/api/records/{RECORD_ID}/todos/{todo_id}/toggles", json={"status": "DONE"}
        )
        assert repeat.status_code == 200
        assert cast(dict[str, object], repeat.json())["status"] == "DONE"
        assert first_item(await read_todos(client))["status"] == "DONE"

        # 取消勾选恢复未完成态
        undone = await client.post(
            f"/api/records/{RECORD_ID}/todos/{todo_id}/toggles", json={"status": "TODO"}
        )
        assert cast(dict[str, object], undone.json())["status"] == "TODO"

    # 重启（同一数据目录重新起应用与迁移）后勾选状态保持
    async with running_todo_app(tmp_path) as (_app, client):
        payload = await read_todos(client)
        assert first_item(payload)["status"] == "TODO"


@pytest.mark.anyio
async def test_manual_items_append_in_creation_order(tmp_path: Path) -> None:
    async with running_todo_app(tmp_path) as (app, client):
        await seed_record(app, client, summary_status=None)
        for content in ("第一条", "第二条", "第三条"):
            response = await create_todo(client, content)
            assert response.status_code == 201

        payload = await read_todos(client)
        items = cast(list[dict[str, object]], payload["items"])
        assert [item["content"] for item in items] == ["第一条", "第二条", "第三条"]
        assert [item["sort_order"] for item in items] == [0, 1, 2]

        # 删除中间项后再追加：新条目仍排在尾部，不复用空位
        await client.delete(f"/api/records/{RECORD_ID}/todos/{items[1]['id']}")
        appended = await create_todo(client, "第四条")
        assert cast(dict[str, object], appended.json())["sort_order"] == 3
        payload = await read_todos(client)
        assert [item["content"] for item in cast(list[dict[str, object]], payload["items"])] == [
            "第一条",
            "第三条",
            "第四条",
        ]


@pytest.mark.anyio
async def test_blocked_reasons_never_block_manual_crud(tmp_path: Path) -> None:
    async with running_todo_app(tmp_path) as (app, client):
        # 无任何总结 → SUMMARY_NOT_CONFIRMED，手动增删改勾照常可用
        await seed_record(app, client, summary_status=None)
        payload = await read_todos(client)
        assert payload["blocked_reason"] == "SUMMARY_NOT_CONFIRMED"
        assert payload["action_required"] == "NONE"

        created = await create_todo(client, "未确认总结时也能记账")
        assert created.status_code == 201
        todo_id = cast(str, cast(dict[str, object], created.json())["id"])
        toggled = await client.post(
            f"/api/records/{RECORD_ID}/todos/{todo_id}/toggles", json={"status": "DONE"}
        )
        assert toggled.status_code == 200
        edited = await client.patch(
            f"/api/records/{RECORD_ID}/todos/{todo_id}", json={"content": "改写待办"}
        )
        assert edited.status_code == 200
        payload = await read_todos(client)
        assert payload["blocked_reason"] == "SUMMARY_NOT_CONFIRMED"
        assert first_item(payload)["content"] == "改写待办"
        assert first_item(payload)["status"] == "DONE"
        removed = await client.delete(f"/api/records/{RECORD_ID}/todos/{todo_id}")
        assert removed.status_code == 204

        # 仅存在已换代总结 → SUMMARY_SUPERSEDED，手动仍可用
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO ai_summaries "
                    "(id, record_id, version_no, transcript_source_version, topic, abstract, "
                    "summary_json, status, model, prompt_version, token_usage_json, latency_ms, "
                    "user_feedback, confirmed_at, created_at, updated_at, deleted_at) "
                    "VALUES (:id, :record_id, 1, 1, '进程调度', '旧版总结。', '{}', "
                    "'SUPERSEDED', 'qwen-plus', 'summary-v1', '{}', 10, NULL, NULL, "
                    "'2026-08-25T12:00:00.000000Z', '2026-08-25T12:00:00.000000Z', NULL)"
                ),
                {"id": SUPERSEDED_SUMMARY_ID, "record_id": RECORD_ID},
            )
        assert (await read_todos(client))["blocked_reason"] == "SUMMARY_SUPERSEDED"
        superseded_create = await create_todo(client, "换代状态下仍可记录")
        assert superseded_create.status_code == 201

        # 课程归档 → COURSE_ARCHIVED，手动仍可用
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE courses SET status='ARCHIVED' WHERE id="
                    "(SELECT course_id FROM records WHERE id=:record_id)"
                ),
                {"record_id": RECORD_ID},
            )
        assert (await read_todos(client))["blocked_reason"] == "COURSE_ARCHIVED"
        archived_create = await create_todo(client, "归档课程也能记录")
        assert archived_create.status_code == 201

    # 已确认总结但未配置 Provider / 未同意外发 → 两种 blocked，手动仍可用
    async with running_todo_app(tmp_path) as (app, client):
        await seed_record(app, client, record_id=OTHER_RECORD_ID)
        payload = await read_todos(client, record_id=OTHER_RECORD_ID)
        assert payload["blocked_reason"] == "PROVIDER_NOT_CONFIGURED"
        no_provider_create = await create_todo(
            client, "未配置 Provider 也能记录", record_id=OTHER_RECORD_ID
        )
        assert no_provider_create.status_code == 201

        configured = await client.put(
            "/api/settings/providers/llm",
            json={
                "base_url": "https://example.com/v1",
                "api_key": "sk-test",
                "model": "qwen-plus",
            },
        )
        assert configured.status_code == 200
        payload = await read_todos(client, record_id=OTHER_RECORD_ID)
        assert payload["blocked_reason"] == "CONSENT_REQUIRED"
        no_consent_create = await create_todo(
            client, "未同意外发也能记录", record_id=OTHER_RECORD_ID
        )
        assert no_consent_create.status_code == 201

        consent = await client.post("/api/settings/external-processing-consents/llm")
        assert consent.status_code == 200
        payload = await read_todos(client, record_id=OTHER_RECORD_ID)
        assert payload["blocked_reason"] is None
        assert payload["action_required"] == "GENERATE"


@pytest.mark.anyio
async def test_record_soft_delete_cascades_todo_rows(tmp_path: Path) -> None:
    async with running_todo_app(tmp_path) as (app, client):
        await seed_record(app, client, summary_status=None)
        await create_todo(client, "待办一")
        await create_todo(client, "待办二")
        todo_id = cast(str, first_item(await read_todos(client))["id"])
        done = await client.post(
            f"/api/records/{RECORD_ID}/todos/{todo_id}/toggles", json={"status": "DONE"}
        )
        assert done.status_code == 200

        deleted = await client.delete(f"/api/records/{RECORD_ID}")
        assert deleted.status_code == 204

        todos_after_delete = await client.get(f"/api/records/{RECORD_ID}/todos")
        assert todos_after_delete.status_code == 404
        async with app.state.session_factory() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM todo_items "
                        "WHERE record_id=:record_id AND deleted_at IS NULL"
                    ),
                    {"record_id": RECORD_ID},
                )
            ).scalar()
            assert rows == 0


@pytest.mark.anyio
async def test_include_superseded_query_parameter_is_accepted(tmp_path: Path) -> None:
    async with running_todo_app(tmp_path) as (app, client):
        await seed_record(app, client, summary_status=None)
        created = await create_todo(client, "可见待办")
        assert created.status_code == 201

        superseded_view = await client.get(
            f"/api/records/{RECORD_ID}/todos", params={"include": "superseded"}
        )
        assert superseded_view.status_code == 200
        payload = cast(dict[str, object], superseded_view.json())
        assert len(cast(list[object], payload["items"])) == 1
