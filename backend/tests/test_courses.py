from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.main import create_app

TOKEN = "test-launch-token"


@asynccontextmanager
async def course_client(data_dir: Path) -> AsyncGenerator[httpx.AsyncClient]:
    app = create_app(data_dir=data_dir, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield client


@asynccontextmanager
async def running_course_app(
    data_dir: Path,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(data_dir=data_dir, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield app, client


@pytest.mark.anyio
async def test_first_school_course_persists_and_appears_in_list(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"

    async with course_client(data_dir) as client:
        assert (await client.get("/api/courses")).json() == []

        response = await client.post(
            "/api/courses",
            json={
                "name": "  操作系统  ",
                "learning_context": "SCHOOL",
                "education_stage": "UNDERGRADUATE",
                "depth": "ADVANCED",
                "course_type": "MAJOR",
                "description": "理解进程、内存与文件系统。",
            },
        )

        assert response.status_code == 201
        assert response.json() == {
            "id": response.json()["id"],
            "name": "操作系统",
            "learning_context": "SCHOOL",
            "education_stage": "UNDERGRADUATE",
            "depth": None,
            "course_type": "MAJOR",
            "description": "理解进程、内存与文件系统。",
            "status": "ACTIVE",
            "created_at": response.json()["created_at"],
            "updated_at": response.json()["updated_at"],
        }
        assert (await client.get("/api/courses")).json() == [response.json()]

    async with course_client(data_dir) as restarted_client:
        assert (await restarted_client.get("/api/courses")).json() == [response.json()]


@pytest.mark.anyio
async def test_token_context_constraints_and_sqlite_pragmas(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with running_course_app(data_dir) as (app, client):
        assert (await client.get("/api/health")).status_code == 403
        assert (
            await client.get("/api/health", headers={"X-KnowRealm-Token": "wrong"})
        ).status_code == 403
        assert (await client.get("/api/health", headers={"X-KnowRealm-Token": TOKEN})).json() == {
            "status": "ok"
        }

        headers = {"X-KnowRealm-Token": TOKEN}
        school_error = await client.post(
            "/api/courses",
            headers=headers,
            json={"name": "数学", "learning_context": "SCHOOL"},
        )
        career_error = await client.post(
            "/api/courses",
            headers=headers,
            json={"name": "Rust", "learning_context": "CAREER"},
        )
        assert school_error.status_code == 422
        assert career_error.status_code == 422
        assert isinstance(school_error.json()["detail"], str)
        assert isinstance(career_error.json()["detail"], str)

        career = await client.post(
            "/api/courses",
            headers=headers,
            json={
                "name": "Rust",
                "learning_context": "CAREER",
                "education_stage": "GRADUATE",
                "depth": "INTERMEDIATE",
            },
        )
        assert career.status_code == 201
        assert career.json()["education_stage"] is None
        assert career.json()["depth"] == "INTERMEDIATE"

        async with app.state.session_factory() as session:
            foreign_keys = (await session.execute(text("PRAGMA foreign_keys"))).scalar_one()
            journal_mode = (await session.execute(text("PRAGMA journal_mode"))).scalar_one()
        assert foreign_keys == 1
        assert journal_mode == "wal"

    db_path = data_dir / "knowrealm.db"
    async with aiosqlite.connect(db_path) as connection:
        version_row = await (await connection.execute("PRAGMA user_version")).fetchone()
        assert version_row is not None
        user_version = cast(int, version_row[0])
        assert user_version == 1
        with pytest.raises(aiosqlite.IntegrityError):
            await connection.execute(
                """
                INSERT INTO courses (
                    id, name, learning_context, education_stage, depth,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "invalid-context",
                    "矛盾课程",
                    "SCHOOL",
                    "UNDERGRADUATE",
                    "ADVANCED",
                    "ACTIVE",
                    "2026-08-17T00:00:00.000000Z",
                    "2026-08-17T00:00:00.000000Z",
                ),
            )


@pytest.mark.anyio
async def test_list_sorts_by_updated_time_and_hides_soft_deleted_courses(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with running_course_app(data_dir) as (app, client):
        headers = {"X-KnowRealm-Token": TOKEN}
        older = await client.post(
            "/api/courses",
            headers=headers,
            json={
                "name": "旧课程",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        newer = await client.post(
            "/api/courses",
            headers=headers,
            json={
                "name": "新课程",
                "learning_context": "INTEREST",
                "depth": "ADVANCED",
            },
        )
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE courses SET updated_at = :updated_at WHERE id = :id"),
                {
                    "updated_at": "2025-01-01T00:00:00.000000Z",
                    "id": older.json()["id"],
                },
            )
            await session.execute(
                text("UPDATE courses SET deleted_at = :deleted_at WHERE id = :id"),
                {
                    "deleted_at": "2026-08-17T00:00:00.000000Z",
                    "id": newer.json()["id"],
                },
            )

        visible = await client.get("/api/courses", headers=headers)
        assert [course["name"] for course in visible.json()] == ["旧课程"]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
