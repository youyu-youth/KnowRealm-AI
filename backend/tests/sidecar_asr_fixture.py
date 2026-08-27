import argparse
import json
import sys
from pathlib import Path
from typing import cast

import httpx
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.llm import SummaryModelResult  # noqa: E402
from app.core.logging import setup_logging  # noqa: E402
from app.main import create_app  # noqa: E402
from app.schemas.summary import SummaryContent, SummarySection  # noqa: E402
from app.services.tencent_asr_client import TencentAsrClient  # noqa: E402


class FakeSummaryModel:
    async def generate(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        prompt: str,
    ) -> SummaryModelResult:
        return SummaryModelResult(
            output=SummaryContent(
                topic="真实进程升级主题",
                abstract="用于真实 socket 升级验收的合成摘要。" * 30,
                sections=[
                    SummarySection(heading="核心内容", points=["合成要点，不依赖真实供应商。"])
                ],
            ),
            token_usage={"total_tokens": 1},
        )


class FixtureTencentAsrTransport(httpx.AsyncBaseTransport):
    def __init__(self, control_path: Path) -> None:
        self._control_path = control_path
        self._events_path = control_path.with_suffix(".events.json")

    def _control(self) -> dict[str, object]:
        return json.loads(self._control_path.read_text(encoding="utf-8"))

    def _append(self, event: dict[str, object]) -> None:
        raw: object = (
            json.loads(self._events_path.read_text(encoding="utf-8"))
            if self._events_path.exists()
            else []
        )
        events = cast(list[dict[str, object]], raw)
        events.append(event)
        self._events_path.write_text(json.dumps(events), encoding="utf-8")

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            if not bool(self._control().get("online", True)):
                raise httpx.ConnectError("fixture offline", request=request)
            return httpx.Response(200, request=request)

        assert request.headers["X-TC-Version"] == "2019-06-14"
        assert request.headers["X-TC-Region"] == "ap-shanghai"
        assert request.headers["Authorization"].startswith("TC3-HMAC-SHA256 ")
        payload = cast(dict[str, object], json.loads(request.content))
        action = request.headers["X-TC-Action"]
        mode = self._control().get("mode", "success")
        if action == "CreateRecTask":
            assert payload["EngineModelType"] == "16k_zh"
            assert payload["SourceType"] == 1
            self._append({"event": "submit", "region": request.headers["X-TC-Region"]})
            if mode == "submit_timeout":
                raise httpx.ReadTimeout("fixture timeout", request=request)
            if mode == "invalid_json":
                return httpx.Response(200, request=request, text="not-json")
            if mode == "invalid_task_id":
                return httpx.Response(
                    200,
                    request=request,
                    json={
                        "Response": {
                            "Data": {"TaskId": "not-a-number"},
                            "RequestId": "fixture",
                        }
                    },
                )
            task_id = 1000 + sum(
                event["event"] == "submit"
                for event in cast(
                    list[dict[str, object]],
                    json.loads(self._events_path.read_text(encoding="utf-8")),
                )
            )
            return httpx.Response(
                200,
                request=request,
                json={"Response": {"Data": {"TaskId": task_id}, "RequestId": "fixture"}},
            )

        assert action == "DescribeTaskStatus"
        assert isinstance(payload["TaskId"], int)
        self._append(
            {
                "event": "poll",
                "task_id": payload["TaskId"],
                "region": request.headers["X-TC-Region"],
            }
        )
        if mode == "pending":
            return httpx.Response(
                200,
                request=request,
                json={"Response": {"Data": {"Status": 1}, "RequestId": "fixture"}},
            )
        if mode == "poll_503":
            return httpx.Response(503, request=request)
        text = str(self._control().get("text", "真实进程替身正文。"))
        return httpx.Response(
            200,
            request=request,
            json={
                "Response": {
                    "Data": {
                        "Status": 2,
                        "Result": f"[0:0.020,0:2.380]  {text}\n",
                        "ResultDetail": [{"FinalSentence": text}],
                    },
                    "RequestId": "fixture",
                }
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--token", required=True)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--ffmpeg", required=True, type=Path)
    parser.add_argument("--asr-control", required=True, type=Path)
    parser.add_argument("--fake-summary", action="store_true")
    args = parser.parse_args()
    setup_logging()
    app = create_app(
        data_dir=args.data_dir,
        launch_token=args.token,
        ffmpeg_path=args.ffmpeg,
        asr_client=TencentAsrClient(transport=FixtureTencentAsrTransport(args.asr_control)),
        summary_model=FakeSummaryModel() if args.fake_summary else None,
    )
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=args.port,
        access_log=False,
        log_config=None,
        loop="app.core.loop:sidecar_loop_factory",
    )
    server = uvicorn.Server(config)
    listener = config.bind_socket()
    print(f"KNOWREALM_SIDECAR_PORT={listener.getsockname()[1]}", flush=True)
    server.run(sockets=[listener])


if __name__ == "__main__":
    main()
