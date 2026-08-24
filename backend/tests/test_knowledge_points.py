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
from app.schemas.knowledge_point import KnowledgePointBatch

TOKEN = "test-launch-token"


def test_candidate_schema_rejects_instead_of_trimming() -> None:
    with pytest.raises(ValueError):
        KnowledgePointBatch.model_validate(
            {
                "items": [
                    {
                        "name": " 进程调度 ",
                        "detail": "操作系统选择下一个进程。",
                        "tags": ["调度"],
                        "importance": 5,
                    }
                ]
            }
        )


class FakeKnowledgePointModel:
    def __init__(
        self,
        output: object | None = None,
        sequence: list[object] | None = None,
    ) -> None:
        self.output = (
            output
            if output is not None
            else {
                "items": [
                    {
                        "name": "进程调度",
                        "detail": "操作系统按照调度策略选择下一个占用处理器的就绪进程。",
                        "tags": ["操作系统", "调度"],
                        "importance": 5,
                    },
                    {
                        "name": "时间片",
                        "detail": "时间片限制单个进程连续占用处理器的时长。",
                        "tags": ["调度"],
                        "importance": 4,
                    },
                ]
            }
        )
        self.sequence = list(sequence) if sequence is not None else None
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
    ) -> StructuredModelResult:
        assert base_url == "https://example.com/v1"
        assert api_key == "sk-test"
        assert model == "qwen-plus"
        self.prompts.append(prompt)
        self.started.set()
        await self.release.wait()
        output = self.sequence.pop(0) if self.sequence is not None else self.output
        return StructuredModelResult(output=output, token_usage={"total_tokens": 21})


@asynccontextmanager
async def running_knowledge_point_app(
    data_dir: Path,
    model: FakeKnowledgePointModel,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(
        data_dir=data_dir,
        launch_token=TOKEN,
        knowledge_point_model=model,
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client


async def create_completed_record(app: FastAPI, client: httpx.AsyncClient) -> tuple[str, str]:
    course = await client.post(
        "/api/courses",
        json={
            "name": "操作系统",
            "learning_context": "SCHOOL",
            "education_stage": "UNDERGRADUATE",
        },
    )
    course_id = cast(str, course.json()["id"])
    record_id = "11111111-1111-4111-8111-111111111111"
    summary_id = "33333333-3333-4333-8333-333333333333"
    now = "2026-08-24T12:00:00.000000Z"
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
        await session.execute(
            text(
                "INSERT INTO ai_summaries "
                "(id, record_id, version_no, transcript_source_version, topic, abstract, "
                "summary_json, status, model, prompt_version, token_usage_json, latency_ms, "
                "user_feedback, confirmed_at, created_at, updated_at, deleted_at) "
                "VALUES (:id, :record_id, 1, 1, '进程调度', :abstract, :summary_json, "
                "'CONFIRMED', 'qwen-plus', 'summary-v1', '{}', 10, NULL, :now, :now, :now, NULL)"
            ),
            {
                "id": summary_id,
                "record_id": record_id,
                "abstract": "总结介绍了操作系统如何通过调度策略分配处理器时间。" * 20,
                "summary_json": json.dumps(
                    {"sections": [{"heading": "调度", "points": ["调度器选择就绪进程。"]}]},
                    ensure_ascii=False,
                ),
                "now": now,
            },
        )
    return record_id, summary_id


async def configure_llm(client: httpx.AsyncClient) -> None:
    response = await client.put(
        "/api/settings/providers/llm",
        json={
            "base_url": "https://example.com/v1",
            "api_key": "sk-test",
            "model": "qwen-plus",
        },
    )
    assert response.status_code == 200


async def grant_llm_consent(client: httpx.AsyncClient) -> None:
    consent = await client.post("/api/settings/external-processing-consents/llm")
    assert consent.status_code == 200


async def wait_for_candidates(
    client: httpx.AsyncClient,
    record_id: str,
) -> dict[str, object]:
    for _ in range(200):
        payload = cast(
            dict[str, object],
            (await client.get(f"/api/records/{record_id}/knowledge-points")).json(),
        )
        if payload.get("action_required") == "CONFIRM":
            return payload
        await asyncio.sleep(0.02)
    pytest.fail("知识点候选未生成")


async def wait_for_action(
    client: httpx.AsyncClient,
    record_id: str,
    action: str,
) -> dict[str, object]:
    for _ in range(200):
        payload = cast(
            dict[str, object],
            (await client.get(f"/api/records/{record_id}/knowledge-points")).json(),
        )
        if payload.get("action_required") == action:
            return payload
        await asyncio.sleep(0.02)
    pytest.fail(f"知识点状态未进入 {action}")


@pytest.mark.anyio
async def test_knowledge_point_migration_creates_table_and_active_job_guard(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "knowrealm.db"

    await run_migrations(db_path)

    async with aiosqlite.connect(db_path) as connection:
        version = await (await connection.execute("PRAGMA user_version")).fetchone()
        columns = {
            cast(str, row[1])
            for row in await (
                await connection.execute("PRAGMA table_info(knowledge_points)")
            ).fetchall()
        }
        indexes = {
            cast(str, row[1])
            for row in await (
                await connection.execute("PRAGMA index_list(processing_jobs)")
            ).fetchall()
        }

    assert version == (9,)
    assert {
        "id",
        "record_id",
        "batch_id",
        "name",
        "detail",
        "tags",
        "importance",
        "generated_from_summary_id",
        "generation_status",
        "source_anchor_id",
        "created_at",
        "updated_at",
        "deleted_at",
    } == columns
    assert "idx_processing_jobs_one_active_knowledge_extraction" in indexes


@pytest.mark.anyio
async def test_generate_candidates_persists_draft_batch_and_provenance(tmp_path: Path) -> None:
    model = FakeKnowledgePointModel()
    async with running_knowledge_point_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)

        before = await client.get(f"/api/records/{record_id}/knowledge-points")
        accepted = await client.post(f"/api/records/{record_id}/knowledge-point-jobs")
        assert accepted.status_code == 202, accepted.text
        candidates = await wait_for_candidates(client, record_id)

        async with app.state.session_factory() as session:
            job_row = (
                await session.execute(
                    text("SELECT status, result_json FROM processing_jobs WHERE id=:job_id"),
                    {"job_id": accepted.json()["job_id"]},
                )
            ).one()
            log_row = (
                await session.execute(
                    text(
                        "SELECT graph_name, graph_node, prompt_version, error_code "
                        "FROM llm_call_logs WHERE graph_name='knowledge-points'"
                    )
                )
            ).one()

    assert before.json()["action_required"] == "GENERATE"
    assert candidates["input_mode"] == "FULL_TRANSCRIPT"
    assert [item["name"] for item in cast(list[dict[str, object]], candidates["items"])] == [
        "进程调度",
        "时间片",
    ]
    assert all(
        item["generation_status"] == "DRAFT"
        and item["batch_id"] == accepted.json()["job_id"]
        and item["generated_from_summary_id"] == summary_id
        for item in cast(list[dict[str, object]], candidates["items"])
    )
    assert len(model.prompts) == 1
    assert "学习场景：SCHOOL" in model.prompts[0]
    assert "进程调度用于决定" in model.prompts[0]
    result = json.loads(cast(str, job_row.result_json))
    assert result == {
        "model": "qwen-plus",
        "prompt_version": "kp_v1",
        "candidate_count": 2,
        "input_mode": "FULL_TRANSCRIPT",
    }
    assert job_row.status == "SUCCEEDED"
    assert tuple(log_row) == ("knowledge-points", "generate", "kp_v1", None)


@pytest.mark.anyio
async def test_generate_rejects_missing_prerequisites_without_creating_jobs(
    tmp_path: Path,
) -> None:
    model = FakeKnowledgePointModel()
    async with running_knowledge_point_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)

        missing_provider = await client.post(f"/api/records/{record_id}/knowledge-point-jobs")
        await configure_llm(client)
        missing_consent = await client.post(f"/api/records/{record_id}/knowledge-point-jobs")
        await grant_llm_consent(client)
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE ai_summaries SET status='SUPERSEDED' WHERE record_id=:record_id"),
                {"record_id": record_id},
            )
        missing_summary = await client.post(f"/api/records/{record_id}/knowledge-point-jobs")
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE ai_summaries SET status='CONFIRMED' WHERE record_id=:record_id"),
                {"record_id": record_id},
            )
            await session.execute(
                text(
                    "UPDATE courses SET status='ARCHIVED' "
                    "WHERE id=(SELECT course_id FROM records WHERE id=:record_id)"
                ),
                {"record_id": record_id},
            )
        archived_course = await client.post(f"/api/records/{record_id}/knowledge-point-jobs")
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE courses SET status='ACTIVE' "
                    "WHERE id=(SELECT course_id FROM records WHERE id=:record_id)"
                ),
                {"record_id": record_id},
            )
        accepted = await client.post(f"/api/records/{record_id}/knowledge-point-jobs")
        assert accepted.status_code == 202
        await wait_for_candidates(client, record_id)
        existing_draft = await client.post(f"/api/records/{record_id}/knowledge-point-jobs")
        async with app.state.session_factory() as session:
            job_count = await session.scalar(
                text("SELECT count(*) FROM processing_jobs WHERE job_type='KNOWLEDGE_EXTRACTION'")
            )

    assert [
        missing_provider.status_code,
        missing_consent.status_code,
        missing_summary.status_code,
        archived_course.status_code,
        existing_draft.status_code,
    ] == [409, 409, 409, 409, 409]
    assert job_count == 1
    assert len(model.prompts) == 1


@pytest.mark.anyio
async def test_invalid_output_fails_once_and_manual_retry_reuses_job(tmp_path: Path) -> None:
    invalid = cast(
        object,
        {
            "items": [
                {
                    "name": "错误候选",
                    "detail": "importance 不是整数",
                    "tags": [],
                    "importance": 4.5,
                }
            ]
        },
    )
    model = FakeKnowledgePointModel(sequence=[invalid, FakeKnowledgePointModel().output])
    async with running_knowledge_point_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)

        first = await client.post(f"/api/records/{record_id}/knowledge-point-jobs")
        failed = await wait_for_action(client, record_id, "RETRY")
        retry = await client.post(f"/api/records/{record_id}/knowledge-point-jobs")
        candidates = await wait_for_candidates(client, record_id)

        async with app.state.session_factory() as session:
            job_rows = (
                await session.execute(
                    text(
                        "SELECT id, status, attempts FROM processing_jobs "
                        "WHERE job_type='KNOWLEDGE_EXTRACTION'"
                    )
                )
            ).all()
            log_errors = list(
                (
                    await session.scalars(
                        text(
                            "SELECT error_code FROM llm_call_logs "
                            "WHERE graph_name='knowledge-points' ORDER BY created_at"
                        )
                    )
                ).all()
            )

    assert failed["items"] == []
    assert first.status_code == 202
    assert retry.status_code == 202
    assert first.json()["job_id"] == retry.json()["job_id"]
    assert candidates["action_required"] == "CONFIRM"
    assert [tuple(row) for row in job_rows] == [(first.json()["job_id"], "SUCCEEDED", 1)]
    assert log_errors == ["LLM_OUTPUT_INVALID", None]
    assert len(model.prompts) == 2


@pytest.mark.anyio
async def test_long_transcript_uses_confirmed_summary_only(tmp_path: Path) -> None:
    model = FakeKnowledgePointModel()
    marker = "绝不能进入提示词的末尾标记"
    async with running_knowledge_point_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE transcripts SET content=:content WHERE record_id=:record_id"),
                {"record_id": record_id, "content": "知" * 30_001 + marker},
            )
        await configure_llm(client)
        await grant_llm_consent(client)

        accepted = await client.post(f"/api/records/{record_id}/knowledge-point-jobs")
        candidates = await wait_for_candidates(client, record_id)

    assert accepted.status_code == 202
    assert candidates["input_mode"] == "SUMMARY_ONLY"
    assert "已确认总结" in model.prompts[0]
    assert "Transcript：" not in model.prompts[0]
    assert marker not in model.prompts[0]


@pytest.mark.anyio
async def test_active_job_guard_rejects_duplicate_submit(tmp_path: Path) -> None:
    model = FakeKnowledgePointModel()
    model.release.clear()
    async with running_knowledge_point_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)

        first = await client.post(f"/api/records/{record_id}/knowledge-point-jobs")
        await asyncio.wait_for(model.started.wait(), timeout=2)
        duplicate = await client.post(f"/api/records/{record_id}/knowledge-point-jobs")
        async with app.state.session_factory() as session:
            active_count = await session.scalar(
                text(
                    "SELECT count(*) FROM processing_jobs "
                    "WHERE job_type='KNOWLEDGE_EXTRACTION' "
                    "AND status IN ('PENDING', 'RUNNING')"
                )
            )
        model.release.set()
        await wait_for_candidates(client, record_id)

    assert first.status_code == 202
    assert duplicate.status_code == 409
    assert active_count == 1


@pytest.mark.anyio
async def test_soft_delete_during_generation_discards_candidates(tmp_path: Path) -> None:
    model = FakeKnowledgePointModel()
    model.release.clear()
    async with running_knowledge_point_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)

        accepted = await client.post(f"/api/records/{record_id}/knowledge-point-jobs")
        await asyncio.wait_for(model.started.wait(), timeout=2)
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE records SET deleted_at=:deleted_at WHERE id=:record_id"),
                {
                    "record_id": record_id,
                    "deleted_at": "2026-08-24T10:00:00.000000Z",
                },
            )
        model.release.set()

        status = "RUNNING"
        candidate_count = -1
        for _attempt in range(40):
            async with app.state.session_factory() as session:
                status = cast(
                    str,
                    await session.scalar(
                        text("SELECT status FROM processing_jobs WHERE id=:job_id"),
                        {"job_id": accepted.json()["job_id"]},
                    ),
                )
                candidate_count = cast(
                    int,
                    await session.scalar(
                        text("SELECT count(*) FROM knowledge_points WHERE record_id=:record_id"),
                        {"record_id": record_id},
                    ),
                )
            if status == "CANCELLED":
                break
            await asyncio.sleep(0.05)

    assert accepted.status_code == 202
    assert status == "CANCELLED"
    assert candidate_count == 0
