import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import aiosqlite
import httpx
import openai
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.db.migrations import MIGRATIONS_DIR, run_migrations
from app.main import create_app
from app.modules.llm.service import OpenAiCompatibleSummaryModel, SummaryModel, SummaryModelResult
from app.modules.summary.schemas import SummaryContent, SummarySection
from app.shared.prompts import CONTENT_LANGUAGE_INSTRUCTION

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


def adjusted_summary() -> SummaryContent:
    return SummaryContent(
        topic="进程调度（修订版）",
        abstract="这是根据用户反馈修订后的结构化总结摘要。" * 30,
        sections=[
            SummarySection(
                heading="调度策略",
                points=["反馈驱动的新版本按既定策略选择下一个进程。"],
            )
        ],
    )


class FakeSummaryModel:
    def __init__(
        self,
        output: object | None = None,
        sequence: list[object] | None = None,
    ) -> None:
        self.sequence = list(sequence) if sequence is not None else None
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
        if self.sequence is not None:
            return SummaryModelResult(output=self.sequence.pop(0), token_usage={"total_tokens": 42})
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


async def wait_for_summary_version(
    client: httpx.AsyncClient,
    record_id: str,
    version_no: int,
) -> dict[str, object]:
    for _ in range(200):
        raw: object = (await client.get(f"/api/records/{record_id}/summary")).json()
        payload = cast(dict[str, object], raw)
        summary = payload.get("summary")
        current = cast(dict[str, object], summary) if isinstance(summary, dict) else {}
        if current.get("version_no") == version_no:
            return current
        await asyncio.sleep(0.02)
    pytest.fail(f"Summary 未进入版本 {version_no}")


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

    assert version == (18,)
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
    assert CONTENT_LANGUAGE_INSTRUCTION in fake.prompts[0]
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


async def prepare_ready_summary(app: FastAPI, client: httpx.AsyncClient) -> str:
    record_id = await create_pending_record(app, client)
    await configure_provider(client)
    await client.post("/api/settings/external-processing-consents/llm")
    accepted = await client.post(f"/api/records/{record_id}/summary-jobs")
    assert accepted.status_code == 202
    await wait_for_record_status(client, record_id, "SUMMARY_READY")
    return record_id


@pytest.mark.anyio
async def test_adjust_validates_input_then_supersedes_previous_only_on_success(
    tmp_path: Path,
) -> None:
    fake = FakeSummaryModel(
        sequence=[valid_summary().model_dump(), adjusted_summary().model_dump()]
    )
    async with running_summary_app(tmp_path / "KnowRealm", summary_model=fake) as (app, client):
        record_id = await prepare_ready_summary(app, client)
        first_id = (await client.get(f"/api/records/{record_id}/summary")).json()["summary"]["id"]
        blank = await client.post(
            f"/api/records/{record_id}/summary-adjustments",
            json={"summary_id": first_id, "feedback": "   "},
        )
        too_long = await client.post(
            f"/api/records/{record_id}/summary-adjustments",
            json={"summary_id": first_id, "feedback": "长" * 1001},
        )
        unknown = await client.post(
            f"/api/records/{record_id}/summary-adjustments",
            json={"summary_id": "99999999-9999-4999-8999-999999999999", "feedback": "更简洁"},
        )
        accepted = await client.post(
            f"/api/records/{record_id}/summary-adjustments",
            json={"summary_id": first_id, "feedback": "更简洁一些，侧重调度策略"},
        )
        duplicate = await client.post(
            f"/api/records/{record_id}/summary-adjustments",
            json={"summary_id": first_id, "feedback": "再次调整"},
        )
        second = await wait_for_summary_version(client, record_id, 2)
        stale_adjust = await client.post(
            f"/api/records/{record_id}/summary-adjustments",
            json={"summary_id": first_id, "feedback": "对旧版本调整"},
        )
        versions = await client.get(f"/api/records/{record_id}/summaries")
        detail = await client.get(f"/api/records/{record_id}/summaries/{first_id}")
        missing = await client.get(
            f"/api/records/{record_id}/summaries/99999999-9999-4999-8999-999999999999"
        )
        async with app.state.session_factory() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT version_no, status, user_feedback, prompt_version "
                        "FROM ai_summaries ORDER BY version_no"
                    )
                )
            ).all()
            adjust_log = (
                await session.execute(
                    text(
                        "SELECT prompt_version, error_code FROM llm_call_logs "
                        "WHERE graph_node='generate' ORDER BY created_at"
                    )
                )
            ).all()
            job_count = await session.scalar(
                text("SELECT count(*) FROM processing_jobs WHERE job_type='SUMMARY'")
            )

    assert blank.status_code == 422
    assert too_long.status_code == 422
    assert unknown.status_code == 409
    assert accepted.status_code == 202
    assert duplicate.status_code == 409
    assert stale_adjust.status_code == 409
    assert second["topic"] == "进程调度（修订版）"
    assert second["user_feedback"] == "更简洁一些，侧重调度策略"
    assert [tuple(row) for row in rows] == [
        (1, "SUPERSEDED", None, "summary-v1"),
        (2, "GENERATED", "更简洁一些，侧重调度策略", "summary-adjust-v1"),
    ]
    assert len(fake.prompts) == 2
    assert "更简洁一些，侧重调度策略" in fake.prompts[1]
    assert "操作系统中的进程调度" in fake.prompts[1]
    assert "进程调度用于决定就绪进程获得处理器的顺序。" in fake.prompts[1]
    assert [tuple(row) for row in adjust_log] == [
        ("summary-v1", None),
        ("summary-adjust-v1", None),
    ]
    assert job_count == 2
    assert [version["version_no"] for version in versions.json()] == [2, 1]
    assert detail.json()["status"] == "SUPERSEDED"
    assert detail.json()["version_no"] == 1
    assert missing.status_code == 404


@pytest.mark.anyio
async def test_adjust_failure_keeps_previous_confirmable_and_reuses_failed_job(
    tmp_path: Path,
) -> None:
    fake = FakeSummaryModel(
        sequence=[
            valid_summary().model_dump(),
            {"topic": "", "abstract": "过短", "sections": []},
            adjusted_summary().model_dump(),
        ]
    )
    async with running_summary_app(tmp_path / "KnowRealm", summary_model=fake) as (app, client):
        record_id = await prepare_ready_summary(app, client)
        first_id = (await client.get(f"/api/records/{record_id}/summary")).json()["summary"]["id"]
        failed_adjust = await client.post(
            f"/api/records/{record_id}/summary-adjustments",
            json={"summary_id": first_id, "feedback": "第一次反馈"},
        )
        adjust_job_id = failed_adjust.json()["job_id"]
        for _ in range(200):
            jobs = (await client.get(f"/api/records/{record_id}/jobs")).json()["jobs"]
            adjust_job = next((job for job in jobs if job["id"] == adjust_job_id), None)
            if adjust_job is not None and adjust_job["status"] == "FAILED":
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("调整任务未进入 FAILED")
        after_failure = await client.get(f"/api/records/{record_id}/summary")
        record_after_failure = await client.get(f"/api/records/{record_id}")
        retried_adjust = await client.post(
            f"/api/records/{record_id}/summary-adjustments",
            json={"summary_id": first_id, "feedback": "换一条反馈重试"},
        )
        second = await wait_for_summary_version(client, record_id, 2)
        async with app.state.session_factory() as session:
            job_count = await session.scalar(
                text("SELECT count(*) FROM processing_jobs WHERE job_type='SUMMARY'")
            )
            reused_feedback = await session.scalar(
                text("SELECT input_json FROM processing_jobs WHERE id=:id"),
                {"id": retried_adjust.json()["job_id"]},
            )
            stale_confirm = await client.post(
                f"/api/records/{record_id}/summary-confirmations",
                json={"summary_id": first_id},
            )
            confirmed = await client.post(
                f"/api/records/{record_id}/summary-confirmations",
                json={"summary_id": second["id"]},
            )

    assert failed_adjust.status_code == 202
    assert record_after_failure.json()["status"] == "SUMMARY_READY"
    assert after_failure.json()["summary"]["id"] == first_id
    assert after_failure.json()["summary"]["status"] == "GENERATED"
    assert retried_adjust.status_code == 202
    assert retried_adjust.json()["job_id"] == failed_adjust.json()["job_id"]
    reused_input = json.loads(cast(str, reused_feedback))
    assert reused_input["feedback"] == "换一条反馈重试"
    assert job_count == 2
    assert stale_confirm.status_code == 409
    assert confirmed.status_code == 200
    assert confirmed.json()["record_status"] == "COMPLETED"


@pytest.mark.anyio
async def test_confirm_is_idempotent_and_writes_single_learning_event(tmp_path: Path) -> None:
    fake = FakeSummaryModel()
    async with running_summary_app(tmp_path / "KnowRealm", summary_model=fake) as (app, client):
        record_id = await prepare_ready_summary(app, client)
        summary_id = (await client.get(f"/api/records/{record_id}/summary")).json()["summary"]["id"]
        missing = await client.post(
            f"/api/records/{record_id}/summary-confirmations",
            json={"summary_id": "99999999-9999-4999-8999-999999999999"},
        )
        confirmed = await client.post(
            f"/api/records/{record_id}/summary-confirmations",
            json={"summary_id": summary_id},
        )
        repeated = await client.post(
            f"/api/records/{record_id}/summary-confirmations",
            json={"summary_id": summary_id},
        )
        record = await client.get(f"/api/records/{record_id}")
        summary = await client.get(f"/api/records/{record_id}/summary")
        async with app.state.session_factory() as session:
            events = (await session.execute(text("SELECT * FROM learning_events"))).all()
            summary_row = (
                await session.execute(
                    text("SELECT status, confirmed_at FROM ai_summaries WHERE id=:id"),
                    {"id": summary_id},
                )
            ).one()
            course_id = await session.scalar(
                text("SELECT course_id FROM records WHERE id=:id"), {"id": record_id}
            )

    assert missing.status_code == 404
    assert confirmed.status_code == 200
    assert confirmed.json()["record_status"] == "COMPLETED"
    assert confirmed.json()["summary"]["status"] == "CONFIRMED"
    assert repeated.status_code == 200
    assert repeated.json() == confirmed.json()
    assert record.json()["status"] == "COMPLETED"
    assert record.json()["summary_confirmed_at"] is not None
    assert summary.json()["summary"]["status"] == "CONFIRMED"
    assert summary.json()["action_required"] == "NONE"
    assert len(events) == 1
    event = events[0]._mapping
    assert event["event_type"] == "SUMMARY_CONFIRMED"
    assert event["source_type"] == "AI_SUMMARY"
    assert event["source_id"] == summary_id
    assert event["idempotency_key"] == f"summary-confirmed:{summary_id}"
    assert event["record_id"] == record_id
    assert event["course_id"] == course_id
    assert summary_row[0] == "CONFIRMED"
    assert summary_row[1] is not None


@pytest.mark.anyio
async def test_adjust_resume_and_confirm_survive_full_app_restart(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with running_summary_app(data_dir, summary_model=FakeSummaryModel()) as (app, client):
        record_id = await prepare_ready_summary(app, client)
        first_id = (await client.get(f"/api/records/{record_id}/summary")).json()["summary"]["id"]
        thread_id = f"summary-{record_id}-source-1"

    async with running_summary_app(
        data_dir, summary_model=FakeSummaryModel(output=adjusted_summary().model_dump())
    ) as (app, client):
        accepted = await client.post(
            f"/api/records/{record_id}/summary-adjustments",
            json={"summary_id": first_id, "feedback": "更简洁"},
        )
        second = await wait_for_summary_version(client, record_id, 2)
        snapshot = await app.state.summary_graph.aget_state(
            {"configurable": {"thread_id": thread_id}}
        )

    async with running_summary_app(
        data_dir, summary_model=FakeSummaryModel(output=adjusted_summary().model_dump())
    ) as (_app, client):
        confirmed = await client.post(
            f"/api/records/{record_id}/summary-confirmations",
            json={"summary_id": second["id"]},
        )
        summary = await client.get(f"/api/records/{record_id}/summary")

    assert accepted.status_code == 202
    assert snapshot.values["summary"]["topic"] == "进程调度（修订版）"
    assert confirmed.status_code == 200
    assert confirmed.json()["record_status"] == "COMPLETED"
    assert summary.json()["summary"]["version_no"] == 2
    assert summary.json()["summary"]["status"] == "CONFIRMED"


@pytest.mark.anyio
async def test_worker_restart_recovery_keeps_previous_version_for_interrupted_adjust(
    tmp_path: Path,
) -> None:
    fake = FakeSummaryModel(output=adjusted_summary().model_dump())
    async with running_summary_app(tmp_path / "KnowRealm", summary_model=fake) as (app, client):
        record_id = await prepare_ready_summary(app, client)
        first_id = (await client.get(f"/api/records/{record_id}/summary")).json()["summary"]["id"]
        accepted = await client.post(
            f"/api/records/{record_id}/summary-adjustments",
            json={"summary_id": first_id, "feedback": "更简洁"},
        )
        job_id = accepted.json()["job_id"]
        # 模拟调整已被认领后应用崩溃：任务停在 RUNNING、Record 停在 SUMMARY_PROCESSING
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE processing_jobs SET status='RUNNING' WHERE id=:id"),
                {"id": job_id},
            )
            await session.execute(
                text("UPDATE records SET status='SUMMARY_PROCESSING' WHERE id=:id"),
                {"id": record_id},
            )

    async with running_summary_app(tmp_path / "KnowRealm", summary_model=fake) as (_app, client):
        await wait_for_record_status(client, record_id, "SUMMARY_READY")
        summary = await client.get(f"/api/records/{record_id}/summary")
        confirmed = await client.post(
            f"/api/records/{record_id}/summary-confirmations",
            json={"summary_id": first_id},
        )

    assert summary.json()["summary"]["id"] == first_id
    assert summary.json()["summary"]["status"] == "GENERATED"
    assert confirmed.status_code == 200
    assert confirmed.json()["record_status"] == "COMPLETED"


@pytest.mark.anyio
async def test_json_schema_rejection_falls_back_to_json_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: dict[str, str] = {}

    class SchemaRunnable:
        async def ainvoke(self, prompt: str) -> object:
            received["json_schema"] = prompt
            response = httpx.Response(
                400,
                request=httpx.Request("POST", "https://api.deepseek.com/chat/completions"),
                json={"error": {"message": "This response_format type is unavailable now"}},
            )
            raise openai.BadRequestError(
                "400 Bad Request",
                response=response,  # pyright: ignore[reportArgumentType]
                body=None,
            )

    class RawMessage:
        usage_metadata = {"total_tokens": 7}

    class JsonModeRunnable:
        async def ainvoke(self, prompt: str) -> object:
            received["json_mode"] = prompt
            return {
                "raw": RawMessage(),
                "parsed": valid_summary().model_dump(),
                "parsing_error": None,
            }

    class StubChatOpenAI:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def with_structured_output(
            self,
            _schema: object,
            *,
            method: str,
            include_raw: bool,
            **kwargs: object,
        ) -> object:
            assert include_raw is True
            if method == "json_schema":
                assert kwargs.get("strict") is True
                return SchemaRunnable()
            assert method == "json_mode"
            assert kwargs.get("max_tokens") == 8192
            return JsonModeRunnable()

    monkeypatch.setattr("app.modules.llm.service.ChatOpenAI", StubChatOpenAI)
    result = await OpenAiCompatibleSummaryModel().generate(
        base_url="https://api.deepseek.com",
        api_key="sk-test",
        model="deepseek-v4-flash",
        prompt="总结指令",
    )

    content = SummaryContent.model_validate(result.output)
    assert content.topic == "操作系统中的进程调度"
    assert received["json_schema"] == "总结指令"
    assert "JSON Schema" in received["json_mode"]
    assert received["json_mode"] != "总结指令"
    assert result.token_usage == {"total_tokens": 7}


@pytest.mark.anyio
async def test_provider_auth_error_does_not_fall_back(monkeypatch: pytest.MonkeyPatch) -> None:
    class AuthErrorRunnable:
        async def ainvoke(self, _prompt: str) -> object:
            response = httpx.Response(
                401,
                request=httpx.Request("POST", "https://api.deepseek.com/chat/completions"),
                json={"error": {"message": "Authentication Fails"}},
            )
            raise openai.AuthenticationError(
                "401",
                response=response,  # pyright: ignore[reportArgumentType]
                body=None,
            )

    class StubChatOpenAI:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def with_structured_output(
            self,
            _schema: object,
            *,
            method: str,
            include_raw: bool,
            **_kwargs: object,
        ) -> object:
            assert method == "json_schema"
            assert include_raw is True
            return AuthErrorRunnable()

    monkeypatch.setattr("app.modules.llm.service.ChatOpenAI", StubChatOpenAI)
    with pytest.raises(Exception, match="401"):
        await OpenAiCompatibleSummaryModel().generate(
            base_url="https://api.deepseek.com",
            api_key="sk-wrong",
            model="deepseek-v4-flash",
            prompt="总结指令",
        )
