import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast
from uuid import uuid4

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.db.migrations import run_migrations
from app.main import create_app
from app.modules.knowledge_point.schemas import KnowledgePointBatch
from app.modules.llm.service import StructuredModelResult, SummaryModel
from app.modules.record.models import LearningEvent
from app.modules.summary.schemas import SummaryContent, SummarySection
from app.shared.prompts import CONTENT_LANGUAGE_INSTRUCTION

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
    *,
    summary_model: SummaryModel | None = None,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(
        data_dir=data_dir,
        launch_token=TOKEN,
        knowledge_point_model=model,
        summary_model=summary_model,
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


def draft_batch_id(payload: dict[str, object]) -> str:
    items = cast(list[dict[str, object]], payload["items"])
    batch_ids = {
        cast(str, item["batch_id"]) for item in items if item["generation_status"] == "DRAFT"
    }
    assert len(batch_ids) == 1
    return batch_ids.pop()


async def confirmed_event_count(
    session_factory: async_sessionmaker[AsyncSession],
    record_id: str,
) -> int:
    async with session_factory() as session:
        return cast(
            int,
            await session.scalar(
                text(
                    "SELECT count(*) FROM learning_events "
                    "WHERE event_type='KNOWLEDGE_CONFIRMED' AND record_id=:record_id"
                ),
                {"record_id": record_id},
            ),
        )


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

    assert version == (22,)
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
    assert CONTENT_LANGUAGE_INSTRUCTION in model.prompts[0]
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


async def generate_draft_batch(
    client: httpx.AsyncClient,
    record_id: str,
) -> tuple[str, dict[str, object]]:
    accepted = await client.post(f"/api/records/{record_id}/knowledge-point-jobs")
    assert accepted.status_code == 202, accepted.text
    payload = await wait_for_candidates(client, record_id)
    return draft_batch_id(payload), payload


async def add_manual_item(
    client: httpx.AsyncClient,
    record_id: str,
    name: str = "手工补充：调度队列",
    importance: int = 2,
) -> httpx.Response:
    return await client.post(
        f"/api/records/{record_id}/knowledge-points",
        json={
            "name": name,
            "detail": "就绪队列与阻塞队列承担不同的进程状态。",
            "tags": ["手工"],
            "importance": importance,
        },
    )


@pytest.mark.anyio
async def test_manual_add_creates_independent_active_row_without_events(
    tmp_path: Path,
) -> None:
    model = FakeKnowledgePointModel()
    async with running_knowledge_point_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)

        created = await add_manual_item(client, record_id)
        reread = await client.get(f"/api/records/{record_id}/knowledge-points")

        async with app.state.session_factory() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT batch_id, generated_from_summary_id, generation_status "
                        "FROM knowledge_points WHERE record_id=:record_id"
                    ),
                    {"record_id": record_id},
                )
            ).one()
            event_count = await confirmed_event_count(app.state.session_factory, record_id)

    assert created.status_code == 201, created.text
    body = cast(dict[str, object], created.json())
    assert body["generation_status"] == "ACTIVE"
    assert body["batch_id"] is None
    assert body["generated_from_summary_id"] is None
    assert row == (None, None, "ACTIVE")
    items = cast(list[dict[str, object]], reread.json()["items"])
    assert [item["name"] for item in items] == ["手工补充：调度队列"]
    assert reread.json()["action_required"] == "GENERATE"
    assert event_count == 0


@pytest.mark.anyio
async def test_edit_and_delete_apply_immediately_on_draft_rows(tmp_path: Path) -> None:
    model = FakeKnowledgePointModel()
    async with running_knowledge_point_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)
        _batch_id, candidates = await generate_draft_batch(client, record_id)
        items = cast(list[dict[str, object]], candidates["items"])
        first_id = cast(str, items[0]["id"])
        second_id = cast(str, items[1]["id"])

        edited = await client.patch(
            f"/api/records/{record_id}/knowledge-points/{first_id}",
            json={
                "name": "调度器",
                "detail": "调度器决定处理器时间的分配对象。",
                "tags": ["操作系统"],
                "importance": 3,
            },
        )
        deleted = await client.delete(f"/api/records/{record_id}/knowledge-points/{second_id}")
        missing = await client.delete(f"/api/records/{record_id}/knowledge-points/{second_id}")
        after = await client.get(f"/api/records/{record_id}/knowledge-points")

        async with app.state.session_factory() as session:
            deleted_row = (
                await session.execute(
                    text("SELECT deleted_at IS NOT NULL FROM knowledge_points WHERE id=:id"),
                    {"id": second_id},
                )
            ).scalar_one()

    assert edited.status_code == 200, edited.text
    edited_body = cast(dict[str, object], edited.json())
    assert edited_body["name"] == "调度器"
    assert edited_body["tags"] == ["操作系统"]
    assert edited_body["importance"] == 3
    assert edited_body["generation_status"] == "DRAFT"
    assert deleted.status_code == 204
    assert missing.status_code == 404
    assert cast(int, deleted_row) == 1
    remaining = cast(list[dict[str, object]], after.json()["items"])
    assert [item["id"] for item in remaining] == [first_id]
    assert after.json()["action_required"] == "CONFIRM"


@pytest.mark.anyio
async def test_confirm_transaction_supersedes_old_ai_batch_and_keeps_manual_rows(
    tmp_path: Path,
) -> None:
    model = FakeKnowledgePointModel()
    async with running_knowledge_point_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)

        first_batch, _first = await generate_draft_batch(client, record_id)
        first_confirm = await client.post(
            f"/api/records/{record_id}/knowledge-point-batches/{first_batch}/confirmations"
        )
        manual = await add_manual_item(client, record_id)
        second_batch, _second = await generate_draft_batch(client, record_id)
        second_confirm = await client.post(
            f"/api/records/{record_id}/knowledge-point-batches/{second_batch}/confirmations"
        )
        visible = await client.get(f"/api/records/{record_id}/knowledge-points")
        traced = await client.get(f"/api/records/{record_id}/knowledge-points?include=superseded")

        async with app.state.session_factory() as session:
            event_rows = (
                await session.execute(
                    text(
                        "SELECT source_type, source_id, idempotency_key, metadata_json "
                        "FROM learning_events WHERE event_type='KNOWLEDGE_CONFIRMED' "
                        "ORDER BY created_at"
                    )
                )
            ).all()
        traced_items = cast(list[dict[str, object]], traced.json()["items"])
        superseded_id = next(
            cast(str, item["id"])
            for item in traced_items
            if item["generation_status"] == "SUPERSEDED"
        )
        old_row_edit = await client.patch(
            f"/api/records/{record_id}/knowledge-points/{superseded_id}",
            json={
                "name": "尝试编辑过时行",
                "detail": "不应被允许。",
                "tags": [],
                "importance": 1,
            },
        )

    assert manual.status_code == 201
    assert first_confirm.status_code == 200, first_confirm.text
    assert second_confirm.status_code == 200, second_confirm.text
    assert [(row[0], row[1], row[2]) for row in event_rows] == [
        ("KNOWLEDGE_BATCH", first_batch, f"knowledge-confirmed:{first_batch}"),
        ("KNOWLEDGE_BATCH", second_batch, f"knowledge-confirmed:{second_batch}"),
    ]
    assert json.loads(event_rows[1][3]) == {
        "batch_id": second_batch,
        "confirmed_count": 2,
        "generated_from_summary_id": summary_id,
    }
    visible_items = cast(list[dict[str, object]], visible.json()["items"])
    assert {item["generation_status"] for item in visible_items} == {"ACTIVE"}
    assert {item["batch_id"] for item in visible_items} == {second_batch, None}
    assert [item["importance"] for item in visible_items] == [5, 4, 2]
    assert {(item["batch_id"], item["generation_status"]) for item in traced_items} == {
        (first_batch, "SUPERSEDED"),
        (second_batch, "ACTIVE"),
        (None, "ACTIVE"),
    }
    assert old_row_edit.status_code == 409
    assert len(model.prompts) == 2


@pytest.mark.anyio
async def test_double_confirm_is_idempotent_and_event_key_is_unique(
    tmp_path: Path,
) -> None:
    model = FakeKnowledgePointModel()
    async with running_knowledge_point_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)
        batch_id, payload = await generate_draft_batch(client, record_id)

        first = await client.post(
            f"/api/records/{record_id}/knowledge-point-batches/{batch_id}/confirmations"
        )
        second = await client.post(
            f"/api/records/{record_id}/knowledge-point-batches/{batch_id}/confirmations"
        )
        unknown = await client.post(
            f"/api/records/{record_id}/knowledge-point-batches/{uuid4()}/confirmations"
        )
        event_count = await confirmed_event_count(app.state.session_factory, record_id)

        for item in cast(list[dict[str, object]], payload["items"]):
            await client.delete(f"/api/records/{record_id}/knowledge-points/{item['id']}")
        third = await client.post(
            f"/api/records/{record_id}/knowledge-point-batches/{batch_id}/confirmations"
        )
        final_event_count = await confirmed_event_count(app.state.session_factory, record_id)
        async with app.state.session_factory() as session:
            event_row = (
                (
                    await session.execute(
                        text(
                            "SELECT source_id, score, metadata_json FROM learning_events "
                            "WHERE event_type='KNOWLEDGE_CONFIRMED' AND record_id=:record_id"
                        ),
                        {"record_id": record_id},
                    )
                )
                .mappings()
                .one()
            )

        with pytest.raises(IntegrityError):
            async with app.state.session_factory() as session, session.begin():
                session.add(
                    LearningEvent(
                        id=str(uuid4()),
                        course_id="11111111-1111-4111-8111-111111111111",
                        record_id=record_id,
                        event_type="KNOWLEDGE_CONFIRMED",
                        source_type="KNOWLEDGE_BATCH",
                        source_id=batch_id,
                        metadata_json="{}",
                        idempotency_key=f"knowledge-confirmed:{batch_id}",
                        schema_version=1,
                        occurred_at=utcnow(),
                    )
                )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["items"] == first.json()["items"]
    assert unknown.status_code == 404
    assert event_count == 1
    assert third.status_code == 200
    assert third.json()["items"] == []
    assert final_event_count == 1
    assert event_row["source_id"] == batch_id
    assert event_row["score"] is None
    assert json.loads(event_row["metadata_json"]) == {
        "batch_id": batch_id,
        "confirmed_count": len(cast(list[dict[str, object]], payload["items"])),
        "generated_from_summary_id": summary_id,
    }


@pytest.mark.anyio
async def test_confirm_blocked_by_stale_summary_or_archived_course_but_discard_works(
    tmp_path: Path,
) -> None:
    model = FakeKnowledgePointModel()
    async with running_knowledge_point_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)
        stale_batch, _payload = await generate_draft_batch(client, record_id)

        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE ai_summaries SET status='SUPERSEDED' WHERE record_id=:record_id"),
                {"record_id": record_id},
            )
        stale_confirm = await client.post(
            f"/api/records/{record_id}/knowledge-point-batches/{stale_batch}/confirmations"
        )
        stale_discard = await client.post(
            f"/api/records/{record_id}/knowledge-point-batches/{stale_batch}/discards"
        )
        after_discard = await client.get(f"/api/records/{record_id}/knowledge-points")

        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE ai_summaries SET status='CONFIRMED' WHERE record_id=:record_id"),
                {"record_id": record_id},
            )
        archived_batch, _payload = await generate_draft_batch(client, record_id)
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE courses SET status='ARCHIVED' "
                    "WHERE id=(SELECT course_id FROM records WHERE id=:record_id)"
                ),
                {"record_id": record_id},
            )
        archived_confirm = await client.post(
            f"/api/records/{record_id}/knowledge-point-batches/{archived_batch}/confirmations"
        )
        event_count = await confirmed_event_count(app.state.session_factory, record_id)

    assert stale_confirm.status_code == 409
    assert stale_confirm.json()["detail"] == "总结已换代或课程已归档，请丢弃当前候选后重新生成"
    assert stale_discard.status_code == 200
    assert after_discard.json()["items"] == []
    assert after_discard.json()["blocked_reason"] == "SUMMARY_SUPERSEDED"
    assert archived_confirm.status_code == 409
    assert event_count == 0


@pytest.mark.anyio
async def test_discard_soft_deletes_batch_and_keeps_manual_rows(tmp_path: Path) -> None:
    model = FakeKnowledgePointModel()
    async with running_knowledge_point_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)
        batch_id, _payload = await generate_draft_batch(client, record_id)
        manual = await add_manual_item(client, record_id)

        discarded = await client.post(
            f"/api/records/{record_id}/knowledge-point-batches/{batch_id}/discards"
        )
        again = await client.post(
            f"/api/records/{record_id}/knowledge-point-batches/{batch_id}/discards"
        )
        after = await client.get(f"/api/records/{record_id}/knowledge-points")

        async with app.state.session_factory() as session:
            remaining_draft = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM knowledge_points "
                        "WHERE batch_id=:batch_id AND deleted_at IS NULL"
                    ),
                    {"batch_id": batch_id},
                )
            ).scalar_one()

    assert manual.status_code == 201
    assert discarded.status_code == 200, discarded.text
    assert again.status_code == 404
    items = cast(list[dict[str, object]], after.json()["items"])
    assert [item["name"] for item in items] == ["手工补充：调度队列"]
    assert items[0]["generation_status"] == "ACTIVE"
    assert after.json()["action_required"] == "GENERATE"
    assert cast(int, remaining_draft) == 0


@pytest.mark.anyio
async def test_manual_changes_after_confirm_do_not_record_events(tmp_path: Path) -> None:
    model = FakeKnowledgePointModel()
    async with running_knowledge_point_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)
        batch_id, candidates = await generate_draft_batch(client, record_id)
        await client.post(
            f"/api/records/{record_id}/knowledge-point-batches/{batch_id}/confirmations"
        )
        items = cast(list[dict[str, object]], candidates["items"])

        await add_manual_item(client, record_id, name="确认后的手工补充")
        edited = await client.patch(
            f"/api/records/{record_id}/knowledge-points/{cast(str, items[0]['id'])}",
            json={
                "name": "确认后的编辑",
                "detail": "编辑已生效但不产生新事件。",
                "tags": [],
                "importance": 5,
            },
        )
        await client.delete(f"/api/records/{record_id}/knowledge-points/{items[1]['id']}")
        event_count = await confirmed_event_count(app.state.session_factory, record_id)
        final = await client.get(f"/api/records/{record_id}/knowledge-points")

    assert edited.status_code == 200
    assert event_count == 1
    final_items = cast(list[dict[str, object]], final.json()["items"])
    assert [item["name"] for item in final_items] == ["确认后的编辑", "确认后的手工补充"]
    assert all(item["generation_status"] == "ACTIVE" for item in final_items)


class FakeRegenerationSummaryModel:
    """换代链路测试中驱动新总结生成的最小 Fake，契约与 test_summary 的 Fake 一致。"""

    def __init__(self) -> None:
        self.prompts: list[str] = []

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
        output = SummaryContent(
            topic="进程调度（第二代）",
            abstract="转写修订后的第二代总结摘要，用于验证换代后的重新生成链路。" * 30,
            sections=[
                SummarySection(
                    heading="调度",
                    points=["调度器按修订后的策略选择下一个进程。"],
                )
            ],
        )
        return StructuredModelResult(output=output, token_usage={"total_tokens": 42})


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


async def edit_transcript(
    client: httpx.AsyncClient,
    record_id: str,
) -> httpx.Response:
    return await client.patch(
        f"/api/records/{record_id}/transcript",
        json={
            "content": "修订后的转写正文：调度器按优先级从就绪队列选择进程。",
            "expected_source_version": 1,
        },
    )


async def confirm_new_summary(
    client: httpx.AsyncClient,
    record_id: str,
) -> dict[str, object]:
    await client.post(f"/api/records/{record_id}/summary-jobs")
    summary = await wait_for_summary_version(client, record_id, 2)
    confirmed = await client.post(
        f"/api/records/{record_id}/summary-confirmations",
        json={"summary_id": summary["id"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    return summary


@pytest.mark.anyio
async def test_transcript_regeneration_full_chain(tmp_path: Path) -> None:
    model = FakeKnowledgePointModel()
    summary_model = FakeRegenerationSummaryModel()
    async with running_knowledge_point_app(
        tmp_path / "KnowRealm", model, summary_model=summary_model
    ) as (app, client):
        record_id, first_summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)

        first_batch, first_payload = await generate_draft_batch(client, record_id)
        first_confirm = await client.post(
            f"/api/records/{record_id}/knowledge-point-batches/{first_batch}/confirmations"
        )
        manual = await add_manual_item(client, record_id)
        stale_batch, _stale_payload = await generate_draft_batch(client, record_id)
        saved_item_id = cast(str, cast(list[dict[str, object]], first_payload["items"])[0]["id"])

        transcript_edit = await edit_transcript(client, record_id)
        record_after_edit = await client.get(f"/api/records/{record_id}")
        saved_during_change = await client.get(f"/api/records/{record_id}/knowledge-points")
        edit_during_change = await client.patch(
            f"/api/records/{record_id}/knowledge-points/{saved_item_id}",
            json={
                "name": "进程调度",
                "detail": "调度器按优先级从就绪队列选择下一个进程。",
                "tags": ["调度"],
                "importance": 5,
            },
        )
        blocked_confirm = await client.post(
            f"/api/records/{record_id}/knowledge-point-batches/{stale_batch}/confirmations"
        )
        blocked_submit = await client.post(f"/api/records/{record_id}/knowledge-point-jobs")
        discarded = await client.post(
            f"/api/records/{record_id}/knowledge-point-batches/{stale_batch}/discards"
        )
        after_discard = await client.get(f"/api/records/{record_id}/knowledge-points")

        second_summary = await confirm_new_summary(client, record_id)
        record_after_summary = await client.get(f"/api/records/{record_id}")
        unlocked = await client.get(f"/api/records/{record_id}/knowledge-points")

        second_batch, _second_payload = await generate_draft_batch(client, record_id)
        second_confirm = await client.post(
            f"/api/records/{record_id}/knowledge-point-batches/{second_batch}/confirmations"
        )
        final = await client.get(f"/api/records/{record_id}/knowledge-points")
        traced = await client.get(f"/api/records/{record_id}/knowledge-points?include=superseded")
        event_count = await confirmed_event_count(app.state.session_factory, record_id)
        async with app.state.session_factory() as session:
            event_rows = (
                await session.execute(
                    text(
                        "SELECT source_id, metadata_json FROM learning_events "
                        "WHERE event_type='KNOWLEDGE_CONFIRMED' ORDER BY created_at"
                    )
                )
            ).all()

    assert first_confirm.status_code == 200, first_confirm.text
    assert manual.status_code == 201, manual.text
    assert transcript_edit.status_code == 200, transcript_edit.text
    assert record_after_edit.json()["status"] == "SUMMARY_PENDING"
    during_items = cast(list[dict[str, object]], saved_during_change.json()["items"])
    assert {
        (cast(str | None, item["batch_id"]), cast(str, item["generation_status"]))
        for item in during_items
    } == {
        (first_batch, "ACTIVE"),
        (stale_batch, "DRAFT"),
        (None, "ACTIVE"),
    }
    assert saved_during_change.json()["action_required"] == "NONE"
    assert saved_during_change.json()["blocked_reason"] == "SUMMARY_SUPERSEDED"
    assert edit_during_change.status_code == 200, edit_during_change.text
    assert blocked_confirm.status_code == 409
    assert blocked_confirm.json()["detail"] == "总结已换代或课程已归档，请丢弃当前候选后重新生成"
    assert blocked_submit.status_code == 409
    assert blocked_submit.json()["detail"] == "请先确认当前总结"
    assert discarded.status_code == 200, discarded.text
    after_discard_items = cast(list[dict[str, object]], after_discard.json()["items"])
    assert {
        (cast(str | None, item["batch_id"]), cast(str, item["generation_status"]))
        for item in after_discard_items
    } == {(first_batch, "ACTIVE"), (None, "ACTIVE")}
    assert after_discard.json()["blocked_reason"] == "SUMMARY_SUPERSEDED"
    assert record_after_summary.json()["status"] == "COMPLETED"
    assert unlocked.json()["action_required"] == "GENERATE"
    assert unlocked.json()["blocked_reason"] is None
    assert second_confirm.status_code == 200, second_confirm.text
    final_items = cast(list[dict[str, object]], final.json()["items"])
    assert {
        (cast(str | None, item["batch_id"]), cast(str, item["generation_status"]))
        for item in final_items
    } == {(second_batch, "ACTIVE"), (None, "ACTIVE")}
    traced_items = cast(list[dict[str, object]], traced.json()["items"])
    assert {
        (cast(str | None, item["batch_id"]), cast(str, item["generation_status"]))
        for item in traced_items
    } == {
        (first_batch, "SUPERSEDED"),
        (second_batch, "ACTIVE"),
        (None, "ACTIVE"),
    }
    assert [row[0] for row in event_rows] == [first_batch, second_batch]
    assert json.loads(event_rows[1][1])["generated_from_summary_id"] == (second_summary["id"])
    assert second_summary["id"] != first_summary_id
    assert event_count == 2
    assert len(model.prompts) == 3


@pytest.mark.anyio
async def test_stale_draft_after_new_summary_confirm_guides_discard(
    tmp_path: Path,
) -> None:
    model = FakeKnowledgePointModel()
    summary_model = FakeRegenerationSummaryModel()
    async with running_knowledge_point_app(
        tmp_path / "KnowRealm", model, summary_model=summary_model
    ) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)
        stale_batch, stale_payload = await generate_draft_batch(client, record_id)

        await edit_transcript(client, record_id)
        second_summary = await confirm_new_summary(client, record_id)
        stale_read = await client.get(f"/api/records/{record_id}/knowledge-points")
        stale_confirm = await client.post(
            f"/api/records/{record_id}/knowledge-point-batches/{stale_batch}/confirmations"
        )
        stale_submit = await client.post(f"/api/records/{record_id}/knowledge-point-jobs")
        discarded = await client.post(
            f"/api/records/{record_id}/knowledge-point-batches/{stale_batch}/discards"
        )
        after = await client.get(f"/api/records/{record_id}/knowledge-points")
        event_count = await confirmed_event_count(app.state.session_factory, record_id)

    assert second_summary["version_no"] == 2
    stale_items = cast(list[dict[str, object]], stale_read.json()["items"])
    assert len(stale_items) == len(cast(list[dict[str, object]], stale_payload["items"]))
    assert all(item["generation_status"] == "DRAFT" for item in stale_items)
    assert stale_read.json()["action_required"] == "NONE"
    assert stale_read.json()["blocked_reason"] == "SUMMARY_SUPERSEDED"
    assert stale_confirm.status_code == 409
    assert stale_submit.status_code == 409
    assert stale_submit.json()["detail"] == "已有待确认的知识点候选"
    assert discarded.status_code == 200, discarded.text
    assert after.json()["items"] == []
    assert after.json()["action_required"] == "GENERATE"
    assert after.json()["blocked_reason"] is None
    assert event_count == 0
