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

from app.db.migrations import run_migrations
from app.main import create_app
from app.modules.llm.service import ReviewMaterialModel, ReviewMaterialModelResult
from app.modules.review_material.schemas import ReviewMaterialContent
from app.modules.review_material.worker import (
    MODEL_INPUT_TOKEN_BUDGET,
    choose_generation_mode,
    estimate_tokens,
)
from app.shared.prompts import CONTENT_LANGUAGE_INSTRUCTION

TOKEN = "test-launch-token"


class FakeReviewMaterialModel:
    def __init__(self, output: object) -> None:
        self.output = output
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
    ) -> ReviewMaterialModelResult:
        assert base_url == "https://example.com/v1"
        assert api_key == "sk-test"
        assert model == "qwen-plus"
        self.prompts.append(prompt)
        self.started.set()
        await self.release.wait()
        return ReviewMaterialModelResult(
            output=self.output,
            token_usage={"total_tokens": 77},
        )


def valid_review_material() -> ReviewMaterialContent:
    return ReviewMaterialContent(
        quick_review="## 核心\n\n```python\nprint('hello')\n```",
        key_list=["理解调度目标", "比较不同调度算法"],
        mind_map_markdown="# 进程调度\n## 基础\n- 调度目标\n## 算法\n- 时间片轮转",
    )


@asynccontextmanager
async def running_review_app(
    data_dir: Path,
    model: ReviewMaterialModel,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(
        data_dir=data_dir,
        launch_token=TOKEN,
        review_material_model=model,
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client


async def configure_llm(client: httpx.AsyncClient) -> None:
    configured = await client.put(
        "/api/settings/providers/llm",
        json={
            "base_url": "https://example.com/v1",
            "api_key": "sk-test",
            "model": "qwen-plus",
        },
    )
    assert configured.status_code == 200
    consented = await client.post("/api/settings/external-processing-consents/llm")
    assert consented.status_code == 200


async def create_completed_record(app: FastAPI, client: httpx.AsyncClient) -> str:
    course_response = await client.post(
        "/api/courses",
        json={
            "name": "操作系统",
            "learning_context": "SCHOOL",
            "education_stage": "UNDERGRADUATE",
        },
    )
    course_id = cast(str, course_response.json()["id"])
    record_id = "11111111-1111-4111-8111-111111111111"
    summary_id = "33333333-3333-4333-8333-333333333333"
    now = "2026-09-06T12:00:00.000000Z"
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO records "
                "(id, course_id, capture_type, title, status, duration_ms, "
                "summary_confirmed_at, created_at, updated_at, deleted_at) "
                "VALUES (:id, :course_id, 'DOCUMENT_IMPORT', '进程调度', 'COMPLETED', "
                "0, :now, :now, :now, NULL)"
            ),
            {"id": record_id, "course_id": course_id, "now": now},
        )
        await session.execute(
            text(
                "INSERT INTO transcripts "
                "(id, record_id, language, content, source_version, edited_by_user, "
                "created_at, updated_at, deleted_at) VALUES "
                "('22222222-2222-4222-8222-222222222222', :record_id, 'zh-CN', "
                ":content, 1, 0, :now, :now, NULL)"
            ),
            {
                "record_id": record_id,
                "content": "原文唯一标记：时间片轮转覆盖全文。",
                "now": now,
            },
        )
        await session.execute(
            text(
                "INSERT INTO ai_summaries "
                "(id, record_id, version_no, transcript_source_version, topic, abstract, "
                "summary_json, status, model, prompt_version, token_usage_json, latency_ms, "
                "user_feedback, confirmed_at, created_at, updated_at, deleted_at) VALUES "
                "(:id, :record_id, 1, 1, '进程调度', :abstract, :summary_json, "
                "'CONFIRMED', 'qwen-plus', 'summary-v1', '{}', 1, NULL, :now, :now, :now, NULL)"
            ),
            {
                "id": summary_id,
                "record_id": record_id,
                "abstract": "已确认总结唯一标记：关注公平性。" * 20,
                "summary_json": json.dumps(
                    {"sections": [{"heading": "算法", "points": ["轮转算法"]}]},
                    ensure_ascii=False,
                ),
                "now": now,
            },
        )
        await session.execute(
            text(
                "INSERT INTO knowledge_points "
                "(id, record_id, batch_id, name, detail, tags, importance, "
                "generated_from_summary_id, generation_status, source_anchor_id, "
                "created_at, updated_at, deleted_at) VALUES "
                "('44444444-4444-4444-8444-444444444444', :record_id, NULL, "
                "'KP', '绝不能进入复习资料上下文', '[]', 5, :summary_id, 'ACTIVE', "
                "NULL, :now, :now, NULL)"
            ),
            {
                "record_id": record_id,
                "summary_id": summary_id,
                "now": now,
            },
        )
    return record_id


async def wait_for_review_material(
    client: httpx.AsyncClient,
    record_id: str,
) -> dict[str, object]:
    for _ in range(200):
        response = await client.get(f"/api/records/{record_id}/review-material")
        payload = cast(dict[str, object], response.json())
        material = payload.get("review_material")
        if isinstance(material, dict):
            return cast(dict[str, object], material)
        await asyncio.sleep(0.02)
    pytest.fail("复习资料未完成生成")


async def wait_for_review_job(
    client: httpx.AsyncClient,
    record_id: str,
    status: str,
) -> dict[str, object]:
    for _ in range(200):
        payload = cast(
            dict[str, object], (await client.get(f"/api/records/{record_id}/jobs")).json()
        )
        jobs = cast(list[dict[str, object]], payload["jobs"])
        match = next(
            (
                job
                for job in jobs
                if job["job_type"] == "REVIEW_MATERIAL_GENERATION" and job["status"] == status
            ),
            None,
        )
        if match is not None:
            return match
        await asyncio.sleep(0.02)
    pytest.fail(f"复习资料任务未进入 {status}")


@pytest.mark.anyio
async def test_migration_0017_adds_review_materials_and_single_active_job(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "review-materials.db"
    await run_migrations(db_path)

    async with aiosqlite.connect(db_path) as connection:
        version = await (await connection.execute("PRAGMA user_version")).fetchone()
        columns = {
            cast(str, row[1])
            for row in await (
                await connection.execute("PRAGMA table_info(review_materials)")
            ).fetchall()
        }
        foreign_keys = await (
            await connection.execute("PRAGMA foreign_key_list(review_materials)")
        ).fetchall()
        indexes = {
            cast(str, row[1])
            for row in await (
                await connection.execute("PRAGMA index_list(processing_jobs)")
            ).fetchall()
        }
        job_sql_row = await (
            await connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='processing_jobs'"
            )
        ).fetchone()

    assert version == (24,)
    assert columns == {
        "id",
        "record_id",
        "version_no",
        "transcript_source_version",
        "generated_from_summary_id",
        "quick_review",
        "key_list_json",
        "mind_map_markdown",
        "status",
        "model",
        "prompt_version",
        "user_feedback",
        "token_usage_json",
        "latency_ms",
        "confirmed_at",
        "created_at",
        "updated_at",
        "deleted_at",
    }
    assert any(row[2] == "records" and row[6] == "CASCADE" for row in foreign_keys)
    assert any(
        row[2] == "ai_summaries" and row[3] == "generated_from_summary_id" and row[6] == "SET NULL"
        for row in foreign_keys
    )
    assert "idx_processing_jobs_one_active_review_material_generation" in indexes
    assert job_sql_row is not None
    assert "REVIEW_MATERIAL_GENERATION" in cast(str, job_sql_row[0])


@pytest.mark.parametrize(
    ("text", "token_budget", "expected"),
    [
        ("", 0, "single"),
        ("复" * 10, 10, "single"),
        ("复" * 11, 10, "map_reduce"),
        ("，" * 11, 10, "map_reduce"),
    ],
)
def test_generation_mode_respects_exact_token_budget(
    text: str,
    token_budget: int,
    expected: str,
) -> None:
    assert choose_generation_mode(text, token_budget=token_budget) == expected


@pytest.mark.anyio
async def test_first_generation_is_single_active_and_readable(tmp_path: Path) -> None:
    model = FakeReviewMaterialModel(valid_review_material())
    model.release.clear()
    async with running_review_app(tmp_path / "KnowRealm", model) as (app, client):
        await configure_llm(client)
        record_id = await create_completed_record(app, client)

        accepted = await client.post(f"/api/records/{record_id}/review-material-jobs")
        assert accepted.status_code == 202
        await asyncio.wait_for(model.started.wait(), timeout=2)

        duplicate = await client.post(f"/api/records/{record_id}/review-material-jobs")
        assert duplicate.status_code == 409

        model.release.set()
        material = await wait_for_review_material(client, record_id)

        assert material["version_no"] == 1
        assert (
            await client.post(f"/api/records/{record_id}/review-material-jobs")
        ).status_code == 409
        assert material["status"] == "GENERATED"
        assert material["quick_review"] == valid_review_material().quick_review
        assert material["key_list"] == valid_review_material().key_list
        assert material["mind_map_markdown"] == valid_review_material().mind_map_markdown
        assert material["generated_from_summary_id"] == "33333333-3333-4333-8333-333333333333"
        assert "原文唯一标记" in model.prompts[0]
        assert "已确认总结唯一标记" in model.prompts[0]
        assert "绝不能进入复习资料上下文" not in model.prompts[0]
        assert CONTENT_LANGUAGE_INSTRUCTION in model.prompts[0]

        async with aiosqlite.connect(tmp_path / "KnowRealm" / "knowrealm.db") as connection:
            row = await (
                await connection.execute(
                    "SELECT model, prompt_version, token_usage_json, latency_ms "
                    "FROM review_materials WHERE record_id = ?",
                    (record_id,),
                )
            ).fetchone()
        assert row is not None
        assert row[0] == "qwen-plus"
        assert row[1] == "review_v1"
        assert json.loads(cast(str, row[2])) == {"total_tokens": 77}
        assert cast(int, row[3]) >= 0


@pytest.mark.anyio
async def test_submit_prerequisite_matrix_rejects_without_creating_jobs(tmp_path: Path) -> None:
    model = FakeReviewMaterialModel(valid_review_material())
    async with running_review_app(tmp_path / "KnowRealm", model) as (app, client):
        record_id = await create_completed_record(app, client)

        missing_provider = await client.post(f"/api/records/{record_id}/review-material-jobs")
        assert missing_provider.status_code == 409

        configured = await client.put(
            "/api/settings/providers/llm",
            json={
                "base_url": "https://example.com/v1",
                "api_key": "sk-test",
                "model": "qwen-plus",
            },
        )
        assert configured.status_code == 200
        missing_consent = await client.post(f"/api/records/{record_id}/review-material-jobs")
        assert missing_consent.status_code == 409
        assert (
            await client.post("/api/settings/external-processing-consents/llm")
        ).status_code == 200

        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE ai_summaries SET status='SUPERSEDED' WHERE record_id=:record_id"),
                {"record_id": record_id},
            )
        missing_summary = await client.post(f"/api/records/{record_id}/review-material-jobs")
        assert missing_summary.status_code == 409

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
        archived_course = await client.post(f"/api/records/{record_id}/review-material-jobs")
        assert archived_course.status_code == 409

        async with aiosqlite.connect(tmp_path / "KnowRealm" / "knowrealm.db") as connection:
            count = await (
                await connection.execute(
                    "SELECT count(*) FROM processing_jobs "
                    "WHERE job_type='REVIEW_MATERIAL_GENERATION'"
                )
            ).fetchone()
        assert count == (0,)


@pytest.mark.anyio
async def test_publish_recheck_cancels_stale_result(tmp_path: Path) -> None:
    model = FakeReviewMaterialModel(valid_review_material())
    model.release.clear()
    async with running_review_app(tmp_path / "KnowRealm", model) as (app, client):
        await configure_llm(client)
        record_id = await create_completed_record(app, client)
        accepted = await client.post(f"/api/records/{record_id}/review-material-jobs")
        assert accepted.status_code == 202
        await asyncio.wait_for(model.started.wait(), timeout=2)

        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE transcripts SET source_version=2 WHERE record_id=:record_id"),
                {"record_id": record_id},
            )
        model.release.set()

        cancelled = await wait_for_review_job(client, record_id, "CANCELLED")
        assert cancelled["error_code"] is None
        payload = cast(
            dict[str, object],
            (await client.get(f"/api/records/{record_id}/review-material")).json(),
        )
        assert payload["review_material"] is None


@pytest.mark.anyio
async def test_invalid_output_fails_without_writing_material(tmp_path: Path) -> None:
    model = FakeReviewMaterialModel(
        {
            "quick_review": "合法速记",
            "key_list": ["合法重点"],
            "mind_map_markdown": "```text\n禁止代码块\n```",
        }
    )
    async with running_review_app(tmp_path / "KnowRealm", model) as (app, client):
        await configure_llm(client)
        record_id = await create_completed_record(app, client)
        assert (
            await client.post(f"/api/records/{record_id}/review-material-jobs")
        ).status_code == 202

        failed = await wait_for_review_job(client, record_id, "FAILED")
        assert failed["error_code"] == "LLM_OUTPUT_INVALID"
        read_out = cast(
            dict[str, object],
            (await client.get(f"/api/records/{record_id}/review-material")).json(),
        )
        assert read_out["review_material"] is None
        assert read_out["action_required"] == "RETRY"


@pytest.mark.anyio
async def test_long_source_uses_map_reduce_without_omitting_tail(tmp_path: Path) -> None:
    model = FakeReviewMaterialModel(valid_review_material())
    async with running_review_app(tmp_path / "KnowRealm", model) as (app, client):
        await configure_llm(client)
        record_id = await create_completed_record(app, client)
        long_source = "开头标记" + ("复" * 108_100) + "尾段标记"
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE transcripts SET content=:content WHERE record_id=:record_id"),
                {"content": long_source, "record_id": record_id},
            )

        assert (
            await client.post(f"/api/records/{record_id}/review-material-jobs")
        ).status_code == 202
        await wait_for_review_material(client, record_id)

        assert len(model.prompts) >= 3
        assert any("开头标记" in prompt for prompt in model.prompts)
        assert any("尾段标记" in prompt for prompt in model.prompts)
        assert "归并" in model.prompts[-1]
        assert all(CONTENT_LANGUAGE_INSTRUCTION in prompt for prompt in model.prompts)
        assert all(estimate_tokens(prompt) <= MODEL_INPUT_TOKEN_BUDGET for prompt in model.prompts)


@pytest.mark.anyio
async def test_map_reduce_converges_with_largest_valid_partial_results(
    tmp_path: Path,
) -> None:
    rich_result = ReviewMaterialContent(
        quick_review="复" * 5_000,
        key_list=["复" * 80 for _ in range(50)],
        mind_map_markdown="\n".join(["# 复习"] + ["- " + ("复" * 400) for _ in range(12)]),
    )
    model = FakeReviewMaterialModel(rich_result)
    async with running_review_app(tmp_path / "KnowRealm", model) as (app, client):
        await configure_llm(client)
        record_id = await create_completed_record(app, client)
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE transcripts SET content=:content WHERE record_id=:record_id"),
                {"content": "复" * 108_100, "record_id": record_id},
            )

        assert (
            await client.post(f"/api/records/{record_id}/review-material-jobs")
        ).status_code == 202
        material = await wait_for_review_material(client, record_id)

        assert material["quick_review"] == rich_result.quick_review
        assert len(model.prompts) == 3


@pytest.mark.anyio
async def test_record_soft_delete_cascades_review_material(tmp_path: Path) -> None:
    model = FakeReviewMaterialModel(valid_review_material())
    async with running_review_app(tmp_path / "KnowRealm", model) as (app, client):
        await configure_llm(client)
        record_id = await create_completed_record(app, client)
        assert (
            await client.post(f"/api/records/{record_id}/review-material-jobs")
        ).status_code == 202
        await wait_for_review_material(client, record_id)

        deleted = await client.delete(f"/api/records/{record_id}")
        assert deleted.status_code == 204

        async with aiosqlite.connect(tmp_path / "KnowRealm" / "knowrealm.db") as connection:
            row = await (
                await connection.execute(
                    "SELECT deleted_at FROM review_materials WHERE record_id=?",
                    (record_id,),
                )
            ).fetchone()
        assert row is not None and row[0] is not None


async def list_review_versions(
    client: httpx.AsyncClient, record_id: str
) -> list[dict[str, object]]:
    return cast(
        list[dict[str, object]],
        (await client.get(f"/api/records/{record_id}/review-materials")).json(),
    )


@pytest.mark.anyio
async def test_adjust_creates_new_version_and_supersedes_previous(tmp_path: Path) -> None:
    model = FakeReviewMaterialModel(valid_review_material())
    async with running_review_app(tmp_path / "KnowRealm", model) as (app, client):
        await configure_llm(client)
        record_id = await create_completed_record(app, client)
        assert (
            await client.post(f"/api/records/{record_id}/review-material-jobs")
        ).status_code == 202
        await wait_for_review_material(client, record_id)

        accepted = await client.post(
            f"/api/records/{record_id}/review-material-adjustments",
            json={"feedback": "更简洁"},
        )
        assert accepted.status_code == 202
        # one-active：调整任务存在期间再次提交被拒
        duplicate = await client.post(
            f"/api/records/{record_id}/review-material-adjustments",
            json={"feedback": "再改一版"},
        )
        assert duplicate.status_code == 409

        v2 = await wait_for_review_material(client, record_id)
        assert v2["version_no"] == 2
        assert v2["status"] == "GENERATED"
        assert v2["user_feedback"] == "更简洁"
        assert v2["prompt_version"] == "review_adjust_v1"

        versions = await list_review_versions(client, record_id)
        assert [version["version_no"] for version in versions] == [2, 1]
        assert [version["status"] for version in versions] == ["GENERATED", "SUPERSEDED"]

        # 调整 prompt 携带上一版内容与用户反馈，且仍以原文为主要依据
        adjust_prompt = model.prompts[-1]
        assert "更简洁" in adjust_prompt
        assert "上一版复习资料" in adjust_prompt
        assert valid_review_material().quick_review in adjust_prompt
        assert "原文唯一标记" in adjust_prompt

        # 对 CONFIRMED 版本再调整走同一流程
        confirmed = await client.post(f"/api/records/{record_id}/review-material-confirmations")
        assert confirmed.status_code == 200
        assert (
            await client.post(
                f"/api/records/{record_id}/review-material-adjustments",
                json={"feedback": "再聚焦调度算法"},
            )
        ).status_code == 202
        v3 = await wait_for_review_material(client, record_id)
        assert v3["version_no"] == 3
        assert v3["status"] == "GENERATED"
        versions = await list_review_versions(client, record_id)
        assert [version["status"] for version in versions] == [
            "GENERATED",
            "SUPERSEDED",
            "SUPERSEDED",
        ]


@pytest.mark.anyio
async def test_confirm_idempotent_and_edit_updates_in_place(tmp_path: Path) -> None:
    model = FakeReviewMaterialModel(valid_review_material())
    async with running_review_app(tmp_path / "KnowRealm", model) as (app, client):
        await configure_llm(client)
        record_id = await create_completed_record(app, client)
        assert (
            await client.post(f"/api/records/{record_id}/review-material-jobs")
        ).status_code == 202
        await wait_for_review_material(client, record_id)

        # 手动编辑 GENERATED 版本：就地生效、不换代、不迁移状态
        patched = await client.patch(
            f"/api/records/{record_id}/review-material",
            json={
                "quick_review": "## 手改速记\n- 我自己写的",
                "key_list": ["手改重点一", "手改重点二"],
                "mind_map_markdown": "# 手改大纲\n- 新条目",
            },
        )
        assert patched.status_code == 200
        edited = cast(dict[str, object], patched.json())
        assert edited["version_no"] == 1
        assert edited["status"] == "GENERATED"
        assert edited["quick_review"] == "## 手改速记\n- 我自己写的"
        assert edited["key_list"] == ["手改重点一", "手改重点二"]

        # 违规内容（大纲带代码块）整体拒绝，内容不变
        invalid = await client.patch(
            f"/api/records/{record_id}/review-material",
            json={
                "quick_review": "合法速记",
                "key_list": ["合法重点"],
                "mind_map_markdown": "```text\n禁止代码块\n```",
            },
        )
        assert invalid.status_code == 422

        first = await client.post(f"/api/records/{record_id}/review-material-confirmations")
        assert first.status_code == 200
        confirmed = cast(dict[str, object], first.json())
        assert confirmed["status"] == "CONFIRMED"
        # 幂等：重复确认返回现状
        second = await client.post(f"/api/records/{record_id}/review-material-confirmations")
        assert second.status_code == 200
        assert cast(dict[str, object], second.json())["id"] == confirmed["id"]

        # 编辑 CONFIRMED 版本无需重新确认：状态与 confirmed_at 不变（导出前置语义不变）
        patched_again = await client.patch(
            f"/api/records/{record_id}/review-material",
            json={
                "quick_review": "## 定版后微调",
                "key_list": ["定版重点"],
                "mind_map_markdown": "# 定版大纲\n- 微调",
            },
        )
        assert patched_again.status_code == 200
        final = cast(dict[str, object], patched_again.json())
        assert final["status"] == "CONFIRMED"
        assert final["version_no"] == 1
        assert final["quick_review"] == "## 定版后微调"
        async with aiosqlite.connect(tmp_path / "KnowRealm" / "knowrealm.db") as connection:
            row = await (
                await connection.execute(
                    "SELECT confirmed_at, updated_at, created_at FROM review_materials "
                    "WHERE record_id=?",
                    (record_id,),
                )
            ).fetchone()
        assert row is not None and row[0] is not None
        assert row[1] > row[2]
        versions = await list_review_versions(client, record_id)
        assert len(versions) == 1


@pytest.mark.anyio
async def test_adjust_rejects_invalid_feedback_and_superseded_current(tmp_path: Path) -> None:
    model = FakeReviewMaterialModel(valid_review_material())
    async with running_review_app(tmp_path / "KnowRealm", model) as (app, client):
        await configure_llm(client)
        record_id = await create_completed_record(app, client)

        missing = await client.post(
            f"/api/records/{record_id}/review-material-adjustments",
            json={"feedback": "更简洁"},
        )
        assert missing.status_code == 404
        assert (
            await client.post(
                f"/api/records/{record_id}/review-material-adjustments",
                json={"feedback": "  "},
            )
        ).status_code == 422
        assert (
            await client.post(
                f"/api/records/{record_id}/review-material-adjustments",
                json={"feedback": "长" * 1001},
            )
        ).status_code == 422

        assert (
            await client.post(f"/api/records/{record_id}/review-material-jobs")
        ).status_code == 202
        await wait_for_review_material(client, record_id)
        # 当前版本已退场（模拟换代竞态后的提交）
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE review_materials SET status='SUPERSEDED' WHERE record_id=:record_id"),
                {"record_id": record_id},
            )
        superseded = await client.post(
            f"/api/records/{record_id}/review-material-adjustments",
            json={"feedback": "更简洁"},
        )
        assert superseded.status_code == 409


@pytest.mark.anyio
async def test_adjust_job_cancelled_when_transcript_changes_after_submit(tmp_path: Path) -> None:
    model = FakeReviewMaterialModel(valid_review_material())
    async with running_review_app(tmp_path / "KnowRealm", model) as (app, client):
        await configure_llm(client)
        record_id = await create_completed_record(app, client)
        assert (
            await client.post(f"/api/records/{record_id}/review-material-jobs")
        ).status_code == 202
        await wait_for_review_material(client, record_id)

        assert (
            await client.post(
                f"/api/records/{record_id}/review-material-adjustments",
                json={"feedback": "更简洁"},
            )
        ).status_code == 202
        # 提交后转写变更：任务被两阶段复核拒绝，旧资料保持现状
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE transcripts SET source_version=2 WHERE record_id=:record_id"),
                {"record_id": record_id},
            )

        await wait_for_review_job(client, record_id, "CANCELLED")
        payload = cast(
            dict[str, object],
            (await client.get(f"/api/records/{record_id}/review-material")).json(),
        )
        current = cast(dict[str, object], payload["review_material"])
        assert current["version_no"] == 1
        assert payload["transcript_stale"] is True


@pytest.mark.anyio
async def test_transcript_update_marks_stale_and_regenerates_via_adjust(tmp_path: Path) -> None:
    model = FakeReviewMaterialModel(valid_review_material())
    async with running_review_app(tmp_path / "KnowRealm", model) as (app, client):
        await configure_llm(client)
        record_id = await create_completed_record(app, client)
        assert (
            await client.post(f"/api/records/{record_id}/review-material-jobs")
        ).status_code == 202
        await wait_for_review_material(client, record_id)

        payload = cast(
            dict[str, object],
            (await client.get(f"/api/records/{record_id}/review-material")).json(),
        )
        assert payload["transcript_stale"] is False

        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE transcripts SET source_version=2 WHERE record_id=:record_id"),
                {"record_id": record_id},
            )
        payload = cast(
            dict[str, object],
            (await client.get(f"/api/records/{record_id}/review-material")).json(),
        )
        assert payload["transcript_stale"] is True
        # 旧内容不删不覆盖
        current = cast(dict[str, object], payload["review_material"])
        assert current["quick_review"] == valid_review_material().quick_review

        # 转写更新后的重新生成走反馈调整：新版本绑定新转写，过时标记解除
        assert (
            await client.post(
                f"/api/records/{record_id}/review-material-adjustments",
                json={"feedback": "基于更新后的转写重新生成"},
            )
        ).status_code == 202
        regenerated = await wait_for_review_material(client, record_id)
        assert regenerated["version_no"] == 2
        assert regenerated["transcript_source_version"] == 2
        payload = cast(
            dict[str, object],
            (await client.get(f"/api/records/{record_id}/review-material")).json(),
        )
        assert payload["transcript_stale"] is False
