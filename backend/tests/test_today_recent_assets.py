import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.modules.agent.graph import resolve_agent_config
from app.modules.agent.runtime import (
    AgentRuntimeContext,
    bind_agent_runtime_context,
    reset_agent_runtime_context,
)
from app.modules.agent.tools.list_recent_assets import list_recent_assets
from app.modules.jobs.models import ProcessingJob
from app.modules.knowledge_point.models import KnowledgePoint
from app.modules.quiz.models import Quiz
from app.modules.review_material.models import ReviewMaterial
from app.modules.summary.models import AiSummary
from app.modules.today.recent_assets import RecentAssetService
from tests.test_today import insert_stats_record, running_today_app
from tests.test_today_plan_items import create_course

URL = "/api/today/recent-assets"
MOMENT = datetime(2026, 10, 10, 8, tzinfo=UTC)


def summary(record: str, version: int = 1, status: str = "CONFIRMED") -> AiSummary:
    return AiSummary(
        record_id=record,
        version_no=version,
        transcript_source_version=1,
        topic="事务",
        abstract="事务摘要",
        summary_json='{"sections": []}',
        status=status,
        model="fixture",
        prompt_version="fixture",
        token_usage_json="{}",
        latency_ms=0,
        created_at=MOMENT,
        updated_at=MOMENT,
        confirmed_at=MOMENT + timedelta(days=version) if status == "CONFIRMED" else None,
    )


def point(record: str, status: str = "ACTIVE") -> KnowledgePoint:
    return KnowledgePoint(
        record_id=record,
        name="事务隔离",
        detail="详细内容不进入聚合",
        tags="[]",
        importance=3,
        generation_status=status,
        created_at=MOMENT,
        updated_at=MOMENT + timedelta(days=20),
    )


def quiz(record: str, status: str = "ACTIVE") -> Quiz:
    return Quiz(
        record_id=record,
        generation_status=status,
        question_type="MULTIPLE_CHOICE",
        stem="事务的隔离性是什么？",
        options_json='["相互隔离", "没有隔离"]',
        correct_answer_json="0",
        explanation="答案不进入聚合",
        difficulty="EASY",
        created_at=MOMENT,
        updated_at=MOMENT + timedelta(days=30),
    )


def review(record: str, version: int = 1, status: str = "CONFIRMED") -> ReviewMaterial:
    return ReviewMaterial(
        record_id=record,
        version_no=version,
        transcript_source_version=1,
        quick_review="复习内容",
        key_list_json='["隔离"]',
        mind_map_markdown="事务",
        status=status,
        model="fixture",
        prompt_version="fixture",
        token_usage_json="{}",
        latency_ms=0,
        created_at=MOMENT,
        updated_at=MOMENT,
        confirmed_at=None,
    )


@pytest.mark.anyio
async def test_grouped_assets_versions_times_soft_deletion_and_archive(tmp_path: Path) -> None:
    async with running_today_app(tmp_path) as (app, client):
        course = await create_course(client, "数据库")
        record = str(uuid4())
        await insert_stats_record(app, record, course_id=course)
        deleted_point = point(record)
        deleted_point.deleted_at = MOMENT
        visible_point = point(record)
        deleted_summary = summary(record, 5)
        deleted_summary.deleted_at = MOMENT
        deleted_quiz = quiz(record)
        deleted_quiz.deleted_at = MOMENT
        deleted_review = review(record, 3)
        deleted_review.deleted_at = MOMENT
        old_summary = summary(record)
        latest_summary = summary(record, 2)
        async with app.state.session_factory() as session, session.begin():
            session.add_all(
                [
                    old_summary,
                    latest_summary,
                    deleted_summary,
                    summary(record, 3, "GENERATED"),
                    summary(record, 4, "SUPERSEDED"),
                    visible_point,
                    point(record),
                    deleted_point,
                    point(record, "DRAFT"),
                    point(record, "SUPERSEDED"),
                    quiz(record),
                    deleted_quiz,
                    quiz(record, "DRAFT"),
                    quiz(record, "SUPERSEDED"),
                    review(record),
                    deleted_review,
                    review(record, 2, "GENERATED"),
                ]
            )
        response = await client.get(URL)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["total"] == 4
        items = {item["asset_type"]: item for item in data["items"]}
        assert items["knowledge_point"]["asset_count"] == 2
        assert items["quiz"]["asset_count"] == 1
        assert items["summary"]["asset_count"] == 1
        assert items["summary"]["asset_at"] == "2026-10-12T08:00:00Z"
        assert items["summary"]["time_basis"] == "confirmed"
        assert items["review_material"]["time_basis"] == "created"
        assert items["knowledge_point"]["asset_at"] == "2026-10-10T08:00:00Z"
        assert [i["asset_type"] for i in data["items"]] == [
            "summary",
            "knowledge_point",
            "quiz",
            "review_material",
        ]
        for item in data["items"]:
            assert item["course_id"] == course and item["course_name"] == "数据库"
            assert item["href"].startswith(f"/records/{record}")
            assert "detail" not in item and "correct_answer" not in item
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE courses SET status='ARCHIVED' WHERE id=:id"), {"id": course}
            )
        assert (await client.get(URL)).json() == data
        for table, identifier in [
            ("knowledge_points", visible_point.id),
            ("records", record),
            ("courses", course),
        ]:
            async with app.state.session_factory() as session, session.begin():
                await session.execute(
                    text(f"UPDATE {table} SET deleted_at=:at WHERE id=:id"),
                    {"at": MOMENT.isoformat(), "id": identifier},
                )
            current = (await client.get(URL)).json()
            if table == "knowledge_points":
                assert (
                    next(
                        item["asset_count"]
                        for item in current["items"]
                        if item["asset_type"] == "knowledge_point"
                    )
                    == 1
                )
            else:
                assert current["total"] == 0
            async with app.state.session_factory() as session, session.begin():
                await session.execute(
                    text(f"UPDATE {table} SET deleted_at=NULL WHERE id=:id"), {"id": identifier}
                )
        unclassified = str(uuid4())
        await insert_stats_record(app, unclassified, course_id=None)
        async with app.state.session_factory() as session, session.begin():
            session.add(point(unclassified))
        unclassified_row = next(
            item
            for item in (await client.get(URL)).json()["items"]
            if item["record_id"] == unclassified
        )
        assert unclassified_row["course_id"] is None and unclassified_row["course_name"] is None


@pytest.mark.anyio
async def test_pagination_validation_agent_budget_and_no_domain_writes(tmp_path: Path) -> None:
    async with running_today_app(tmp_path) as (app, client):
        course = await create_course(client, "课程")
        records = sorted(str(uuid4()) for _ in range(26))
        for record in records:
            await insert_stats_record(app, record, course_id=course)
        async with app.state.session_factory() as session, session.begin():
            session.add_all(point(record) for record in records)
        data = (await client.get(URL)).json()
        assert data["total"] == 26 and len(data["items"]) == 5
        page = (await client.get(URL, params={"offset": 20, "limit": 20})).json()
        assert [item["record_id"] for item in page["items"]] == records[20:]
        assert (await client.get(URL, params={"asset_type": "summary"})).json()["total"] == 0
        assert (await client.get(URL, params={"course_id": str(uuid4())})).json()["total"] == 0
        for params in [
            {"asset_type": "bad"},
            {"course_id": "bad"},
            {"limit": 0},
            {"limit": 101},
            {"offset": -1},
        ]:
            assert (await client.get(URL, params=params)).status_code == 422
        assert (await client.get(URL, headers={"X-KnowRealm-Token": "bad"})).status_code == 403
        async with app.state.session_factory() as session:
            before = (
                await session.execute(text("SELECT * FROM knowledge_points ORDER BY id"))
            ).all()
        runtime = AgentRuntimeContext(
            session_factory=app.state.session_factory, session_id=str(uuid4())
        )
        token = bind_agent_runtime_context(runtime)
        try:
            with pytest.raises(ValidationError):
                await list_recent_assets.ainvoke({"course_id": "invalid"})
            with pytest.raises(ValidationError):
                await list_recent_assets.ainvoke({"asset_type": "invalid"})
            assert not json.loads(await list_recent_assets.ainvoke({"limit": 0}))["ok"]
            result = json.loads(await list_recent_assets.ainvoke({"limit": 5}))
            assert result["assets"] == data["items"]
            assert result["total"] == 26 and result["truncated"]
            assert "仅列前 5" in result["message"]
            all_items = json.loads(
                await list_recent_assets.ainvoke(
                    {"course_id": course, "asset_type": "knowledge_point"}
                )
            )
            assert len(all_items["assets"]) == 26
            runtime.budget.calls_used = 6
            assert "上限" in json.loads(await list_recent_assets.ainvoke({}))["message"]
        finally:
            reset_agent_runtime_context(token)
        assert not json.loads(await list_recent_assets.ainvoke({}))["ok"]
        async with app.state.session_factory() as session:
            assert (
                await session.execute(text("SELECT * FROM knowledge_points ORDER BY id"))
            ).all() == before
            assert await session.scalar(text("SELECT COUNT(*) FROM learning_events")) == 0
        for retrieval in (False, True):
            for research in (False, True):
                tools = resolve_agent_config(
                    retrieval=retrieval, research=research, web_search_enabled=False
                ).tools
                assert sum(tool.name == "list_recent_assets" for tool in tools) == 1


@pytest.mark.anyio
async def test_confirmation_and_adoption_production_endpoints_to_recent_assets(
    tmp_path: Path,
) -> None:
    async with running_today_app(tmp_path) as (app, client):
        course = await create_course(client, "事务学习")
        record = str(uuid4())
        await insert_stats_record(app, record, course_id=course, status="SUMMARY_READY")
        generated = summary(record, status="GENERATED")
        material = review(record, status="GENERATED")
        async with app.state.session_factory() as session, session.begin():
            session.add_all([generated, material])
        assert (await client.get(URL)).json()["total"] == 0
        confirmed = await client.post(
            f"/api/records/{record}/summary-confirmations", json={"summary_id": generated.id}
        )
        assert confirmed.status_code == 200, confirmed.text
        material_response = await client.post(
            f"/api/records/{record}/review-material-confirmations"
        )
        assert material_response.status_code == 200, material_response.text
        batch_ids = [str(uuid4()), str(uuid4())]
        async with app.state.session_factory() as session, session.begin():
            for batch_id, job_type in zip(
                batch_ids, ["KNOWLEDGE_EXTRACTION", "QUIZ_GENERATION"], strict=True
            ):
                session.add(
                    ProcessingJob(
                        id=batch_id,
                        record_id=record,
                        job_type=job_type,
                        status="SUCCEEDED",
                        input_json="{}",
                    )
                )
            await session.flush()
            kp, question = point(record, "DRAFT"), quiz(record, "DRAFT")
            kp.batch_id, question.batch_id = batch_ids
            kp.generated_from_summary_id = question.generated_from_summary_id = generated.id
            session.add_all([kp, question])
        for prefix, batch_id in zip(["knowledge-point", "quiz"], batch_ids, strict=True):
            response = await client.post(
                f"/api/records/{record}/{prefix}-batches/{batch_id}/confirmations"
            )
            assert response.status_code == 200, response.text
        result = (await client.get(URL)).json()
        assert result["total"] == 4
        assert all(item["asset_count"] == 1 for item in result["items"])
        token = bind_agent_runtime_context(
            AgentRuntimeContext(session_factory=app.state.session_factory, session_id=str(uuid4()))
        )
        try:
            assert json.loads(await list_recent_assets.ainvoke({}))["assets"] == result["items"]
        finally:
            reset_agent_runtime_context(token)


@pytest.mark.anyio
async def test_agent_reports_query_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def unavailable(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("fixture failure")

    async with running_today_app(tmp_path) as (app, _client):
        monkeypatch.setattr(RecentAssetService, "list_recent", unavailable)
        token = bind_agent_runtime_context(
            AgentRuntimeContext(session_factory=app.state.session_factory, session_id=str(uuid4()))
        )
        try:
            payload = json.loads(await list_recent_assets.ainvoke({}))
            assert not payload["ok"] and "查询失败" in payload["message"]
        finally:
            reset_agent_runtime_context(token)
