import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.main import create_app
from app.modules.llm.service import SummaryModel, SummaryModelResult
from app.modules.summary.schemas import SummaryContent, SummarySection

TOKEN = "test-launch-token"


class FakeSummaryModel:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def generate(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
    ) -> SummaryModelResult:
        self.prompts.append(prompt)
        return SummaryModelResult(
            output=SummaryContent(
                topic="归类升级主题",
                abstract="用于验证归类与升级入队的合成摘要。" * 30,
                sections=[
                    SummarySection(heading="核心内容", points=["合成要点，不依赖真实供应商。"])
                ],
            ),
            token_usage={"total_tokens": 1},
        )


@asynccontextmanager
async def running_app(
    data_dir: Path,
    *,
    summary_model: SummaryModel | None = None,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient], None]:
    app = create_app(
        data_dir=data_dir,
        launch_token=TOKEN,
        summary_model=summary_model,
    )
    app.exception_handlers.pop(Exception, None)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client


async def create_course(client: httpx.AsyncClient, name: str = "归类课程") -> str:
    response = await client.post(
        "/api/courses",
        json={"name": name, "learning_context": "INTEREST", "depth": "BEGINNER"},
    )
    assert response.status_code == 201
    return cast(str, response.json()["id"])


async def configure_llm(client: httpx.AsyncClient) -> None:
    provider = await client.put(
        "/api/settings/providers/llm",
        json={
            "base_url": "https://example.com/v1",
            "api_key": "sk-test",
            "model": "qwen-plus",
        },
    )
    assert provider.status_code == 200
    consent = await client.post("/api/settings/external-processing-consents/llm")
    assert consent.status_code == 200


async def create_note(
    client: httpx.AsyncClient,
    content: str,
) -> str:
    response = await client.post(
        "/api/text-captures",
        json={"capture_type": "QUICK_NOTE", "content": content},
    )
    assert response.status_code == 201
    return cast(str, response.json()["record_id"])


async def set_record_status(
    app: FastAPI,
    record_id: str,
    status: str,
) -> None:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text("UPDATE records SET status = :status WHERE id = :id"),
            {"status": status, "id": record_id},
        )


async def insert_pending_summary_job(
    app: FastAPI,
    record_id: str,
    *,
    status: str = "PENDING",
) -> str:
    async with app.state.session_factory() as session, session.begin():
        await session.execute(
            text(
                "INSERT INTO processing_jobs "
                "(id, record_id, job_type, status, progress, attempts, max_attempts,"
                " next_run_at, waiting_reason, input_json, created_at, updated_at)"
                " VALUES (hex(randomblob(16)), :record_id, 'SUMMARY', :status, 0, 0, 1,"
                " NULL, NULL, '{}', strftime('%Y-%m-%dT%H:%M:%fZ','now'),"
                " strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
            ),
            {"record_id": record_id, "status": status},
        )
        job_id = await session.scalar(
            text("SELECT id FROM processing_jobs WHERE record_id = :record_id"),
            {"record_id": record_id},
        )
    return cast(str, job_id)


async def row_value(
    app: FastAPI,
    query: str,
    record_id: str,
) -> object:
    async with app.state.session_factory() as session:
        return cast(object, await session.scalar(text(query), {"id": record_id}))


async def classify(
    client: httpx.AsyncClient,
    record_id: str,
    course_id: str,
) -> httpx.Response:
    return await client.post(
        f"/api/records/{record_id}/classification",
        json={"course_id": course_id},
    )


async def upgrade(
    client: httpx.AsyncClient,
    record_id: str,
    course_id: str | None = None,
) -> httpx.Response:
    return await client.post(
        f"/api/records/{record_id}/upgrade",
        json=({"course_id": course_id} if course_id is not None else {}),
    )


async def wait_for_status(
    client: httpx.AsyncClient,
    record_id: str,
    status: str,
) -> None:
    for _ in range(250):
        current = cast(str, (await client.get(f"/api/records/{record_id}")).json()["status"])
        if current == status:
            return
        await asyncio.sleep(0.02)
    pytest.fail(f"Record 未进入 {status}")


@pytest.mark.anyio
async def test_classification_moves_note_to_active_course_without_any_ai_side_effect(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    fake = FakeSummaryModel()
    async with running_app(data_dir, summary_model=fake) as (app, client):
        record_id = await create_note(client, "归类标题\n\n归类正文")
        course_id = await create_course(client)
        await configure_llm(client)
        before = (await client.get(f"/api/records/{record_id}")).json()
        response = await classify(client, record_id, course_id)
        after = response.json()
        job_count = await row_value(
            app, "SELECT count(*) FROM processing_jobs WHERE record_id = :id", record_id
        )
        event_count = await row_value(app, "SELECT count(*) FROM learning_events", record_id)
        summary_state = (await client.get(f"/api/records/{record_id}/summary")).json()

    assert response.status_code == 200
    assert after["course_id"] == course_id
    assert after["status"] == "NOTE"
    assert after["title"] == before["title"] == "归类标题"
    assert after["capture_type"] == before["capture_type"]
    assert job_count == 0
    assert event_count == 0
    assert fake.prompts == []
    # 纯归类后 Summary 页进入可生成状态，但没有任何活动 Job。
    assert summary_state["action_required"] == "GENERATE"
    assert summary_state["active_job_id"] is None


@pytest.mark.anyio
async def test_classification_is_idempotent_for_same_course_and_conflicts_across_courses(
    tmp_path: Path,
) -> None:
    async with running_app(tmp_path / "KnowRealm") as (_app, client):
        record_id = await create_note(client, "幂等归类")
        first_course = await create_course(client, "第一门")
        second_course = await create_course(client, "第二门")
        first = await classify(client, record_id, first_course)
        repeat = await classify(client, record_id, first_course)
        conflict = await classify(client, record_id, second_course)

    assert first.status_code == 200
    assert repeat.status_code == 200
    assert repeat.json()["course_id"] == first_course
    assert repeat.json()["updated_at"] == first.json()["updated_at"]
    assert conflict.status_code == 409
    assert "已归到其他课程" in conflict.json()["detail"]


@pytest.mark.anyio
@pytest.mark.parametrize("status", ["CONTENT_PROCESSING", "FAILED"])
async def test_classification_rejects_non_classifiable_statuses(
    tmp_path: Path,
    status: str,
) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        record_id = await create_note(client, "不可归类")
        await set_record_status(app, record_id, status)
        course_id = await create_course(client)
        response = await classify(client, record_id, course_id)
        course_id_after = await row_value(
            app, "SELECT course_id FROM records WHERE id = :id", record_id
        )

    assert response.status_code == 409
    assert "不能归类" in response.json()["detail"]
    assert course_id_after is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("course_state", "expected_status"),
    [("missing", 404), ("archived", 409)],
)
async def test_classification_validates_course_state(
    tmp_path: Path,
    course_state: str,
    expected_status: int,
) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        record_id = await create_note(client, "课程校验")
        course_id = await create_course(client)
        if course_state == "archived":
            async with app.state.session_factory() as session, session.begin():
                await session.execute(
                    text("UPDATE courses SET status = 'ARCHIVED' WHERE id = :id"),
                    {"id": course_id},
                )
        if course_state == "missing":
            course_id = "99999999-9999-4999-8999-999999999999"
        response = await classify(client, record_id, course_id)
        course_id_after = await row_value(
            app, "SELECT course_id FROM records WHERE id = :id", record_id
        )

    assert response.status_code == expected_status
    assert course_id_after is None


@pytest.mark.anyio
@pytest.mark.parametrize("record_state", ["missing", "deleted", "parent_deleted"])
async def test_classification_follows_existing_record_404_semantics(
    tmp_path: Path,
    record_state: str,
) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        record_id = await create_note(client, "404 语义")
        course_id = await create_course(client)
        if record_state == "missing":
            record_id = "99999999-9999-4999-8999-999999999999"
        elif record_state == "deleted":
            await client.delete(f"/api/records/{record_id}")
        else:
            async with app.state.session_factory() as session, session.begin():
                await session.execute(
                    text("UPDATE records SET course_id = :course_id WHERE id = :id"),
                    {"course_id": course_id, "id": record_id},
                )
                await session.execute(
                    text("UPDATE courses SET deleted_at = '2026-08-27T00:00:00Z' WHERE id = :id"),
                    {"id": course_id},
                )
        response = await classify(client, record_id, course_id)

    assert response.status_code == 404
    assert response.json()["detail"] == "学习记录不存在或已删除"


@pytest.mark.anyio
async def test_classification_requires_launch_token(tmp_path: Path) -> None:
    async with running_app(tmp_path / "KnowRealm") as (_app, client):
        client.headers.pop("X-KnowRealm-Token")
        response = await client.post(
            "/api/records/99999999-9999-4999-8999-999999999999/classification",
            json={"course_id": "99999999-9999-4999-8999-999999999999"},
        )

    assert response.status_code == 403


@pytest.mark.anyio
async def test_upgrade_requires_course_for_unclassified_record(tmp_path: Path) -> None:
    async with running_app(tmp_path / "KnowRealm") as (_app, client):
        record_id = await create_note(client, "未选课升级")
        response = await upgrade(client, record_id)

    assert response.status_code == 422
    assert "UPGRADE_COURSE_REQUIRED" in response.json()["detail"]


@pytest.mark.anyio
async def test_upgrade_of_note_advances_to_summary_pending_and_enqueues_single_job(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    fake = FakeSummaryModel()
    async with running_app(data_dir, summary_model=fake) as (app, client):
        record_id = await create_note(client, "升级标题\n升级正文")
        course_id = await create_course(client)
        await configure_llm(client)
        response = await upgrade(client, record_id, course_id)
        accepted = response.json()
        await wait_for_status(client, record_id, "SUMMARY_READY")
        job_count = await row_value(
            app, "SELECT count(*) FROM processing_jobs WHERE record_id = :id", record_id
        )
        final_status = await row_value(app, "SELECT status FROM records WHERE id = :id", record_id)

    assert response.status_code == 200
    assert accepted["record"]["course_id"] == course_id
    assert accepted["record"]["status"] == "SUMMARY_PENDING"
    assert accepted["summary_job_id"] is not None
    assert len(fake.prompts) == 1
    assert job_count == 1
    assert final_status == "SUMMARY_READY"


@pytest.mark.anyio
async def test_upgrade_without_provider_keeps_local_facts_and_returns_null_job(
    tmp_path: Path,
) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        record_id = await create_note(client, "无 Provider 升级")
        course_id = await create_course(client)
        response = await upgrade(client, record_id, course_id)
        accepted = response.json()
        job_count = await row_value(
            app, "SELECT count(*) FROM processing_jobs WHERE record_id = :id", record_id
        )
        stored_course = await row_value(
            app, "SELECT course_id FROM records WHERE id = :id", record_id
        )
        stored_status = await row_value(app, "SELECT status FROM records WHERE id = :id", record_id)

    assert response.status_code == 200
    assert accepted["summary_job_id"] is None
    assert accepted["record"]["status"] == "SUMMARY_PENDING"
    assert job_count == 0
    assert stored_course == course_id
    assert stored_status == "SUMMARY_PENDING"


@pytest.mark.anyio
async def test_upgrade_of_summary_pending_keeps_status_and_enqueues(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    fake = FakeSummaryModel()
    async with running_app(data_dir, summary_model=fake) as (app, client):
        record_id = await create_note(client, "待总结升级")
        course_id = await create_course(client)
        await set_record_status(app, record_id, "SUMMARY_PENDING")
        await configure_llm(client)
        response = await upgrade(client, record_id, course_id)
        accepted = response.json()
        await wait_for_status(client, record_id, "SUMMARY_READY")

    assert response.status_code == 200
    assert accepted["record"]["status"] == "SUMMARY_PENDING"
    assert accepted["summary_job_id"] is not None
    assert len(fake.prompts) == 1


@pytest.mark.anyio
async def test_upgrade_of_classified_record_reuses_course_without_body(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    fake = FakeSummaryModel()
    async with running_app(data_dir, summary_model=fake) as (_app, client):
        record_id = await create_note(client, "先归类后升级")
        course_id = await create_course(client)
        assert (await classify(client, record_id, course_id)).status_code == 200
        await configure_llm(client)
        response = await upgrade(client, record_id)
        accepted = response.json()
        await wait_for_status(client, record_id, "SUMMARY_READY")

    assert response.status_code == 200
    assert accepted["record"]["course_id"] == course_id
    assert accepted["record"]["status"] == "SUMMARY_PENDING"
    assert accepted["summary_job_id"] is not None
    assert len(fake.prompts) == 1


@pytest.mark.anyio
async def test_upgrade_reuses_active_summary_job_instead_of_creating_second(
    tmp_path: Path,
) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        record_id = await create_note(client, "复用活动 Job")
        course_id = await create_course(client)
        await set_record_status(app, record_id, "SUMMARY_PENDING")
        existing_job_id = await insert_pending_summary_job(app, record_id)
        first = await upgrade(client, record_id, course_id)
        second = await upgrade(client, record_id)
        job_count = await row_value(
            app, "SELECT count(*) FROM processing_jobs WHERE record_id = :id", record_id
        )

    assert first.status_code == 200
    assert first.json()["summary_job_id"] == existing_job_id
    assert second.status_code == 200
    assert second.json()["summary_job_id"] == existing_job_id
    assert job_count == 1


@pytest.mark.anyio
@pytest.mark.parametrize("status", ["SUMMARY_PROCESSING", "SUMMARY_READY", "COMPLETED"])
async def test_repeat_upgrade_after_later_statuses_returns_current_facts(
    tmp_path: Path,
    status: str,
) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        record_id = await create_note(client, "重复升级")
        course_id = await create_course(client)
        assert (await classify(client, record_id, course_id)).status_code == 200
        await set_record_status(app, record_id, status)
        response = await upgrade(client, record_id, course_id)
        accepted = response.json()
        job_count = await row_value(
            app, "SELECT count(*) FROM processing_jobs WHERE record_id = :id", record_id
        )
        stored_status = await row_value(app, "SELECT status FROM records WHERE id = :id", record_id)

    assert response.status_code == 200
    assert accepted["record"]["status"] == status
    assert accepted["record"]["course_id"] == course_id
    assert accepted["summary_job_id"] is None
    assert job_count == 0
    assert stored_status == status


@pytest.mark.anyio
@pytest.mark.parametrize("status", ["CONTENT_PROCESSING", "FAILED"])
async def test_upgrade_rejects_non_upgradable_statuses(
    tmp_path: Path,
    status: str,
) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        record_id = await create_note(client, "不可升级")
        course_id = await create_course(client)
        await set_record_status(app, record_id, status)
        response = await upgrade(client, record_id, course_id)
        stored_course = await row_value(
            app, "SELECT course_id FROM records WHERE id = :id", record_id
        )

    assert response.status_code == 409
    assert "不能升级" in response.json()["detail"]
    assert stored_course is None


@pytest.mark.anyio
async def test_upgrade_conflicts_when_requesting_different_course(
    tmp_path: Path,
) -> None:
    async with running_app(tmp_path / "KnowRealm") as (_app, client):
        record_id = await create_note(client, "跨课程冲突")
        first_course = await create_course(client, "原课程")
        second_course = await create_course(client, "另一门")
        assert (await classify(client, record_id, first_course)).status_code == 200
        response = await upgrade(client, record_id, second_course)

    assert response.status_code == 409
    assert "已归到其他课程" in response.json()["detail"]


@pytest.mark.anyio
async def test_upgrade_revalidates_active_course_before_enqueue(
    tmp_path: Path,
) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        record_id = await create_note(client, "归档竞态")
        course_id = await create_course(client)
        assert (await classify(client, record_id, course_id)).status_code == 200
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE courses SET status = 'ARCHIVED' WHERE id = :id"),
                {"id": course_id},
            )
        response = await upgrade(client, record_id)
        stored_status = await row_value(app, "SELECT status FROM records WHERE id = :id", record_id)

    assert response.status_code == 409
    assert "归档" in response.json()["detail"]
    assert stored_status == "NOTE"


@pytest.mark.anyio
async def test_upgrade_requires_transcript_before_enqueue(tmp_path: Path) -> None:
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        course_id = await create_course(client)
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO records (id, course_id, capture_type, title, status,"
                    " duration_ms, created_at, updated_at)"
                    " VALUES ('11111111-1111-4111-8111-111111111111', NULL,"
                    " 'AUDIO_IMPORT', '无转写', 'SUMMARY_PENDING', 0,"
                    " strftime('%Y-%m-%dT%H:%M:%fZ','now'),"
                    " strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
                )
            )
        response = await upgrade(client, "11111111-1111-4111-8111-111111111111", course_id)
        stored_course = await row_value(
            app,
            "SELECT course_id FROM records WHERE id = :id",
            "11111111-1111-4111-8111-111111111111",
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Transcript 尚未生成"
    assert stored_course is None


@pytest.mark.anyio
async def test_upgrade_enqueue_failure_keeps_local_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.summary.service import SummaryService

    async def broken_enqueue(*args: object, **kwargs: object) -> None:
        raise RuntimeError("forced enqueue failure")

    monkeypatch.setattr(SummaryService, "enqueue_if_eligible", broken_enqueue)
    async with running_app(tmp_path / "KnowRealm") as (app, client):
        record_id = await create_note(client, "入队异常")
        course_id = await create_course(client)
        response = await upgrade(client, record_id, course_id)
        accepted = response.json()
        stored_course = await row_value(
            app, "SELECT course_id FROM records WHERE id = :id", record_id
        )
        stored_status = await row_value(app, "SELECT status FROM records WHERE id = :id", record_id)

    assert response.status_code == 200
    assert accepted["summary_job_id"] is None
    assert accepted["record"]["status"] == "SUMMARY_PENDING"
    assert stored_course == course_id
    assert stored_status == "SUMMARY_PENDING"


@pytest.mark.anyio
async def test_summary_read_reports_course_required_for_unclassified_record(
    tmp_path: Path,
) -> None:
    async with running_app(tmp_path / "KnowRealm") as (_app, client):
        record_id = await create_note(client, "无课程总结")
        response = await client.get(f"/api/records/{record_id}/summary")

    assert response.status_code == 200
    assert response.json()["blocked_reason"] == "COURSE_REQUIRED"
    assert response.json()["action_required"] == "NONE"


@pytest.mark.anyio
async def test_editing_note_transcript_keeps_note_status_and_title(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    fake = FakeSummaryModel()
    async with running_app(data_dir, summary_model=fake) as (app, client):
        record_id = await create_note(client, "编辑标题\n编辑正文")
        await configure_llm(client)
        response = await client.patch(
            f"/api/records/{record_id}/transcript",
            json={"content": "编辑后的正文", "expected_source_version": 1},
        )
        record = (await client.get(f"/api/records/{record_id}")).json()
        transcript = response.json()
        job_count = await row_value(
            app, "SELECT count(*) FROM processing_jobs WHERE record_id = :id", record_id
        )

    assert response.status_code == 200
    assert transcript["source_version"] == 2
    assert transcript["content"] == "编辑后的正文"
    assert transcript["edited_by_user"] is True
    assert record["status"] == "NOTE"
    assert record["title"] == "编辑标题"
    assert job_count == 0
    assert fake.prompts == []


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
