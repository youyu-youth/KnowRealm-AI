from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.main import create_app

TOKEN = "test-launch-token"


@asynccontextmanager
async def running_today_app(
    data_dir: Path,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(data_dir=data_dir, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client


@pytest.mark.anyio
async def test_today_lists_only_live_summary_ready_records(tmp_path: Path) -> None:
    async with running_today_app(tmp_path / "KnowRealm") as (app, client):
        active_course = await client.post(
            "/api/courses",
            json={
                "name": "操作系统",
                "learning_context": "SCHOOL",
                "education_stage": "UNDERGRADUATE",
            },
        )
        archived_course = await client.post(
            "/api/courses",
            json={
                "name": "已归档课程",
                "learning_context": "INTEREST",
                "depth": "ADVANCED",
            },
        )
        active_id = active_course.json()["id"]
        archived_id = archived_course.json()["id"]
        await client.patch(f"/api/courses/{archived_id}", json={"status": "ARCHIVED"})

        async def insert_record(
            record_id: str,
            course_id: str,
            status: str,
            updated_at: str,
            *,
            deleted: bool = False,
        ) -> None:
            async with app.state.session_factory() as session, session.begin():
                await session.execute(
                    text(
                        "INSERT INTO records "
                        "(id, course_id, capture_type, title, status, duration_ms, "
                        "summary_confirmed_at, created_at, updated_at, deleted_at) "
                        "VALUES (:id, :course_id, 'DOCUMENT_IMPORT', :title, :status, 0, "
                        "NULL, :updated_at, :updated_at, :deleted_at)"
                    ),
                    {
                        "id": record_id,
                        "course_id": course_id,
                        "title": f"记录-{record_id[:4]}",
                        "status": status,
                        "updated_at": updated_at,
                        "deleted_at": "2026-08-23T13:00:00.000000Z" if deleted else None,
                    },
                )

        await insert_record(
            "11111111-1111-4111-8111-111111111111",
            active_id,
            "SUMMARY_READY",
            "2026-08-23T12:00:00.000000Z",
        )
        await insert_record(
            "22222222-2222-4222-8222-222222222222",
            active_id,
            "SUMMARY_PENDING",
            "2026-08-23T12:30:00.000000Z",
        )
        await insert_record(
            "33333333-3333-4333-8333-333333333333",
            active_id,
            "COMPLETED",
            "2026-08-23T12:40:00.000000Z",
        )
        await insert_record(
            "44444444-4444-4444-8444-444444444444",
            active_id,
            "SUMMARY_READY",
            "2026-08-23T12:50:00.000000Z",
            deleted=True,
        )
        await insert_record(
            "55555555-5555-4555-8555-555555555555",
            archived_id,
            "SUMMARY_READY",
            "2026-08-23T11:00:00.000000Z",
        )

        todos = await client.get("/api/today/pending-summaries")

    assert todos.status_code == 200
    assert todos.json() == [
        {
            "record_id": "11111111-1111-4111-8111-111111111111",
            "title": "记录-1111",
            "course_id": active_id,
            "course_name": "操作系统",
            "ready_at": "2026-08-23T12:00:00.000000Z",
        },
        {
            "record_id": "55555555-5555-4555-8555-555555555555",
            "title": "记录-5555",
            "course_id": archived_id,
            "course_name": "已归档课程",
            "ready_at": "2026-08-23T11:00:00.000000Z",
        },
    ]
