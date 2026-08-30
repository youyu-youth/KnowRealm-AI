import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import cast

import httpx

HOST = "asr.tencentcloudapi.com"
ENDPOINT = f"https://{HOST}"
SERVICE = "asr"
VERSION = "2019-06-14"
CONTENT_TYPE = "application/json; charset=utf-8"


@dataclass(frozen=True)
class TencentAsrCredentials:
    secret_id: str
    secret_key: str
    region: str


class TencentAsrTaskStatus(StrEnum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class TencentAsrTask:
    status: TencentAsrTaskStatus
    text: str = ""
    error_code: str | None = None


class TencentAsrApiError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _signing_key(secret_key: str, date: str) -> bytes:
    secret_date = hmac.new(f"TC3{secret_key}".encode(), date.encode(), hashlib.sha256).digest()
    secret_service = hmac.new(secret_date, SERVICE.encode(), hashlib.sha256).digest()
    return hmac.new(secret_service, b"tc3_request", hashlib.sha256).digest()


class TencentAsrClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def is_online(self) -> bool:
        try:
            async with httpx.AsyncClient(
                timeout=3, trust_env=False, transport=self._transport
            ) as client:
                await client.get(ENDPOINT)
        except httpx.RequestError:
            return False
        return True

    async def test_credentials(
        self,
        credentials: TencentAsrCredentials,
    ) -> None:
        """GetAsrVocabList 只读轻调用：验证 TC3 凭据可用，不创建任何资源。"""
        await self._request("GetAsrVocabList", {"Limit": 1}, credentials)

    async def submit(
        self,
        path: Path,
        credentials: TencentAsrCredentials,
        config: dict[str, object],
    ) -> str:
        audio = await self._read_audio(path)
        payload: dict[str, object] = {
            "EngineModelType": config["engine_model_type"],
            "ChannelNum": config["channel_num"],
            "ResTextFormat": config["res_text_format"],
            "SourceType": 1,
            "Data": base64.b64encode(audio).decode("ascii"),
            "DataLen": len(audio),
        }
        hot_words = config.get("hot_words")
        if isinstance(hot_words, str) and hot_words:
            payload["HotwordList"] = hot_words
        response = await self._request("CreateRecTask", payload, credentials)
        data = response.get("Data")
        if not isinstance(data, dict):
            raise TencentAsrApiError("INVALID_CREATE_RESPONSE")
        task_id = cast(dict[str, object], data).get("TaskId")
        if isinstance(task_id, bool) or not (
            isinstance(task_id, int) or isinstance(task_id, str) and task_id.isdigit()
        ):
            raise TencentAsrApiError("INVALID_CREATE_RESPONSE")
        return str(task_id)

    async def poll(
        self,
        task_id: str,
        credentials: TencentAsrCredentials,
    ) -> TencentAsrTask:
        response = await self._request(
            "DescribeTaskStatus",
            {"TaskId": int(task_id)},
            credentials,
        )
        data = response.get("Data")
        if not isinstance(data, dict):
            raise TencentAsrApiError("INVALID_STATUS_RESPONSE")
        task = cast(dict[str, object], data)
        status = task.get("Status")
        if not isinstance(status, int):
            raise TencentAsrApiError("INVALID_STATUS_RESPONSE")
        if status in (0, 1):
            return TencentAsrTask(status=TencentAsrTaskStatus.PENDING)
        if status == 2:
            result_detail = task.get("ResultDetail")
            if not isinstance(result_detail, list):
                raise TencentAsrApiError("INVALID_STATUS_RESPONSE")
            sentences: list[str] = []
            for item in cast(list[object], result_detail):
                if not isinstance(item, dict):
                    raise TencentAsrApiError("INVALID_STATUS_RESPONSE")
                sentence = cast(dict[str, object], item).get("FinalSentence")
                if not isinstance(sentence, str):
                    raise TencentAsrApiError("INVALID_STATUS_RESPONSE")
                sentences.append(sentence)
            return TencentAsrTask(
                status=TencentAsrTaskStatus.SUCCEEDED,
                text="\n".join(sentences),
            )
        error = task.get("ErrorMsg")
        return TencentAsrTask(
            status=TencentAsrTaskStatus.FAILED,
            error_code=error if isinstance(error, str) and error else "ASR_FAILED",
        )

    async def _read_audio(self, path: Path) -> bytes:
        import asyncio

        return await asyncio.to_thread(path.read_bytes)

    async def _request(
        self,
        action: str,
        payload: dict[str, object],
        credentials: TencentAsrCredentials,
    ) -> dict[str, object]:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        timestamp = int(time.time())
        date = datetime.fromtimestamp(timestamp, UTC).strftime("%Y-%m-%d")
        hashed_body = hashlib.sha256(body.encode()).hexdigest()
        canonical_headers = f"content-type:{CONTENT_TYPE}\nhost:{HOST}\n"
        canonical_request = f"POST\n/\n\n{canonical_headers}\ncontent-type;host\n{hashed_body}"
        scope = f"{date}/{SERVICE}/tc3_request"
        string_to_sign = (
            "TC3-HMAC-SHA256\n"
            f"{timestamp}\n"
            f"{scope}\n"
            f"{hashlib.sha256(canonical_request.encode()).hexdigest()}"
        )
        signature = hmac.new(
            _signing_key(credentials.secret_key, date),
            string_to_sign.encode(),
            hashlib.sha256,
        ).hexdigest()
        authorization = (
            "TC3-HMAC-SHA256 "
            f"Credential={credentials.secret_id}/{scope}, "
            "SignedHeaders=content-type;host, "
            f"Signature={signature}"
        )
        headers = {
            "Authorization": authorization,
            "Content-Type": CONTENT_TYPE,
            "Host": HOST,
            "X-TC-Action": action,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": VERSION,
            "X-TC-Region": credentials.region,
        }
        async with httpx.AsyncClient(
            timeout=15, trust_env=False, transport=self._transport
        ) as client:
            raw = await client.post(ENDPOINT, content=body.encode(), headers=headers)
            raw.raise_for_status()
        try:
            decoded: object = raw.json()
        except ValueError as exc:
            raise TencentAsrApiError("INVALID_RESPONSE") from exc
        if not isinstance(decoded, dict):
            raise TencentAsrApiError("INVALID_RESPONSE")
        response_value = cast(dict[str, object], decoded).get("Response")
        if not isinstance(response_value, dict):
            raise TencentAsrApiError("INVALID_RESPONSE")
        response = cast(dict[str, object], response_value)
        error = response.get("Error")
        if isinstance(error, dict):
            code = cast(dict[str, object], error).get("Code")
            if isinstance(code, str):
                raise TencentAsrApiError(code)
        return response
