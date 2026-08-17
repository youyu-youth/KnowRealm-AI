from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest

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


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
