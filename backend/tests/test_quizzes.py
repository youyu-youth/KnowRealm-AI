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
from sqlalchemy.exc import IntegrityError

from app.agents.llm import StructuredModelResult, SummaryModel
from app.db.migrations import run_migrations
from app.main import create_app
from app.schemas.quiz import QuizBatch

TOKEN = "test-launch-token"

ALL_TYPES = ["MULTIPLE_CHOICE", "TRUE_FALSE", "SHORT_ANSWER"]


def candidate(
    question_type: str,
    index: int,
) -> dict[str, object]:
    if question_type == "MULTIPLE_CHOICE":
        return {
            "question_type": "MULTIPLE_CHOICE",
            "stem": f"第 {index} 题：进程调度的基本功能是什么？",
            "options": ["选择就绪进程分配处理器", "管理内存分配", "处理外部中断", "维护文件系统"],
            "correct_answer": 0,
            "explanation": "进程调度决定哪个就绪进程获得处理器。",
            "difficulty": "EASY",
        }
    if question_type == "TRUE_FALSE":
        return {
            "question_type": "TRUE_FALSE",
            "stem": f"第 {index} 题：时间片越小，系统效率越高。",
            "options": ["对", "错"],
            "correct_answer": 1,
            "explanation": "时间片过小会导致上下文切换开销过大。",
            "difficulty": "MEDIUM",
        }
    return {
        "question_type": "SHORT_ANSWER",
        "stem": f"第 {index} 题：简述进程调度器的职责。",
        "options": [],
        "correct_answer": "调度器按照调度策略从就绪队列中选择下一个占用处理器的进程。",
        "explanation": "调度器负责就绪队列管理与处理器时间分配。",
        "difficulty": "MEDIUM",
    }


def batch_output(composition: list[str]) -> dict[str, object]:
    return {
        "items": [
            candidate(question_type, index) for index, question_type in enumerate(composition, 1)
        ]
    }


DEFAULT_OUTPUT = batch_output(ALL_TYPES)


def test_candidate_schema_rejects_invalid_question_shapes() -> None:
    wrong_true_false = batch_output(["TRUE_FALSE"])
    cast(list[dict[str, object]], wrong_true_false["items"])[0]["options"] = ["正确", "错误"]
    with pytest.raises(ValueError):
        QuizBatch.model_validate(wrong_true_false)

    short_answer_with_options = batch_output(["SHORT_ANSWER"])
    cast(list[dict[str, object]], short_answer_with_options["items"])[0]["options"] = ["提示"]
    with pytest.raises(ValueError):
        QuizBatch.model_validate(short_answer_with_options)

    float_answer = batch_output(["MULTIPLE_CHOICE"])
    cast(list[dict[str, object]], float_answer["items"])[0]["correct_answer"] = 0.5
    with pytest.raises(ValueError):
        QuizBatch.model_validate(float_answer)


class FakeQuizModel:
    def __init__(
        self,
        output: object | None = None,
        sequence: list[object] | None = None,
    ) -> None:
        self.output = output if output is not None else DEFAULT_OUTPUT
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
async def running_quiz_app(
    data_dir: Path,
    model: FakeQuizModel,
    *,
    summary_model: SummaryModel | None = None,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(
        data_dir=data_dir,
        launch_token=TOKEN,
        quiz_model=model,
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


async def read_quizzes(client: httpx.AsyncClient, record_id: str) -> dict[str, object]:
    return cast(
        dict[str, object],
        (await client.get(f"/api/records/{record_id}/quizzes")).json(),
    )


async def submit_quiz_job(
    client: httpx.AsyncClient,
    record_id: str,
    *,
    question_types: list[str] | None = None,
    total_count: int = 3,
) -> httpx.Response:
    return await client.post(
        f"/api/records/{record_id}/quiz-jobs",
        json={
            "question_types": question_types or ALL_TYPES,
            "total_count": total_count,
        },
    )


async def wait_for_action(
    client: httpx.AsyncClient,
    record_id: str,
    action: str,
) -> dict[str, object]:
    for _ in range(200):
        payload = await read_quizzes(client, record_id)
        if payload.get("action_required") == action:
            return payload
        await asyncio.sleep(0.02)
    pytest.fail(f"习题状态未进入 {action}")


def draft_batch_id(payload: dict[str, object]) -> str:
    items = cast(list[dict[str, object]], payload["items"])
    batch_ids = {
        cast(str, item["batch_id"]) for item in items if item["generation_status"] == "DRAFT"
    }
    assert len(batch_ids) == 1
    return batch_ids.pop()


async def generate_draft_batch(
    client: httpx.AsyncClient,
    record_id: str,
    *,
    question_types: list[str] | None = None,
    total_count: int = 3,
) -> tuple[str, dict[str, object]]:
    accepted = await submit_quiz_job(
        client, record_id, question_types=question_types, total_count=total_count
    )
    assert accepted.status_code == 202, accepted.text
    payload = await wait_for_action(client, record_id, "ADOPT")
    return draft_batch_id(payload), payload


@pytest.mark.anyio
async def test_quiz_migration_creates_table_and_active_job_guard(tmp_path: Path) -> None:
    db_path = tmp_path / "knowrealm.db"

    await run_migrations(db_path)

    async with aiosqlite.connect(db_path) as connection:
        version = await (await connection.execute("PRAGMA user_version")).fetchone()
        columns = {
            cast(str, row[1])
            for row in await (await connection.execute("PRAGMA table_info(quizzes)")).fetchall()
        }
        job_indexes = {
            cast(str, row[1])
            for row in await (
                await connection.execute("PRAGMA index_list(processing_jobs)")
            ).fetchall()
        }

    assert version == (14,)
    assert {
        "id",
        "record_id",
        "batch_id",
        "generated_from_summary_id",
        "generation_status",
        "question_type",
        "stem",
        "options_json",
        "correct_answer_json",
        "explanation",
        "difficulty",
        "user_answer_json",
        "answer_result",
        "answered_at",
        "created_at",
        "updated_at",
        "deleted_at",
    } == columns
    assert "idx_processing_jobs_one_active_quiz_generation" in job_indexes


@pytest.mark.anyio
async def test_adopt_batch_supersedes_previous_batch_and_keeps_history(tmp_path: Path) -> None:
    model = FakeQuizModel()
    async with running_quiz_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)

        first_batch_id, _first_draft = await generate_draft_batch(client, record_id)
        first_adoption = await client.post(
            f"/api/records/{record_id}/quiz-batches/{first_batch_id}/confirmations"
        )
        repeated_adoption = await client.post(
            f"/api/records/{record_id}/quiz-batches/{first_batch_id}/confirmations"
        )
        async with app.state.session_factory() as session, session.begin():
            first_item_id = cast(
                str,
                await session.scalar(
                    text(
                        "SELECT id FROM quizzes WHERE batch_id=:batch_id "
                        "ORDER BY created_at LIMIT 1"
                    ),
                    {"batch_id": first_batch_id},
                ),
            )
            await session.execute(
                text(
                    "UPDATE quizzes SET user_answer_json='0', answer_result='CORRECT', "
                    "answered_at='2026-08-25T13:00:00.000000Z' WHERE id=:item_id"
                ),
                {"item_id": first_item_id},
            )

        second_batch_id, during_regeneration = await generate_draft_batch(client, record_id)
        async with app.state.session_factory() as session:
            with pytest.raises(IntegrityError):
                await session.execute(
                    text("UPDATE quizzes SET generation_status='ACTIVE' WHERE batch_id=:batch_id"),
                    {"batch_id": second_batch_id},
                )
                await session.commit()
            await session.rollback()

        second_adoption = await client.post(
            f"/api/records/{record_id}/quiz-batches/{second_batch_id}/confirmations"
        )
        visible = await read_quizzes(client, record_id)
        history_response = await client.get(f"/api/records/{record_id}/quizzes?include=superseded")
        async with app.state.session_factory() as session:
            quiz_events = await session.scalar(
                text("SELECT count(*) FROM learning_events WHERE event_type LIKE 'QUIZ_%'")
            )

    assert first_adoption.status_code == 200, first_adoption.text
    assert repeated_adoption.status_code == 200, repeated_adoption.text
    during_items = cast(list[dict[str, object]], during_regeneration["items"])
    assert {item["generation_status"] for item in during_items} == {"ACTIVE", "DRAFT"}
    assert second_adoption.status_code == 200, second_adoption.text
    visible_items = cast(list[dict[str, object]], visible["items"])
    assert {item["batch_id"] for item in visible_items} == {second_batch_id}
    assert {item["generation_status"] for item in visible_items} == {"ACTIVE"}
    history_items = cast(list[dict[str, object]], history_response.json()["items"])
    old_items = [item for item in history_items if item["batch_id"] == first_batch_id]
    assert len(history_items) == 6
    assert {item["generation_status"] for item in old_items} == {"SUPERSEDED"}
    answered = next(item for item in old_items if item["id"] == first_item_id)
    assert answered["user_answer"] == 0
    assert answered["answer_result"] == "CORRECT"
    assert answered["answered_at"] == "2026-08-25T13:00:00.000000Z"
    assert quiz_events == 0


@pytest.mark.anyio
async def test_adopt_stale_draft_returns_blocked_reason_and_keeps_active_batch(
    tmp_path: Path,
) -> None:
    model = FakeQuizModel()
    async with running_quiz_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)
        active_batch_id, _first = await generate_draft_batch(client, record_id)
        adopted = await client.post(
            f"/api/records/{record_id}/quiz-batches/{active_batch_id}/confirmations"
        )
        stale_batch_id, _second = await generate_draft_batch(client, record_id)

        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE ai_summaries SET status='SUPERSEDED' WHERE record_id=:record_id"),
                {"record_id": record_id},
            )
        stale_adoption = await client.post(
            f"/api/records/{record_id}/quiz-batches/{stale_batch_id}/confirmations"
        )
        stale_read = await read_quizzes(client, record_id)

        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE ai_summaries SET status='CONFIRMED' WHERE record_id=:record_id"),
                {"record_id": record_id},
            )
            await session.execute(
                text(
                    "UPDATE courses SET status='ARCHIVED' WHERE id="
                    "(SELECT course_id FROM records WHERE id=:record_id)"
                ),
                {"record_id": record_id},
            )
        archived_adoption = await client.post(
            f"/api/records/{record_id}/quiz-batches/{stale_batch_id}/confirmations"
        )

    assert adopted.status_code == 200, adopted.text
    assert stale_adoption.status_code == 409
    assert stale_adoption.json()["blocked_reason"] == "SUMMARY_SUPERSEDED"
    stale_items = cast(list[dict[str, object]], stale_read["items"])
    assert stale_read["blocked_reason"] == "SUMMARY_SUPERSEDED"
    assert any(
        item["batch_id"] == active_batch_id and item["generation_status"] == "ACTIVE"
        for item in stale_items
    )
    assert archived_adoption.status_code == 409
    assert archived_adoption.json()["blocked_reason"] == "COURSE_ARCHIVED"


@pytest.mark.anyio
async def test_generate_candidates_persists_draft_batch_and_provenance(tmp_path: Path) -> None:
    model = FakeQuizModel(output=batch_output(["MULTIPLE_CHOICE", "TRUE_FALSE", "SHORT_ANSWER"]))
    async with running_quiz_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)

        before = await read_quizzes(client, record_id)
        accepted = await submit_quiz_job(client, record_id, total_count=3)
        candidates = await wait_for_action(client, record_id, "ADOPT")

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
                        "FROM llm_call_logs WHERE graph_name='quiz'"
                    )
                )
            ).one()
            answer_row = (
                await session.execute(
                    text(
                        "SELECT user_answer_json, answer_result, answered_at "
                        "FROM quizzes WHERE record_id=:record_id LIMIT 1"
                    ),
                    {"record_id": record_id},
                )
            ).one()

    assert before["action_required"] == "GENERATE"
    items = cast(list[dict[str, object]], candidates["items"])
    assert [item["question_type"] for item in items] == ALL_TYPES
    assert all(
        item["generation_status"] == "DRAFT"
        and item["batch_id"] == accepted.json()["job_id"]
        and item["generated_from_summary_id"] == summary_id
        and item["user_answer"] is None
        and item["answer_result"] is None
        and item["answered_at"] is None
        for item in items
    )
    assert tuple(answer_row) == (None, None, None)
    assert len(model.prompts) == 1
    assert "学习场景：SCHOOL" in model.prompts[0]
    assert "恰好出 3 题" in model.prompts[0]
    assert "已确认总结" in model.prompts[0]
    result = json.loads(cast(str, job_row.result_json))
    assert result == {
        "model": "qwen-plus",
        "prompt_version": "quiz_v1",
        "question_count": 3,
        "question_types": {"MULTIPLE_CHOICE": 1, "TRUE_FALSE": 1, "SHORT_ANSWER": 1},
    }
    assert job_row.status == "SUCCEEDED"
    assert tuple(log_row) == ("quiz", "generate", "quiz_v1", None)


@pytest.mark.anyio
async def test_generate_rejects_missing_prerequisites_without_creating_jobs(
    tmp_path: Path,
) -> None:
    model = FakeQuizModel()
    async with running_quiz_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)

        missing_provider = await submit_quiz_job(client, record_id)
        await configure_llm(client)
        missing_consent = await submit_quiz_job(client, record_id)
        await grant_llm_consent(client)
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE ai_summaries SET status='SUPERSEDED' WHERE record_id=:record_id"),
                {"record_id": record_id},
            )
        missing_summary = await submit_quiz_job(client, record_id)
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
        archived_course = await submit_quiz_job(client, record_id)
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "UPDATE courses SET status='ACTIVE' "
                    "WHERE id=(SELECT course_id FROM records WHERE id=:record_id)"
                ),
                {"record_id": record_id},
            )
        accepted = await submit_quiz_job(client, record_id)
        assert accepted.status_code == 202, accepted.text
        await wait_for_action(client, record_id, "ADOPT")
        existing_draft = await submit_quiz_job(client, record_id)
        async with app.state.session_factory() as session:
            job_count = await session.scalar(
                text("SELECT count(*) FROM processing_jobs WHERE job_type='QUIZ_GENERATION'")
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
async def test_generate_rejects_invalid_requests_at_boundary(tmp_path: Path) -> None:
    model = FakeQuizModel()
    async with running_quiz_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)

        empty_types = await client.post(
            f"/api/records/{record_id}/quiz-jobs",
            json={"question_types": [], "total_count": 3},
        )
        duplicate_types = await client.post(
            f"/api/records/{record_id}/quiz-jobs",
            json={"question_types": ["TRUE_FALSE", "TRUE_FALSE"], "total_count": 3},
        )
        bad_count = await client.post(
            f"/api/records/{record_id}/quiz-jobs",
            json={"question_types": ALL_TYPES, "total_count": 7},
        )

    assert [empty_types.status_code, duplicate_types.status_code, bad_count.status_code] == [
        422,
        422,
        422,
    ]
    assert len(model.prompts) == 0


@pytest.mark.anyio
async def test_count_mismatch_fails_job_with_llm_output_invalid(tmp_path: Path) -> None:
    model = FakeQuizModel(output=batch_output(["MULTIPLE_CHOICE"] * 3))
    async with running_quiz_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)

        accepted = await submit_quiz_job(client, record_id, total_count=3)
        failed = await wait_for_action(client, record_id, "RETRY")

        async with app.state.session_factory() as session:
            job_row = (
                await session.execute(
                    text("SELECT status, error_code FROM processing_jobs WHERE id=:job_id"),
                    {"job_id": accepted.json()["job_id"]},
                )
            ).one()
            log_errors = list(
                (
                    await session.scalars(
                        text(
                            "SELECT error_code FROM llm_call_logs "
                            "WHERE graph_name='quiz' ORDER BY created_at"
                        )
                    )
                ).all()
            )

    assert accepted.status_code == 202
    assert failed["items"] == []
    assert job_row == ("FAILED", "LLM_OUTPUT_INVALID")
    assert log_errors == [None]


@pytest.mark.anyio
async def test_missing_selected_type_fails_job_with_llm_output_invalid(tmp_path: Path) -> None:
    # 输出 3 题但缺少所选题型之一（简答题），批次构成违规。
    model = FakeQuizModel(output=batch_output(["MULTIPLE_CHOICE", "MULTIPLE_CHOICE", "TRUE_FALSE"]))
    async with running_quiz_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)

        accepted = await submit_quiz_job(client, record_id, total_count=3)
        failed = await wait_for_action(client, record_id, "RETRY")

        async with app.state.session_factory() as session:
            job_row = (
                await session.execute(
                    text("SELECT status, error_code FROM processing_jobs WHERE id=:job_id"),
                    {"job_id": accepted.json()["job_id"]},
                )
            ).one()
            quiz_count = await session.scalar(
                text("SELECT count(*) FROM quizzes WHERE record_id=:record_id"),
                {"record_id": record_id},
            )

    assert accepted.status_code == 202
    assert failed["items"] == []
    assert job_row == ("FAILED", "LLM_OUTPUT_INVALID")
    assert quiz_count == 0


@pytest.mark.anyio
async def test_unselected_type_in_output_fails_job_with_llm_output_invalid(
    tmp_path: Path,
) -> None:
    # 只勾选选择题与判断题，输出却混入未勾选的简答题——用户勾选必须被如实兑现。
    model = FakeQuizModel(output=batch_output(["MULTIPLE_CHOICE", "TRUE_FALSE", "SHORT_ANSWER"]))
    async with running_quiz_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)

        accepted = await submit_quiz_job(
            client,
            record_id,
            question_types=["MULTIPLE_CHOICE", "TRUE_FALSE"],
            total_count=3,
        )
        failed = await wait_for_action(client, record_id, "RETRY")

        async with app.state.session_factory() as session:
            job_row = (
                await session.execute(
                    text("SELECT status, error_code FROM processing_jobs WHERE id=:job_id"),
                    {"job_id": accepted.json()["job_id"]},
                )
            ).one()
            quiz_count = await session.scalar(
                text("SELECT count(*) FROM quizzes WHERE record_id=:record_id"),
                {"record_id": record_id},
            )

    assert accepted.status_code == 202
    assert failed["items"] == []
    assert job_row == ("FAILED", "LLM_OUTPUT_INVALID")
    assert quiz_count == 0


@pytest.mark.anyio
async def test_invalid_output_fails_once_and_manual_retry_reuses_job(tmp_path: Path) -> None:
    invalid = cast(
        object,
        {
            "items": [
                {
                    "question_type": "TRUE_FALSE",
                    "stem": "判断题选项形状错误",
                    "options": ["正确", "错误"],
                    "correct_answer": 0,
                    "explanation": "判断题选项必须固定为「对 / 错」。",
                    "difficulty": "EASY",
                }
            ]
        },
    )
    model = FakeQuizModel(sequence=[invalid, DEFAULT_OUTPUT])
    async with running_quiz_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)

        first = await submit_quiz_job(client, record_id, total_count=3)
        failed = await wait_for_action(client, record_id, "RETRY")
        retry = await submit_quiz_job(client, record_id, total_count=3)
        candidates = await wait_for_action(client, record_id, "ADOPT")

        async with app.state.session_factory() as session:
            job_rows = (
                await session.execute(
                    text(
                        "SELECT id, status, attempts FROM processing_jobs "
                        "WHERE job_type='QUIZ_GENERATION'"
                    )
                )
            ).all()
            log_errors = list(
                (
                    await session.scalars(
                        text(
                            "SELECT error_code FROM llm_call_logs "
                            "WHERE graph_name='quiz' ORDER BY created_at"
                        )
                    )
                ).all()
            )

    assert failed["items"] == []
    assert first.status_code == 202
    assert retry.status_code == 202
    assert first.json()["job_id"] == retry.json()["job_id"]
    assert candidates["action_required"] == "ADOPT"
    assert [tuple(row) for row in job_rows] == [(first.json()["job_id"], "SUCCEEDED", 1)]
    assert log_errors == ["LLM_OUTPUT_INVALID", None]
    assert len(model.prompts) == 2


@pytest.mark.anyio
async def test_generate_five_questions_with_two_selected_types(tmp_path: Path) -> None:
    composition = [
        "MULTIPLE_CHOICE",
        "TRUE_FALSE",
        "MULTIPLE_CHOICE",
        "TRUE_FALSE",
        "MULTIPLE_CHOICE",
    ]
    model = FakeQuizModel(output=batch_output(composition))
    async with running_quiz_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)

        accepted = await submit_quiz_job(
            client, record_id, question_types=["MULTIPLE_CHOICE", "TRUE_FALSE"], total_count=5
        )
        candidates = await wait_for_action(client, record_id, "ADOPT")

        async with app.state.session_factory() as session:
            result_json = cast(
                str,
                await session.scalar(
                    text("SELECT result_json FROM processing_jobs WHERE id=:job_id"),
                    {"job_id": accepted.json()["job_id"]},
                ),
            )

    assert accepted.status_code == 202
    items = cast(list[dict[str, object]], candidates["items"])
    assert len(items) == 5
    assert {item["question_type"] for item in items} == {"MULTIPLE_CHOICE", "TRUE_FALSE"}
    assert json.loads(result_json)["question_types"] == {"MULTIPLE_CHOICE": 3, "TRUE_FALSE": 2}
    assert "恰好出 5 题" in model.prompts[0]
    assert "选择题、判断题" in model.prompts[0]


@pytest.mark.anyio
async def test_active_job_guard_rejects_duplicate_submit(tmp_path: Path) -> None:
    model = FakeQuizModel()
    model.release.clear()
    async with running_quiz_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)

        first = await submit_quiz_job(client, record_id)
        await asyncio.wait_for(model.started.wait(), timeout=2)
        duplicate = await submit_quiz_job(client, record_id)
        async with app.state.session_factory() as session:
            active_count = await session.scalar(
                text(
                    "SELECT count(*) FROM processing_jobs "
                    "WHERE job_type='QUIZ_GENERATION' "
                    "AND status IN ('PENDING', 'RUNNING')"
                )
            )
        model.release.set()
        await wait_for_action(client, record_id, "ADOPT")

    assert first.status_code == 202
    assert duplicate.status_code == 409
    assert active_count == 1


@pytest.mark.anyio
async def test_soft_delete_during_generation_cancels_job_without_rows(tmp_path: Path) -> None:
    model = FakeQuizModel()
    model.release.clear()
    async with running_quiz_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)

        accepted = await submit_quiz_job(client, record_id)
        await asyncio.wait_for(model.started.wait(), timeout=2)
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE records SET deleted_at=:deleted_at WHERE id=:record_id"),
                {
                    "record_id": record_id,
                    "deleted_at": "2026-08-25T10:00:00.000000Z",
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
                        text("SELECT count(*) FROM quizzes WHERE record_id=:record_id"),
                        {"record_id": record_id},
                    ),
                )
            if status == "CANCELLED":
                break
            await asyncio.sleep(0.05)

    assert accepted.status_code == 202
    assert status == "CANCELLED"
    assert candidate_count == 0


@pytest.mark.anyio
async def test_discard_soft_deletes_batch_and_allows_regeneration(tmp_path: Path) -> None:
    model = FakeQuizModel()
    async with running_quiz_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)
        batch_id, _payload = await generate_draft_batch(client, record_id)

        discarded = await client.post(f"/api/records/{record_id}/quiz-batches/{batch_id}/discards")
        again = await client.post(f"/api/records/{record_id}/quiz-batches/{batch_id}/discards")
        after = await read_quizzes(client, record_id)
        regenerated_batch, _regenerated = await generate_draft_batch(client, record_id)

        async with app.state.session_factory() as session:
            remaining = await session.scalar(
                text(
                    "SELECT count(*) FROM quizzes WHERE batch_id=:batch_id AND deleted_at IS NULL"
                ),
                {"batch_id": batch_id},
            )

    assert discarded.status_code == 200, discarded.text
    assert again.status_code == 404
    assert after["items"] == []
    assert after["action_required"] == "GENERATE"
    assert cast(int, remaining) == 0
    assert regenerated_batch != batch_id
    assert len(model.prompts) == 2


@pytest.mark.anyio
async def test_superseded_summary_blocks_read_and_submit_until_discard(tmp_path: Path) -> None:
    model = FakeQuizModel()
    async with running_quiz_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)
        batch_id, _payload = await generate_draft_batch(client, record_id)

        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE ai_summaries SET status='SUPERSEDED' WHERE record_id=:record_id"),
                {"record_id": record_id},
            )
        stale_read = await read_quizzes(client, record_id)
        stale_submit = await submit_quiz_job(client, record_id)
        discarded = await client.post(f"/api/records/{record_id}/quiz-batches/{batch_id}/discards")
        after = await read_quizzes(client, record_id)

    assert stale_read["action_required"] == "NONE"
    assert stale_read["blocked_reason"] == "SUMMARY_SUPERSEDED"
    assert stale_submit.status_code == 409
    assert discarded.status_code == 200
    assert after["items"] == []
    assert after["action_required"] == "NONE"
    assert after["blocked_reason"] == "SUMMARY_SUPERSEDED"


@pytest.mark.anyio
async def test_read_reports_missing_prerequisites_as_blocked_reasons(tmp_path: Path) -> None:
    model = FakeQuizModel()
    async with running_quiz_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)

        missing_provider = await read_quizzes(client, record_id)
        await configure_llm(client)
        missing_consent = await read_quizzes(client, record_id)
        await grant_llm_consent(client)
        ready = await read_quizzes(client, record_id)

    assert missing_provider["blocked_reason"] == "PROVIDER_NOT_CONFIGURED"
    assert missing_consent["blocked_reason"] == "CONSENT_REQUIRED"
    assert ready["blocked_reason"] is None
    assert ready["action_required"] == "GENERATE"


@pytest.mark.anyio
async def test_quiz_last_count_preference_round_trip(tmp_path: Path) -> None:
    model = FakeQuizModel()
    async with running_quiz_app(tmp_path / "KnowRealm", model) as (_app, client):
        default = await client.get("/api/settings/preferences")
        updated = await client.put(
            "/api/settings/preferences",
            json={"quiz_last_count": 10},
        )
        reread = await client.get("/api/settings/preferences")
        invalid = await client.put(
            "/api/settings/preferences",
            json={"quiz_last_count": 7},
        )

    assert default.json() == {
        "theme": "SYSTEM",
        "font_scale": "M",
        "timezone": None,
        "close_behavior": "TRAY",
        "quick_note_shortcut": "Ctrl+Alt+N",
        "autostart": False,
        "quiz_last_count": 5,
        "last_route": None,
    }
    assert updated.json() == {
        "theme": "SYSTEM",
        "font_scale": "M",
        "timezone": None,
        "close_behavior": "TRAY",
        "quick_note_shortcut": "Ctrl+Alt+N",
        "autostart": False,
        "quiz_last_count": 10,
        "last_route": None,
    }
    assert reread.json() == updated.json()
    assert invalid.status_code == 422


@pytest.mark.anyio
async def test_answer_objective_quizzes_scores_once_and_persists_events(tmp_path: Path) -> None:
    model = FakeQuizModel()
    async with running_quiz_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)
        batch_id, draft = await generate_draft_batch(client, record_id)
        adopted = await client.post(
            f"/api/records/{record_id}/quiz-batches/{batch_id}/confirmations"
        )
        assert adopted.status_code == 200, adopted.text
        items = cast(list[dict[str, object]], draft["items"])
        multiple_choice = next(item for item in items if item["question_type"] == "MULTIPLE_CHOICE")
        true_false = next(item for item in items if item["question_type"] == "TRUE_FALSE")
        adopted_items = cast(list[dict[str, object]], adopted.json()["items"])
        unanswered = next(item for item in adopted_items if item["id"] == multiple_choice["id"])
        assert unanswered["correct_answer"] is None
        assert unanswered["explanation"] is None

        invalid = await client.post(
            f"/api/records/{record_id}/quizzes/{multiple_choice['id']}/answers",
            json={"answer": 99},
        )
        wrong = await client.post(
            f"/api/records/{record_id}/quizzes/{multiple_choice['id']}/answers",
            json={"answer": 2},
        )
        repeated = await client.post(
            f"/api/records/{record_id}/quizzes/{multiple_choice['id']}/answers",
            json={"answer": 0},
        )
        correct = await client.post(
            f"/api/records/{record_id}/quizzes/{true_false['id']}/answers",
            json={"answer": 1},
        )
        restored = await read_quizzes(client, record_id)

        async with app.state.session_factory() as session:
            events = (
                (
                    await session.execute(
                        text(
                            "SELECT source_type, source_id, result, score, difficulty, "
                            "duration_ms, concept_id, metadata_json, idempotency_key "
                            "FROM learning_events "
                            "WHERE event_type='QUIZ_ANSWERED' ORDER BY source_id"
                        )
                    )
                )
                .mappings()
                .all()
            )

    assert invalid.status_code == 400, invalid.text
    assert wrong.status_code == 200, wrong.text
    assert wrong.json()["user_answer"] == 2
    assert wrong.json()["answer_result"] == "WRONG"
    assert wrong.json()["answered_at"] is not None
    assert wrong.json()["correct_answer"] == 0
    assert wrong.json()["explanation"] == "进程调度决定哪个就绪进程获得处理器。"
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["user_answer"] == 2
    assert repeated.json()["answer_result"] == "WRONG"
    assert repeated.json()["answered_at"] == wrong.json()["answered_at"]
    assert correct.status_code == 200, correct.text
    assert correct.json()["answer_result"] == "CORRECT"
    restored_items = cast(list[dict[str, object]], restored["items"])
    restored_wrong = next(item for item in restored_items if item["id"] == multiple_choice["id"])
    assert restored_wrong["user_answer"] == 2
    assert restored_wrong["answer_result"] == "WRONG"
    assert len(events) == 2
    by_source_id = {event["source_id"]: event for event in events}
    wrong_event = by_source_id[multiple_choice["id"]]
    assert wrong_event["source_type"] == "QUIZ_QUESTION"
    assert wrong_event["result"] == "WRONG"
    assert wrong_event["score"] is None
    assert wrong_event["difficulty"] == "EASY"
    assert wrong_event["duration_ms"] is None
    assert wrong_event["concept_id"] is None
    assert wrong_event["idempotency_key"] == f"quiz-answered:{multiple_choice['id']}"
    assert json.loads(wrong_event["metadata_json"]) == {
        "batch_id": batch_id,
        "question_type": "MULTIPLE_CHOICE",
        "generated_from_summary_id": summary_id,
    }
    assert "answer" not in wrong_event["metadata_json"]


@pytest.mark.anyio
async def test_short_answer_reveals_reference_without_creating_event(tmp_path: Path) -> None:
    model = FakeQuizModel()
    async with running_quiz_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)
        batch_id, draft = await generate_draft_batch(client, record_id)
        short_draft = next(
            item
            for item in cast(list[dict[str, object]], draft["items"])
            if item["question_type"] == "SHORT_ANSWER"
        )
        adopted = await client.post(
            f"/api/records/{record_id}/quiz-batches/{batch_id}/confirmations"
        )
        short_active = next(
            item
            for item in cast(list[dict[str, object]], adopted.json()["items"])
            if item["id"] == short_draft["id"]
        )

        blank = await client.post(
            f"/api/records/{record_id}/quizzes/{short_draft['id']}/answers",
            json={"answer": "   "},
        )
        submitted = await client.post(
            f"/api/records/{record_id}/quizzes/{short_draft['id']}/answers",
            json={"answer": "调度器从就绪队列中选择下一个进程。"},
        )
        repeated = await client.post(
            f"/api/records/{record_id}/quizzes/{short_draft['id']}/answers",
            json={"answer": "第二次提交不能覆盖首次作答。"},
        )
        restored = await read_quizzes(client, record_id)
        async with app.state.session_factory() as session:
            event_count = await session.scalar(
                text("SELECT count(*) FROM learning_events WHERE source_id=:quiz_id"),
                {"quiz_id": short_draft["id"]},
            )

    assert short_active["correct_answer"] is None
    assert short_active["explanation"] is None
    assert blank.status_code == 422, blank.text
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["user_answer"] == "调度器从就绪队列中选择下一个进程。"
    assert submitted.json()["answer_result"] is None
    assert submitted.json()["answered_at"] is not None
    assert submitted.json()["correct_answer"] == short_draft["correct_answer"]
    assert submitted.json()["explanation"] == short_draft["explanation"]
    assert repeated.json()["user_answer"] == submitted.json()["user_answer"]
    restored_short = next(
        item
        for item in cast(list[dict[str, object]], restored["items"])
        if item["id"] == short_draft["id"]
    )
    assert restored_short == submitted.json()
    assert event_count == 0


@pytest.mark.anyio
async def test_short_answer_self_assessment_creates_event_and_completes_batch(
    tmp_path: Path,
) -> None:
    model = FakeQuizModel()
    async with running_quiz_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)
        batch_id, draft = await generate_draft_batch(client, record_id)
        items = cast(list[dict[str, object]], draft["items"])
        choice = next(item for item in items if item["question_type"] == "MULTIPLE_CHOICE")
        true_false = next(item for item in items if item["question_type"] == "TRUE_FALSE")
        short = next(item for item in items if item["question_type"] == "SHORT_ANSWER")
        await client.post(f"/api/records/{record_id}/quiz-batches/{batch_id}/confirmations")

        premature = await client.post(
            f"/api/records/{record_id}/quizzes/{short['id']}/self-assessments",
            json={"result": "CORRECT"},
        )
        await client.post(
            f"/api/records/{record_id}/quizzes/{choice['id']}/answers",
            json={"answer": 0},
        )
        await client.post(
            f"/api/records/{record_id}/quizzes/{true_false['id']}/answers",
            json={"answer": 0},
        )
        await client.post(
            f"/api/records/{record_id}/quizzes/{short['id']}/answers",
            json={"answer": "调度器负责选择就绪进程。"},
        )
        pending = await read_quizzes(client, record_id)
        assessed = await client.post(
            f"/api/records/{record_id}/quizzes/{short['id']}/self-assessments",
            json={"result": "CORRECT"},
        )
        repeated = await client.post(
            f"/api/records/{record_id}/quizzes/{short['id']}/self-assessments",
            json={"result": "WRONG"},
        )
        completed = await read_quizzes(client, record_id)
        async with app.state.session_factory() as session:
            events = (
                (
                    await session.execute(
                        text(
                            "SELECT source_id, result, difficulty, metadata_json, idempotency_key "
                            "FROM learning_events WHERE event_type='QUIZ_ANSWERED' "
                            "ORDER BY source_id"
                        )
                    )
                )
                .mappings()
                .all()
            )

    pending_items = cast(list[dict[str, object]], pending["items"])
    pending_short = next(item for item in pending_items if item["id"] == short["id"])
    completed_items = cast(list[dict[str, object]], completed["items"])
    assert premature.status_code == 409, premature.text
    assert pending_short["answer_result"] is None
    assert not all(item["answer_result"] is not None for item in pending_items)
    assert assessed.status_code == 200, assessed.text
    assert assessed.json()["answer_result"] == "CORRECT"
    assert repeated.json()["answer_result"] == "CORRECT"
    assert all(item["answer_result"] is not None for item in completed_items)
    assert sum(item["answer_result"] == "CORRECT" for item in completed_items) == 2
    assert len(events) == 3
    short_event = next(event for event in events if event["source_id"] == short["id"])
    assert short_event["result"] == "CORRECT"
    assert short_event["difficulty"] == "MEDIUM"
    assert short_event["idempotency_key"] == f"quiz-answered:{short['id']}"
    assert json.loads(short_event["metadata_json"]) == {
        "batch_id": batch_id,
        "question_type": "SHORT_ANSWER",
        "generated_from_summary_id": summary_id,
    }


@pytest.mark.anyio
async def test_short_self_assessment_and_event_roll_back_together(tmp_path: Path) -> None:
    model = FakeQuizModel()
    async with running_quiz_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)
        batch_id, draft = await generate_draft_batch(client, record_id)
        short = next(
            item
            for item in cast(list[dict[str, object]], draft["items"])
            if item["question_type"] == "SHORT_ANSWER"
        )
        await client.post(f"/api/records/{record_id}/quiz-batches/{batch_id}/confirmations")
        submitted = await client.post(
            f"/api/records/{record_id}/quizzes/{short['id']}/answers",
            json={"answer": "调度器负责选择就绪进程。"},
        )
        assert submitted.status_code == 200, submitted.text
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "CREATE TRIGGER reject_short_answer_event BEFORE INSERT ON learning_events "
                    "WHEN NEW.event_type='QUIZ_ANSWERED' BEGIN "
                    "SELECT RAISE(ABORT, 'forced event failure'); END"
                )
            )

        failed = await client.post(
            f"/api/records/{record_id}/quizzes/{short['id']}/self-assessments",
            json={"result": "CORRECT"},
        )
        async with app.state.session_factory() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT user_answer_json, answer_result, answered_at FROM quizzes "
                        "WHERE id=:quiz_id"
                    ),
                    {"quiz_id": short["id"]},
                )
            ).one()
            event_count = await session.scalar(
                text("SELECT count(*) FROM learning_events WHERE source_id=:quiz_id"),
                {"quiz_id": short["id"]},
            )

    assert failed.status_code == 500
    assert json.loads(row.user_answer_json) == "调度器负责选择就绪进程。"
    assert row.answer_result is None
    assert row.answered_at is not None
    assert event_count == 0


@pytest.mark.anyio
async def test_objective_answer_requires_active_batch_but_not_current_summary(
    tmp_path: Path,
) -> None:
    model = FakeQuizModel()
    async with running_quiz_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)
        first_batch_id, first_draft = await generate_draft_batch(client, record_id)
        first_items = cast(list[dict[str, object]], first_draft["items"])
        first_choice = next(
            item for item in first_items if item["question_type"] == "MULTIPLE_CHOICE"
        )
        draft_answer = await client.post(
            f"/api/records/{record_id}/quizzes/{first_choice['id']}/answers",
            json={"answer": 0},
        )
        await client.post(f"/api/records/{record_id}/quiz-batches/{first_batch_id}/confirmations")
        second_batch_id, _second_draft = await generate_draft_batch(client, record_id)
        await client.post(f"/api/records/{record_id}/quiz-batches/{second_batch_id}/confirmations")
        superseded_answer = await client.post(
            f"/api/records/{record_id}/quizzes/{first_choice['id']}/answers",
            json={"answer": 0},
        )

        active = await read_quizzes(client, record_id)
        active_items = cast(list[dict[str, object]], active["items"])
        active_choice = next(
            item for item in active_items if item["question_type"] == "MULTIPLE_CHOICE"
        )
        active_short = next(
            item for item in active_items if item["question_type"] == "SHORT_ANSWER"
        )
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE ai_summaries SET status='SUPERSEDED' WHERE record_id=:record_id"),
                {"record_id": record_id},
            )
        after_summary_replacement = await client.post(
            f"/api/records/{record_id}/quizzes/{active_choice['id']}/answers",
            json={"answer": 0},
        )
        short_answer = await client.post(
            f"/api/records/{record_id}/quizzes/{active_short['id']}/answers",
            json={"answer": 0},
        )

    assert draft_answer.status_code == 409
    assert superseded_answer.status_code == 409
    assert after_summary_replacement.status_code == 200
    assert after_summary_replacement.json()["answer_result"] == "CORRECT"
    assert short_answer.status_code == 409


@pytest.mark.anyio
async def test_objective_answer_and_event_roll_back_together(tmp_path: Path) -> None:
    model = FakeQuizModel()
    async with running_quiz_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id, _summary_id = await create_completed_record(app, client)
        await configure_llm(client)
        await grant_llm_consent(client)
        batch_id, draft = await generate_draft_batch(client, record_id)
        await client.post(f"/api/records/{record_id}/quiz-batches/{batch_id}/confirmations")
        items = cast(list[dict[str, object]], draft["items"])
        choice = next(item for item in items if item["question_type"] == "MULTIPLE_CHOICE")
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "CREATE TRIGGER reject_quiz_answer_event BEFORE INSERT ON learning_events "
                    "WHEN NEW.event_type='QUIZ_ANSWERED' BEGIN "
                    "SELECT RAISE(ABORT, 'forced event failure'); END"
                )
            )

        failed = await client.post(
            f"/api/records/{record_id}/quizzes/{choice['id']}/answers",
            json={"answer": 0},
        )
        async with app.state.session_factory() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT user_answer_json, answer_result, answered_at FROM quizzes "
                        "WHERE id=:quiz_id"
                    ),
                    {"quiz_id": choice["id"]},
                )
            ).one()
            event_count = await session.scalar(
                text("SELECT count(*) FROM learning_events WHERE idempotency_key=:idempotency_key"),
                {"idempotency_key": f"quiz-answered:{choice['id']}"},
            )

    assert failed.status_code == 500
    assert tuple(row) == (None, None, None)
    assert event_count == 0
