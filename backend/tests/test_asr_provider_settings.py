import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app.main import create_app
from app.services.tencent_asr_client import TencentAsrClient

TOKEN = "test-launch-token"
ASR_URL = "/api/settings/providers/tencent-asr"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


class RecordingTransport(httpx.AsyncBaseTransport):
    """记录 AsrVocabList 轻调用的替身传输：可配置返回成功或腾讯云错误结构。"""

    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responses.pop(0)


def vocab_response(payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(200, json={"Response": payload})


@asynccontextmanager
async def running_app(
    data_dir: Path,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AsyncGenerator[tuple[FastAPI, httpx.AsyncClient, RecordingTransport | None]]:
    recording = transport if isinstance(transport, RecordingTransport) else None
    app = create_app(
        data_dir=data_dir,
        launch_token=TOKEN,
        asr_client=TencentAsrClient(transport=transport),
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers={"X-KnowRealm-Token": TOKEN},
        ) as client:
            yield app, client, recording


@pytest.mark.anyio
async def test_asr_provider_masks_credentials_and_preserves_empty_key(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "KnowRealm"
    async with running_app(data_dir) as (_app, client, _transport):
        missing = await client.get(ASR_URL)
        saved = await client.put(
            ASR_URL,
            json={
                "region": "ap-shanghai",
                "secret_id": "AKIDexample1234",
                "secret_key": "tencent-secret",
            },
        )
        key_kept = await client.put(
            ASR_URL,
            json={"region": "ap-beijing", "secret_id": "", "secret_key": ""},
        )
        cleared = await client.put(
            ASR_URL,
            json={
                "region": "ap-beijing",
                "secret_id": "",
                "secret_key": "",
                "clear_secret_key": True,
            },
        )

    assert missing.status_code == 200
    assert missing.json() == {"provider": None}
    assert saved.status_code == 200
    assert saved.json() == {
        "provider": {
            "region": "ap-shanghai",
            "has_credentials": True,
            "secret_id_hint": "••••1234",
        }
    }
    assert "tencent-secret" not in saved.text
    assert key_kept.json() == {
        "provider": {
            "region": "ap-beijing",
            "has_credentials": True,
            "secret_id_hint": "••••1234",
        }
    }
    assert cleared.json() == {
        "provider": {
            "region": "ap-beijing",
            "has_credentials": False,
            "secret_id_hint": None,
        }
    }

    providers = json.loads((data_dir / "config" / "providers.json").read_text(encoding="utf-8"))
    assert providers["tencent_asr"] == {
        "secret_id": "",
        "secret_key": "",
        "region": "ap-beijing",
    }


@pytest.mark.anyio
async def test_asr_provider_rejects_blank_region(tmp_path: Path) -> None:
    async with running_app(tmp_path / "KnowRealm") as (_app, client, _transport):
        blank = await client.put(
            ASR_URL,
            json={"region": "  ", "secret_id": "id", "secret_key": "key"},
        )

    assert blank.status_code == 422


@pytest.mark.anyio
async def test_asr_connection_test_uses_readonly_vocab_list_call(
    tmp_path: Path,
) -> None:
    transport = RecordingTransport(
        [vocab_response({"VocabList": [], "TotalCount": 0, "RequestId": "t"})]
    )
    data_dir = tmp_path / "KnowRealm"
    async with running_app(data_dir, transport) as (_app, client, _recording):
        unconfigured = await client.post(f"{ASR_URL}/tests")
        await client.put(
            ASR_URL,
            json={
                "region": "ap-shanghai",
                "secret_id": "AKIDexample1234",
                "secret_key": "tencent-secret",
            },
        )
        ok = await client.post(f"{ASR_URL}/tests")

    assert unconfigured.status_code == 409
    assert ok.status_code == 200
    assert ok.json() == {"ok": True, "region": "ap-shanghai"}

    request = transport.requests[0]
    assert request.headers["X-TC-Action"] == "GetAsrVocabList"
    assert request.headers["X-TC-Region"] == "ap-shanghai"
    assert request.headers["Authorization"].startswith("TC3-HMAC-SHA256 ")
    assert json.loads(request.content) == {"Limit": 1}


@pytest.mark.anyio
async def test_asr_connection_test_maps_auth_and_network_errors(
    tmp_path: Path,
) -> None:
    transport = RecordingTransport(
        [
            vocab_response(
                {
                    "Error": {
                        "Code": "AuthFailure.SecretIdNotFound",
                        "Message": "凭据不存在",
                    },
                    "RequestId": "t",
                }
            ),
            vocab_response(
                {
                    "Error": {
                        "Code": "FailedOperation.UserNotRegistered",
                        "Message": "未开通",
                    },
                    "RequestId": "t",
                }
            ),
        ]
    )
    async with running_app(tmp_path / "KnowRealm", transport) as (_app, client, _recording):
        await client.put(
            ASR_URL,
            json={
                "region": "ap-shanghai",
                "secret_id": "AKIDexample1234",
                "secret_key": "tencent-secret",
            },
        )
        auth_failure = await client.post(f"{ASR_URL}/tests")
        not_registered = await client.post(f"{ASR_URL}/tests")

    assert auth_failure.status_code == 502
    assert auth_failure.json()["detail"] == ("腾讯云凭据校验未通过，请检查 SecretId / SecretKey")
    assert not_registered.status_code == 502
    assert not_registered.json()["detail"] == ("凭据有效，但该账号尚未开通语音识别服务")
