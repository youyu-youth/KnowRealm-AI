from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.main import create_app

TOKEN = "test-launch-token"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@asynccontextmanager
async def running_profile_app(
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


async def profile_row_count(data_dir: Path) -> int:
    async with aiosqlite.connect(data_dir / "knowrealm.db") as connection:
        row = await (await connection.execute("SELECT count(*) FROM profile")).fetchone()
    assert row is not None
    return int(row[0])


@pytest.mark.anyio
async def test_read_profile_before_setup_returns_empty_semantics(tmp_path: Path) -> None:
    async with running_profile_app(tmp_path) as (_app, client):
        response = await client.get("/api/profile")

        assert response.status_code == 200
        assert response.json() == {
            "primary_role": None,
            "about_me": None,
            "updated_at": None,
        }
        assert await profile_row_count(tmp_path) == 0


@pytest.mark.anyio
async def test_save_profile_persists_single_row_and_echoes(tmp_path: Path) -> None:
    async with running_profile_app(tmp_path) as (_app, client):
        saved = await client.put(
            "/api/profile",
            json={"primary_role": "DEVELOPER", "about_me": "三年后端，正在补操作系统基础"},
        )
        assert saved.status_code == 200
        body = saved.json()
        assert body["primary_role"] == "DEVELOPER"
        assert body["about_me"] == "三年后端，正在补操作系统基础"
        assert body["updated_at"] is not None

        reread = await client.get("/api/profile")
        assert reread.status_code == 200
        assert reread.json() == body

        updated = await client.put(
            "/api/profile",
            json={"primary_role": "STUDENT", "about_me": "  \n\t"},
        )
        assert updated.status_code == 200
        assert updated.json()["primary_role"] == "STUDENT"
        # 空白自我介绍按未填写处理（None），不落空字符串。
        assert updated.json()["about_me"] is None

        assert await profile_row_count(tmp_path) == 1


@pytest.mark.anyio
async def test_save_profile_rejects_invalid_role_and_overlong_about_me(
    tmp_path: Path,
) -> None:
    async with running_profile_app(tmp_path) as (_app, client):
        bad_role = await client.put(
            "/api/profile",
            json={"primary_role": "TEACHER", "about_me": None},
        )
        assert bad_role.status_code == 422

        overlong = await client.put(
            "/api/profile",
            json={"primary_role": "STUDENT", "about_me": "长" * 201},
        )
        assert overlong.status_code == 422

        assert await profile_row_count(tmp_path) == 0


@pytest.mark.anyio
async def test_profile_endpoints_require_launch_token(tmp_path: Path) -> None:
    async with running_profile_app(tmp_path) as (_app, _client):
        unauthorized = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_app, raise_app_exceptions=False),
            base_url="http://testserver",
        )
        async with unauthorized:
            response = await unauthorized.get("/api/profile")
            assert response.status_code == 403
