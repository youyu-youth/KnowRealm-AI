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

from app.agents.llm import SummaryModel, SummaryModelResult
from app.db.migrations import MIGRATIONS_DIR, run_migrations
from app.main import create_app
from app.schemas.summary import SummaryContent, SummarySection

TOKEN = "test-launch-token"


@asynccontextmanager
async def running_summary_app(
    data_dir: Path,
    *,
    summary_model: SummaryModel | None = None,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(
        data_dir=data_dir,
        launch_token=TOKEN,
        summary_model=summary_model,
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client


def valid_summary() -> SummaryContent:
    return SummaryContent(
        topic="操作系统中的进程调度",
        abstract="这是一段用于验证正式结构化总结契约的摘要。" * 30,
        sections=[
            SummarySection(
                heading="核心机制",
                points=["调度器按照既定策略选择下一个获得处理器时间的进程。"],
            )
        ],
    )


class FakeSummaryModel:
    def __init__(self, output: object | None = None) -> None:
        self.output = output if output is not None else valid_summary()
        self.prompts: list[str] = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()

    async def generate(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
    ) -> SummaryModelResult:
        assert base_url.startswith("https://")
        assert api_key == "sk-test"
        assert model == "qwen-plus"
        self.prompts.append(prompt)
        self.started.set()
        await self.release.wait()
        return SummaryModelResult(output=self.output, token_usage={"total_tokens": 42})


async def create_pending_record(app: FastAPI, client: httpx.AsyncClient) -> str:
    course = await client.post(
        "/api/courses",
        json={
            "name": "操作系统",
            "learning_context": "SCHOOL",
            "education_stage": "UNDERGRADUATE",
        },
    )
    course_id = cast(str, course.json()["id"])
    async with app.state.session_factory() as session, session.begin():
        record_id = "11111111-1111-4111-8111-111111111111"
        now = "2026-08-23T12:00:00.000000Z"
        await session.execute(
            text(
                "INSERT INTO records "
                "(id, course_id, capture_type, title, status, duration_ms, "
                "summary_confirmed_at, created_at, updated_at, deleted_at) "
                "VALUES (:id, :course_id, 'DOCUMENT_IMPORT', '进程调度', "
                "'SUMMARY_PENDING', 0, NULL, :now, :now, NULL)"
            ),
            {"id": record_id, "course_id": course_id, "now": now},
        )
        await session.execute(
            text(
                "INSERT INTO transcripts "
                "(id, record_id, language, content, source_version, edited_by_user, "
                "created_at, updated_at, deleted_at) "
                "VALUES ('22222222-2222-4222-8222-222222222222', :record_id, 'zh-CN', "
                ":content, 1, 0, :now, :now, NULL)"
            ),
            {
                "record_id": record_id,
                "content": "进程调度用于决定就绪进程获得处理器的顺序。",
                "now": now,
            },
        )
    return record_id


async def configure_provider(client: httpx.AsyncClient) -> None:
    response = await client.put(
        "/api/settings/providers/llm",
        json={
            "base_url": "https://example.com/v1",
            "api_key": "sk-test",
            "model": "qwen-plus",
        },
    )
    assert response.status_code == 200


async def wait_for_record_status(
    client: httpx.AsyncClient,
    record_id: str,
    status: str,
) -> None:
    for _ in range(200):
        if (await client.get(f"/api/records/{record_id}")).json()["status"] == status:
            return
        await asyncio.sleep(0.02)
    pytest.fail(f"Record 未进入 {status}")


async def assert_summary_schema(db_path: Path) -> None:
    async with aiosqlite.connect(db_path) as connection:
        version = await (await connection.execute("PRAGMA user_version")).fetchone()
        tables = {
            cast(str, row[0])
            for row in await (
                await connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }
        indexes = {
            cast(str, row[1])
            for row in await (
                await connection.execute("PRAGMA index_list(processing_jobs)")
            ).fetchall()
        }

    assert version == (8,)
    assert {"ai_summaries", "llm_call_logs", "learning_events"} <= tables
    assert "idx_processing_jobs_one_active_summary" in indexes


@pytest.mark.anyio
async def test_summary_migration_is_identical_for_fresh_and_v7_upgrade(tmp_path: Path) -> None:
    fresh_db = tmp_path / "fresh.db"
    upgraded_db = tmp_path / "upgraded.db"

    await run_migrations(fresh_db)
    async with aiosqlite.connect(upgraded_db) as connection:
        for migration in sorted(MIGRATIONS_DIR.glob("000[1-7]_*.sql")):
            await connection.executescript(migration.read_text(encoding="utf-8"))
        await connection.execute("PRAGMA user_version=7")
        await connection.commit()
    await run_migrations(upgraded_db)

    await assert_summary_schema(fresh_db)
    await assert_summary_schema(upgraded_db)


@pytest.mark.anyio
async def test_llm_provider_masks_key_preserves_empty_update_and_invalidates_consent(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with running_summary_app(data_dir) as (_app, client):
        missing = await client.get("/api/settings/providers/llm")
        saved = await client.put(
            "/api/settings/providers/llm",
            json={
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "api_key": "sk-secret-value",
                "model": "qwen-plus",
            },
        )
        consent = await client.post("/api/settings/external-processing-consents/llm")
        model_only = await client.put(
            "/api/settings/providers/llm",
            json={
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "api_key": "",
                "model": "qwen-max",
            },
        )
        consent_after_model = await client.get("/api/settings/external-processing-consents/llm")
        changed_endpoint = await client.put(
            "/api/settings/providers/llm",
            json={
                "base_url": "https://example.com/v1",
                "api_key": "",
                "model": "qwen-max",
            },
        )
        consent_after_endpoint = await client.get("/api/settings/external-processing-consents/llm")
        cleared = await client.put(
            "/api/settings/providers/llm",
            json={
                "base_url": "https://example.com/v1",
                "api_key": "",
                "model": "qwen-max",
                "clear_api_key": True,
            },
        )

    assert missing.status_code == 200
    assert missing.json() == {"provider": None}
    assert saved.status_code == 200
    assert saved.json() == {
        "provider": {
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen-plus",
            "has_api_key": True,
            "api_key_hint": "••••alue",
        }
    }
    assert "sk-secret-value" not in saved.text
    assert consent.status_code == 200
    assert consent.json()["current"] is True
    assert model_only.json()["provider"]["has_api_key"] is True
    assert consent_after_model.json()["current"] is True
    assert changed_endpoint.json()["provider"]["has_api_key"] is True
    assert consent_after_endpoint.json()["current"] is False
    assert cleared.json()["provider"]["has_api_key"] is False

    providers = json.loads((data_dir / "config" / "providers.json").read_text(encoding="utf-8"))
    assert providers["llm"]["api_key"] == ""


@pytest.mark.anyio
async def test_llm_provider_rejects_unsafe_endpoint_and_cannot_consent_without_key(
    tmp_path: Path,
) -> None:
    async with running_summary_app(tmp_path / "KnowRealm") as (_app, client):
        embedded_credentials = await client.put(
            "/api/settings/providers/llm",
            json={
                "base_url": "https://user:password@example.com/v1",
                "api_key": "sk-test",
                "model": "model",
            },
        )
        local_file = await client.put(
            "/api/settings/providers/llm",
            json={
                "base_url": "file:///tmp/provider",
                "api_key": "sk-test",
                "model": "model",
            },
        )
        await client.put(
            "/api/settings/providers/llm",
            json={
                "base_url": "https://example.com/v1",
                "api_key": "",
                "model": "model",
                "clear_api_key": True,
            },
        )
        consent = await client.post("/api/settings/external-processing-consents/llm")

    assert embedded_credentials.status_code == 422
    assert local_file.status_code == 422
    assert consent.status_code == 409


@pytest.mark.anyio
async def test_connection_test_uses_synthetic_text_and_formal_summary_schema(
    tmp_path: Path,
) -> None:
    fake = FakeSummaryModel()
    async with running_summary_app(tmp_path / "KnowRealm", summary_model=fake) as (_app, client):
        await configure_provider(client)
        response = await client.post("/api/settings/providers/llm/tests")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "model": "qwen-plus"}
    assert len(fake.prompts) == 1
    assert "合成" in fake.prompts[0]
    assert "进程调度用于决定" not in fake.prompts[0]


@pytest.mark.anyio
async def test_summary_actions_submit_once_and_publish_first_immutable_version(
    tmp_path: Path,
) -> None:
    fake = FakeSummaryModel()
    async with running_summary_app(tmp_path / "KnowRealm", summary_model=fake) as (app, client):
        record_id = await create_pending_record(app, client)
        missing_provider = await client.get(f"/api/records/{record_id}/summary")
        await configure_provider(client)
        missing_consent = await client.get(f"/api/records/{record_id}/summary")
        await client.post("/api/settings/external-processing-consents/llm")
        ready_to_generate = await client.get(f"/api/records/{record_id}/summary")

        first = await client.post(f"/api/records/{record_id}/summary-jobs")
        duplicate = await client.post(f"/api/records/{record_id}/summary-jobs")
        await wait_for_record_status(client, record_id, "SUMMARY_READY")
        current = await client.get(f"/api/records/{record_id}/summary")
        jobs = await client.get(f"/api/records/{record_id}/jobs")

        async with app.state.session_factory() as session:
            summary_count = await session.scalar(text("SELECT count(*) FROM ai_summaries"))
            log_row = (
                await session.execute(
                    text(
                        "SELECT graph_name, graph_node, model, prompt_version, error_code "
                        "FROM llm_call_logs WHERE graph_name='summary'"
                    )
                )
            ).one()

    assert missing_provider.json()["action_required"] == "CONFIGURE_PROVIDER"
    assert missing_consent.json()["action_required"] == "GRANT_CONSENT"
    assert ready_to_generate.json()["action_required"] == "GENERATE"
    assert first.status_code == 202
    assert duplicate.status_code == 202
    assert first.json()["job_id"] == duplicate.json()["job_id"]
    assert len(fake.prompts) == 1
    assert current.json()["action_required"] == "NONE"
    assert current.json()["summary"]["topic"] == "操作系统中的进程调度"
    assert current.json()["summary"]["version_no"] == 1
    assert [job["job_type"] for job in jobs.json()["jobs"]] == ["SUMMARY"]
    assert summary_count == 1
    assert tuple(log_row) == ("summary", "generate", "qwen-plus", "summary-v1", None)


@pytest.mark.anyio
async def test_invalid_output_fails_once_without_saving_summary(tmp_path: Path) -> None:
    fake = FakeSummaryModel(
        {
            "topic": "",
            "abstract": "过短",
            "sections": [],
        }
    )
    async with running_summary_app(tmp_path / "KnowRealm", summary_model=fake) as (app, client):
        record_id = await create_pending_record(app, client)
        await configure_provider(client)
        await client.post("/api/settings/external-processing-consents/llm")
        accepted = await client.post(f"/api/records/{record_id}/summary-jobs")
        await wait_for_record_status(client, record_id, "FAILED")
        summary = await client.get(f"/api/records/{record_id}/summary")
        async with app.state.session_factory() as session:
            summary_count = await session.scalar(text("SELECT count(*) FROM ai_summaries"))
            error_code = await session.scalar(
                text("SELECT error_code FROM llm_call_logs WHERE graph_name='summary'")
            )

    assert accepted.status_code == 202
    assert len(fake.prompts) == 1
    assert summary.json()["action_required"] == "RETRY"
    assert summary_count == 0
    assert error_code == "INVALID_STRUCTURED_OUTPUT"


@pytest.mark.parametrize(
    "invalid_output",
    [
        {
            "topic": "   ",
            "abstract": "正" * 500,
            "sections": [{"heading": "章节", "points": ["分点"]}],
        },
        {
            "topic": "主题",
            "abstract": "正" * 500,
            "sections": [{"heading": "章节", "points": ["分点"]}],
            "unexpected": "field",
        },
    ],
)
def test_summary_schema_rejects_blank_and_extra_fields(
    invalid_output: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        SummaryContent.model_validate(invalid_output)


@pytest.mark.anyio
async def test_stale_transcript_cancels_late_result_without_body(tmp_path: Path) -> None:
    fake = FakeSummaryModel()
    fake.release.clear()
    async with running_summary_app(tmp_path / "KnowRealm", summary_model=fake) as (app, client):
        record_id = await create_pending_record(app, client)
        await configure_provider(client)
        await client.post("/api/settings/external-processing-consents/llm")
        accepted = await client.post(f"/api/records/{record_id}/summary-jobs")
        await asyncio.wait_for(fake.started.wait(), timeout=2)
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE transcripts SET source_version=2, content='更新后的正文' "
                    "WHERE record_id=:record_id"
                ),
                {"record_id": record_id},
            )
        fake.release.set()

        for _ in range(200):
            jobs = (await client.get(f"/api/records/{record_id}/jobs")).json()["jobs"]
            if jobs[0]["status"] == "CANCELLED":
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("迟到 Summary Job 未取消")

        async with app.state.session_factory() as session:
            summary_count = await session.scalar(text("SELECT count(*) FROM ai_summaries"))
            result_json = await session.scalar(
                text("SELECT result_json FROM processing_jobs WHERE id=:id"),
                {"id": accepted.json()["job_id"]},
            )

    assert summary_count == 0
    assert json.loads(cast(str, result_json)) == {"reason": "STALE_TRANSCRIPT"}


@pytest.mark.anyio
async def test_normal_document_source_auto_enqueues_and_checkpoint_survives_restart(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    fake = FakeSummaryModel()
    async with running_summary_app(data_dir, summary_model=fake) as (app, client):
        await configure_provider(client)
        await client.post("/api/settings/external-processing-consents/llm")
        course = await client.post(
            "/api/courses",
            json={
                "name": "数据库",
                "learning_context": "SCHOOL",
                "education_stage": "UNDERGRADUATE",
            },
        )
        accepted = await client.post(
            "/api/document-imports",
            data={"course_id": course.json()["id"]},
            files={"file": ("mvcc.txt", "MVCC 通过版本链提供一致性读。", "text/plain")},
        )
        record_id = accepted.json()["record_id"]
        await wait_for_record_status(client, record_id, "SUMMARY_READY")
        thread_id = f"summary-{record_id}-source-1"
        first_state = await app.state.summary_graph.aget_state(
            {"configurable": {"thread_id": thread_id}}
        )

    async with running_summary_app(data_dir, summary_model=fake) as (app, client):
        restored_state = await app.state.summary_graph.aget_state(
            {"configurable": {"thread_id": thread_id}}
        )
        summary = await client.get(f"/api/records/{record_id}/summary")

    assert accepted.status_code == 202
    assert len(fake.prompts) == 1
    assert first_state.values["record_id"] == record_id
    assert restored_state.values["record_id"] == record_id
    assert summary.json()["summary"]["topic"] == "操作系统中的进程调度"
