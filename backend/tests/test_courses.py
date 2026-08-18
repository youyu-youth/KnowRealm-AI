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


@pytest.mark.anyio
async def test_list_courses_searches_literal_name_and_combines_filters(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with course_client(data_dir) as client:
        long_name = "课" * 100
        courses = [
            {
                "name": "操作系统",
                "learning_context": "SCHOOL",
                "education_stage": "UNDERGRADUATE",
                "course_type": "MAJOR",
            },
            {
                "name": "操作系统通识",
                "learning_context": "SCHOOL",
                "education_stage": "UNDERGRADUATE",
                "course_type": "GENERAL",
            },
            {
                "name": r"SQL 100%_\\ 转义",
                "learning_context": "CAREER",
                "depth": "INTERMEDIATE",
                "course_type": "MAJOR",
            },
            {
                "name": "SQL 100XY 转义",
                "learning_context": "CAREER",
                "depth": "INTERMEDIATE",
                "course_type": "MAJOR",
            },
            {
                "name": long_name,
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        ]
        for payload in courses:
            assert (await client.post("/api/courses", json=payload)).status_code == 201

        chinese = await client.get("/api/courses", params={"q": "  操作  "})
        combined = await client.get(
            "/api/courses",
            params={
                "q": "操作",
                "education_stage": "UNDERGRADUATE",
                "course_type": "MAJOR",
            },
        )
        literal = await client.get("/api/courses", params={"q": r"%_\\"})
        blank = await client.get("/api/courses", params={"q": "   "})
        trimmed_boundary = await client.get("/api/courses", params={"q": f"  {long_name}  "})
        missing = await client.get("/api/courses", params={"q": "不存在"})

        assert [course["name"] for course in chinese.json()] == [
            "操作系统通识",
            "操作系统",
        ]
        assert [course["name"] for course in combined.json()] == ["操作系统"]
        assert [course["name"] for course in literal.json()] == [r"SQL 100%_\\ 转义"]
        assert len(blank.json()) == len(courses)
        assert [course["name"] for course in trimmed_boundary.json()] == [long_name]
        assert missing.json() == []


@pytest.mark.anyio
async def test_filtered_list_never_returns_soft_deleted_courses(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with running_course_app(data_dir) as (app, client):
        headers = {"X-KnowRealm-Token": TOKEN}
        created = await client.post(
            "/api/courses",
            headers=headers,
            json={
                "name": "墓碑课程",
                "learning_context": "SCHOOL",
                "education_stage": "HIGH_SCHOOL",
                "course_type": "ELECTIVE",
            },
        )
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE courses SET deleted_at = :deleted_at WHERE id = :id"),
                {
                    "deleted_at": "2026-08-18T00:00:00.000000Z",
                    "id": created.json()["id"],
                },
            )

        visible = await client.get(
            "/api/courses",
            headers=headers,
            params={
                "q": "墓碑",
                "education_stage": "HIGH_SCHOOL",
                "course_type": "ELECTIVE",
            },
        )

        assert visible.json() == []


@pytest.mark.anyio
async def test_course_detail_returns_context_and_hot_words(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with running_course_app(data_dir) as (app, client):
        headers = {"X-KnowRealm-Token": TOKEN}
        created = await client.post(
            "/api/courses",
            headers=headers,
            json={
                "name": "操作系统",
                "learning_context": "SCHOOL",
                "education_stage": "UNDERGRADUATE",
                "course_type": "MAJOR",
                "description": "理解进程、内存与文件系统。",
            },
        )
        course_id = created.json()["id"]

        detail = await client.get(f"/api/courses/{course_id}", headers=headers)
        assert detail.status_code == 200
        assert detail.json() == {
            **created.json(),
            "hot_words": [],
        }

        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE courses SET hot_words = :hot_words WHERE id = :id"),
                {"hot_words": '["进程", "内存", "文件系统"]', "id": course_id},
            )

        with_words = await client.get(f"/api/courses/{course_id}", headers=headers)
        assert with_words.json()["hot_words"] == ["进程", "内存", "文件系统"]

        missing = await client.get("/api/courses/nonexistent-id", headers=headers)
        assert missing.status_code == 404
        assert isinstance(missing.json()["detail"], str)


@pytest.mark.anyio
async def test_edit_updates_fields_and_bumps_updated_at(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with course_client(data_dir) as client:
        headers = {"X-KnowRealm-Token": TOKEN}
        await client.post(
            "/api/courses",
            headers=headers,
            json={
                "name": "旧课程",
                "learning_context": "INTEREST",
                "depth": "BEGINNER",
            },
        )
        edited = await client.post(
            "/api/courses",
            headers=headers,
            json={
                "name": "操作系统",
                "learning_context": "SCHOOL",
                "education_stage": "UNDERGRADUATE",
                "course_type": "MAJOR",
                "description": "旧说明",
            },
        )
        course_id = edited.json()["id"]

        updated = await client.patch(
            f"/api/courses/{course_id}",
            headers=headers,
            json={
                "name": "  操作系统导论  ",
                "description": "",
                "course_type": None,
            },
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "操作系统导论"
        assert updated.json()["description"] is None
        assert updated.json()["course_type"] is None

        no_op = await client.patch(f"/api/courses/{course_id}", headers=headers, json={})
        assert no_op.status_code == 200
        assert no_op.json() == updated.json()

        detail = await client.get(f"/api/courses/{course_id}", headers=headers)
        assert detail.json()["updated_at"] >= edited.json()["updated_at"]

        listing = await client.get("/api/courses", headers=headers)
        assert [course["name"] for course in listing.json()] == [
            "操作系统导论",
            "旧课程",
        ]


@pytest.mark.anyio
async def test_edit_rejects_blank_name_and_keeps_old_data(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with course_client(data_dir) as client:
        headers = {"X-KnowRealm-Token": TOKEN}
        created = await client.post(
            "/api/courses",
            headers=headers,
            json={
                "name": "操作系统",
                "learning_context": "SCHOOL",
                "education_stage": "UNDERGRADUATE",
            },
        )
        course_id = created.json()["id"]

        blank = await client.patch(
            f"/api/courses/{course_id}", headers=headers, json={"name": "   "}
        )
        too_long = await client.patch(
            f"/api/courses/{course_id}", headers=headers, json={"name": "课" * 101}
        )
        assert blank.status_code == 422
        assert too_long.status_code == 422

        detail = await client.get(f"/api/courses/{course_id}", headers=headers)
        assert detail.json()["name"] == "操作系统"


@pytest.mark.anyio
async def test_edit_context_switch_requires_and_clears_counterpart(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with course_client(data_dir) as client:
        headers = {"X-KnowRealm-Token": TOKEN}
        created = await client.post(
            "/api/courses",
            headers=headers,
            json={
                "name": "操作系统",
                "learning_context": "SCHOOL",
                "education_stage": "UNDERGRADUATE",
                "depth": None,
            },
        )
        course_id = created.json()["id"]

        switch_without_depth = await client.patch(
            f"/api/courses/{course_id}",
            headers=headers,
            json={"learning_context": "CAREER"},
        )
        assert switch_without_depth.status_code == 422
        detail_after_rejection = await client.get(f"/api/courses/{course_id}", headers=headers)
        assert detail_after_rejection.json()["learning_context"] == "SCHOOL"
        assert detail_after_rejection.json()["education_stage"] == "UNDERGRADUATE"

        switched = await client.patch(
            f"/api/courses/{course_id}",
            headers=headers,
            json={"learning_context": "CAREER", "depth": "INTERMEDIATE"},
        )
        assert switched.status_code == 200
        assert switched.json()["education_stage"] is None
        assert switched.json()["depth"] == "INTERMEDIATE"

        back_without_stage = await client.patch(
            f"/api/courses/{course_id}",
            headers=headers,
            json={"learning_context": "SCHOOL", "depth": None},
        )
        assert back_without_stage.status_code == 422

        back = await client.patch(
            f"/api/courses/{course_id}",
            headers=headers,
            json={"learning_context": "SCHOOL", "education_stage": "GRADUATE"},
        )
        assert back.status_code == 200
        assert back.json()["education_stage"] == "GRADUATE"
        assert back.json()["depth"] is None


@pytest.mark.anyio
async def test_detail_and_edit_hide_soft_deleted_course(tmp_path: Path) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with running_course_app(data_dir) as (app, client):
        headers = {"X-KnowRealm-Token": TOKEN}
        created = await client.post(
            "/api/courses",
            headers=headers,
            json={
                "name": "墓碑课程",
                "learning_context": "SCHOOL",
                "education_stage": "HIGH_SCHOOL",
            },
        )
        course_id = created.json()["id"]
        async with app.state.session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE courses SET deleted_at = :deleted_at WHERE id = :id"),
                {"deleted_at": "2026-08-18T00:00:00.000000Z", "id": course_id},
            )

        detail = await client.get(f"/api/courses/{course_id}", headers=headers)
        edit = await client.patch(
            f"/api/courses/{course_id}", headers=headers, json={"name": "新名字"}
        )
        assert detail.status_code == 404
        assert edit.status_code == 404


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
