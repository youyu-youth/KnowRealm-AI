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


async def stored_avatar_file(data_dir: Path) -> str | None:
    async with aiosqlite.connect(data_dir / "knowrealm.db") as connection:
        row = await (await connection.execute("SELECT avatar_file FROM profile")).fetchone()
    return row[0] if row is not None else None


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 16
JPG_BYTES = b"\xff\xd8\xff\xe0" + b"0" * 16
WEBP_BYTES = b"RIFF" + b"\x18\x00\x00\x00" + b"WEBPVP8L" + b"0" * 8
GIF_BYTES = b"GIF89a" + b"0" * 16


@pytest.mark.anyio
async def test_read_profile_before_setup_returns_empty_semantics(tmp_path: Path) -> None:
    async with running_profile_app(tmp_path) as (_app, client):
        response = await client.get("/api/profile")

        assert response.status_code == 200
        assert response.json() == {
            "nickname": None,
            "primary_role": None,
            "about_me": None,
        }
        assert await profile_row_count(tmp_path) == 0


@pytest.mark.anyio
async def test_save_profile_persists_single_row_and_echoes(tmp_path: Path) -> None:
    async with running_profile_app(tmp_path) as (_app, client):
        saved = await client.put(
            "/api/profile",
            json={
                "primary_role": "DEVELOPER",
                "nickname": "阿邹",
                "about_me": "三年后端，正在补操作系统基础",
            },
        )
        assert saved.status_code == 200
        body = saved.json()
        assert body == {
            "primary_role": "DEVELOPER",
            "nickname": "阿邹",
            "about_me": "三年后端，正在补操作系统基础",
        }

        reread = await client.get("/api/profile")
        assert reread.status_code == 200
        assert reread.json() == body

        updated = await client.put(
            "/api/profile",
            json={"primary_role": "STUDENT", "nickname": "  \n\t", "about_me": "  \n\t"},
        )
        assert updated.status_code == 200
        assert updated.json()["primary_role"] == "STUDENT"
        # 空白昵称与自我介绍均按未填写处理（None），不落空字符串。
        assert updated.json()["nickname"] is None
        assert updated.json()["about_me"] is None

        assert await profile_row_count(tmp_path) == 1


@pytest.mark.anyio
async def test_save_profile_rejects_invalid_role_and_overlong_text(
    tmp_path: Path,
) -> None:
    async with running_profile_app(tmp_path) as (_app, client):
        bad_role = await client.put(
            "/api/profile",
            json={"primary_role": "TEACHER", "nickname": None, "about_me": None},
        )
        assert bad_role.status_code == 422

        overlong_nickname = await client.put(
            "/api/profile",
            json={"primary_role": "STUDENT", "nickname": "长" * 21, "about_me": None},
        )
        assert overlong_nickname.status_code == 422

        overlong = await client.put(
            "/api/profile",
            json={"primary_role": "STUDENT", "nickname": None, "about_me": "长" * 201},
        )
        assert overlong.status_code == 422

        assert await profile_row_count(tmp_path) == 0


@pytest.mark.anyio
async def test_avatar_roundtrip_overwrite_and_delete(tmp_path: Path) -> None:
    async with running_profile_app(tmp_path) as (_app, client):
        missing = await client.get("/api/profile/avatar")
        assert missing.status_code == 404

        uploaded = await client.put("/api/profile/avatar", content=PNG_BYTES)
        assert uploaded.status_code == 204
        assert (tmp_path / "files" / "avatar.png").read_bytes() == PNG_BYTES
        assert await stored_avatar_file(tmp_path) == "files/avatar.png"

        fetched = await client.get("/api/profile/avatar")
        assert fetched.status_code == 200
        assert fetched.content == PNG_BYTES
        assert fetched.headers["content-type"].startswith("image/png")

        # 换格式覆盖上传：旧扩展名文件被清理，files/ 只保留一份。
        replaced = await client.put("/api/profile/avatar", content=JPG_BYTES)
        assert replaced.status_code == 204
        assert not (tmp_path / "files" / "avatar.png").exists()
        assert (tmp_path / "files" / "avatar.jpg").read_bytes() == JPG_BYTES
        assert await stored_avatar_file(tmp_path) == "files/avatar.jpg"
        refetched = await client.get("/api/profile/avatar")
        assert refetched.headers["content-type"].startswith("image/jpeg")

        deleted = await client.delete("/api/profile/avatar")
        assert deleted.status_code == 204
        assert not (tmp_path / "files" / "avatar.jpg").exists()
        assert await stored_avatar_file(tmp_path) is None
        gone = await client.get("/api/profile/avatar")
        assert gone.status_code == 404

        # 幂等：无头像时重复删除不报错。
        assert (await client.delete("/api/profile/avatar")).status_code == 204


@pytest.mark.anyio
async def test_avatar_accepts_webp(tmp_path: Path) -> None:
    async with running_profile_app(tmp_path) as (_app, client):
        uploaded = await client.put("/api/profile/avatar", content=WEBP_BYTES)
        assert uploaded.status_code == 204
        fetched = await client.get("/api/profile/avatar")
        assert fetched.status_code == 200
        assert fetched.headers["content-type"].startswith("image/webp")


@pytest.mark.anyio
async def test_avatar_rejects_bad_format_and_oversize(tmp_path: Path) -> None:
    async with running_profile_app(tmp_path) as (_app, client):
        gif = await client.put("/api/profile/avatar", content=GIF_BYTES)
        assert gif.status_code == 422

        empty = await client.put("/api/profile/avatar", content=b"")
        assert empty.status_code == 422

        oversize = await client.put(
            "/api/profile/avatar",
            content=b"\x89PNG\r\n\x1a\n" + b"0" * (2 * 1024 * 1024 + 1),
        )
        assert oversize.status_code == 413

        assert await stored_avatar_file(tmp_path) is None
        assert not any((tmp_path / "files").glob("avatar.*"))


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
            avatar = await unauthorized.get("/api/profile/avatar")
            assert avatar.status_code == 403
