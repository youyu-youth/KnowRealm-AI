import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi import FastAPI

from app.main import create_app

TOKEN = "test-launch-token"

DEFAULTS = {
    "theme": "SYSTEM",
    "font_scale": "M",
    "timezone": None,
    "close_behavior": "TRAY",
    "quick_note_shortcut": "Ctrl+Alt+N",
    "autostart": False,
    "quiz_last_count": 5,
}


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@asynccontextmanager
async def running_app(
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


def settings_path(data_dir: Path) -> Path:
    return data_dir / "config" / "settings.json"


def read_settings(data_dir: Path) -> dict[str, object]:
    path = settings_path(data_dir)
    if not path.exists():
        return {}
    value: object = json.loads(path.read_text(encoding="utf-8"))
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def write_settings(data_dir: Path, settings: dict[str, object]) -> None:
    path = settings_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings), encoding="utf-8")


@pytest.mark.anyio
async def test_get_preferences_returns_defaults_without_writing_file(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (_app, client):
        response = await client.get("/api/settings/preferences")

    assert response.status_code == 200
    assert response.json() == DEFAULTS
    assert not settings_path(tmp_path).exists()


@pytest.mark.anyio
async def test_put_merges_partial_updates_and_keeps_unknown_keys(tmp_path: Path) -> None:
    write_settings(
        tmp_path,
        {
            "quiz_last_count": 10,
            "tencent_asr_consent_granted_at": "2026-08-29T00:00:00Z",
            "custom_key": {"kept": True},
        },
    )
    async with running_app(tmp_path) as (_app, client):
        theme_update = await client.put("/api/settings/preferences", json={"theme": "DARK"})
        desktop_update = await client.put(
            "/api/settings/preferences",
            json={"close_behavior": "EXIT", "autostart": True},
        )
        timezone_update = await client.put(
            "/api/settings/preferences", json={"timezone": "Asia/Shanghai"}
        )
        shortcut_update = await client.put(
            "/api/settings/preferences", json={"quick_note_shortcut": "Ctrl+Alt+P"}
        )
        reread = await client.get("/api/settings/preferences")

    assert theme_update.json() == {
        **DEFAULTS,
        "theme": "DARK",
        "quiz_last_count": 10,
    }
    assert desktop_update.json() == {
        **DEFAULTS,
        "theme": "DARK",
        "close_behavior": "EXIT",
        "autostart": True,
        "quiz_last_count": 10,
    }
    assert timezone_update.json() == {
        **DEFAULTS,
        "theme": "DARK",
        "timezone": "Asia/Shanghai",
        "close_behavior": "EXIT",
        "autostart": True,
        "quiz_last_count": 10,
    }
    assert shortcut_update.json() == {
        **DEFAULTS,
        "theme": "DARK",
        "timezone": "Asia/Shanghai",
        "close_behavior": "EXIT",
        "quick_note_shortcut": "Ctrl+Alt+P",
        "autostart": True,
        "quiz_last_count": 10,
    }
    assert reread.json() == shortcut_update.json()
    stored = read_settings(tmp_path)
    assert stored == {
        "theme": "DARK",
        "timezone": "Asia/Shanghai",
        "close_behavior": "EXIT",
        "quick_note_shortcut": "Ctrl+Alt+P",
        "autostart": True,
        "quiz_last_count": 10,
        "tencent_asr_consent_granted_at": "2026-08-29T00:00:00Z",
        "custom_key": {"kept": True},
    }


@pytest.mark.anyio
async def test_put_default_values_remove_preference_keys(tmp_path: Path) -> None:
    write_settings(
        tmp_path,
        {
            "theme": "LIGHT",
            "font_scale": "L",
            "timezone": "Asia/Shanghai",
            "close_behavior": "EXIT",
            "quick_note_shortcut": "Ctrl+Alt+P",
            "autostart": True,
            "quiz_last_count": 10,
            "custom_key": {"kept": True},
        },
    )
    async with running_app(tmp_path) as (_app, client):
        for payload in (
            {"font_scale": "M"},
            {"theme": "SYSTEM"},
            {"timezone": None},
            {"close_behavior": "TRAY"},
            {"quick_note_shortcut": "Ctrl+Alt+N"},
            {"autostart": False},
            {"quiz_last_count": 5},
        ):
            response = await client.put("/api/settings/preferences", json=payload)
            assert response.status_code == 200

    assert read_settings(tmp_path) == {"custom_key": {"kept": True}}


@pytest.mark.anyio
async def test_put_empty_body_keeps_everything_unchanged(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (_app, client):
        response = await client.put("/api/settings/preferences", json={})

    assert response.status_code == 200
    assert response.json() == DEFAULTS
    assert not settings_path(tmp_path).exists()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {"theme": "BLUE"},
        {"font_scale": "XL"},
        {"timezone": "Mars/Olympus"},
        {"close_behavior": "ASK"},
        {"quick_note_shortcut": "N"},
        {"quick_note_shortcut": "Ctrl"},
        {"quick_note_shortcut": "Ctrl+Alt"},
        {"quick_note_shortcut": "Ctrl+N+Shift"},
        {"quick_note_shortcut": "N+Ctrl"},
        {"quick_note_shortcut": "Ctrl+Meta+X"},
        {"quick_note_shortcut": "Ctrl+Escape"},
        {"quick_note_shortcut": "Ctrl+Numpad1"},
        {"quick_note_shortcut": "Ctrl+"},
        {"quick_note_shortcut": 42},
        {"quick_note_shortcut": None},
        {"autostart": "maybe"},
        {"quiz_last_count": 7},
        {"theme": None},
        {"font_scale": None},
        {"close_behavior": None},
        {"autostart": None},
        {"quiz_last_count": None},
    ],
)
async def test_put_rejects_invalid_values(tmp_path: Path, payload: dict[str, object]) -> None:
    async with running_app(tmp_path) as (_app, client):
        response = await client.put("/api/settings/preferences", json=payload)

    assert response.status_code == 422


@pytest.mark.anyio
@pytest.mark.parametrize(
    "shortcut",
    [
        "Ctrl+Alt+P",
        "ctrl+alt+p",
        "Shift+F2",
        "Super+X",
        "CmdOrCtrl+Space",
        "Ctrl+Shift+4",
        "Alt+ArrowLeft",
    ],
)
async def test_put_accepts_valid_shortcuts(tmp_path: Path, shortcut: str) -> None:
    async with running_app(tmp_path) as (_app, client):
        response = await client.put(
            "/api/settings/preferences", json={"quick_note_shortcut": shortcut}
        )

    assert response.status_code == 200
    assert response.json()["quick_note_shortcut"] == shortcut


@pytest.mark.anyio
async def test_put_shortcut_rejection_message_names_the_rule(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (_app, client):
        response = await client.put("/api/settings/preferences", json={"quick_note_shortcut": "N"})

    assert response.status_code == 422
    assert "quick_note_shortcut" in response.json()["detail"]


@pytest.mark.anyio
async def test_put_timezone_rejection_message_names_the_rule(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (_app, client):
        response = await client.put("/api/settings/preferences", json={"timezone": "Mars/Olympus"})

    assert response.status_code == 422
    assert "timezone 必须是合法的 IANA 时区名" in response.json()["detail"]


@pytest.mark.anyio
async def test_put_accepts_explicit_null_timezone_and_valid_values(tmp_path: Path) -> None:
    async with running_app(tmp_path) as (_app, client):
        updated = await client.put(
            "/api/settings/preferences",
            json={"theme": "LIGHT", "font_scale": "S", "timezone": None},
        )

    assert updated.status_code == 200
    assert updated.json() == {**DEFAULTS, "theme": "LIGHT", "font_scale": "S"}
    assert read_settings(tmp_path) == {"theme": "LIGHT", "font_scale": "S"}


@pytest.mark.anyio
async def test_get_falls_back_to_defaults_for_corrupted_stored_values(
    tmp_path: Path,
) -> None:
    write_settings(
        tmp_path,
        {
            "theme": "BLUE",
            "font_scale": "XL",
            "timezone": "Mars/Olympus",
            "close_behavior": "ASK",
            "quick_note_shortcut": "NotAHotkey",
            "autostart": "maybe",
            "quiz_last_count": 7,
        },
    )
    async with running_app(tmp_path) as (_app, client):
        response = await client.get("/api/settings/preferences")

    assert response.json() == DEFAULTS
