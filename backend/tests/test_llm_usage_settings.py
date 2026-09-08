import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utcnow
from app.main import create_app
from app.modules.llm.models import LlmCallLog

TOKEN = "test-launch-token"
USAGE_URL = "/api/settings/usage/llm"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@asynccontextmanager
async def running_app(
    data_dir: Path,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient, async_sessionmaker[AsyncSession]]]:
    app = create_app(data_dir=data_dir, launch_token=TOKEN)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client, app.state.session_factory


def make_log(
    model: str,
    *,
    token_usage: dict[str, object] | None = None,
    error_code: str | None = None,
    created_at: object = None,
) -> LlmCallLog:
    return LlmCallLog(
        request_id=str(uuid4()),
        graph_name="summary",
        graph_node="generate",
        model=model,
        prompt_version="summary-v1",
        token_usage_json=json.dumps(token_usage or {}, separators=(",", ":")),
        latency_ms=12,
        error_code=error_code,
        created_at=created_at if created_at is not None else utcnow(),
    )


async def insert_logs(
    session_factory: async_sessionmaker[AsyncSession],
    logs: list[LlmCallLog],
) -> None:
    async with session_factory() as session, session.begin():
        session.add_all(logs)


@pytest.mark.anyio
async def test_llm_usage_empty_database_returns_zero_filled_series(
    tmp_path: Path,
) -> None:
    async with running_app(tmp_path / "KnowRealm") as (_app, client, _factory):
        response = await client.get(USAGE_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    daily = body["daily"]
    assert len(daily) == 30
    assert all(point["total_tokens"] == 0 and point["call_count"] == 0 for point in daily)
    start_date = (utcnow().date() - timedelta(days=29)).isoformat()
    end_date = utcnow().date().isoformat()
    assert daily[0]["date"] == start_date
    assert daily[-1]["date"] == end_date


@pytest.mark.anyio
async def test_llm_usage_aggregates_by_model_with_errors_and_window(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with running_app(data_dir) as (_app, client, session_factory):
        await insert_logs(
            session_factory,
            [
                make_log(
                    "qwen-plus",
                    token_usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
                ),
                make_log(
                    "qwen-plus",
                    token_usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                ),
                # 失败行：token_usage 为空 JSON，token 计 0 但计入调用数与失败数。
                make_log("qwen-plus", error_code="PROVIDER_REQUEST_FAILED"),
                make_log(
                    "deepseek-v3",
                    token_usage={"input_tokens": 300, "output_tokens": 200, "total_tokens": 500},
                    created_at=utcnow() - timedelta(days=3),
                ),
                # 窗口外（31 天前）：不进入任何口径。
                make_log(
                    "qwen-plus",
                    token_usage={"input_tokens": 9, "output_tokens": 9, "total_tokens": 9},
                    created_at=utcnow() - timedelta(days=31),
                ),
            ],
        )
        response = await client.get(USAGE_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == [
        {
            "model": "deepseek-v3",
            "call_count": 1,
            "input_tokens": 300,
            "output_tokens": 200,
            "total_tokens": 500,
            "error_count": 0,
        },
        {
            "model": "qwen-plus",
            "call_count": 3,
            "input_tokens": 110,
            "output_tokens": 55,
            "total_tokens": 165,
            "error_count": 1,
        },
    ]

    daily = body["daily"]
    assert len(daily) == 30
    today_point = daily[-1]
    assert today_point["total_tokens"] == 165
    assert today_point["call_count"] == 3
    three_days_ago = daily[-4]
    assert three_days_ago["total_tokens"] == 500
    assert three_days_ago["call_count"] == 1
    # 无调用日补零（如昨天），31 天前的行不落入任何点位。
    assert daily[-2]["total_tokens"] == 0 and daily[-2]["call_count"] == 0
    assert sum(point["total_tokens"] for point in daily) == 665
