"""真实 sidecar 进程故障验收：仅替换模型、网页网络，保留所有 worker 与写回。"""

import asyncio
import json
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.outputs import ChatGenerationChunk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_chat_turns import StubChatModel, ToolCallReply  # noqa: E402

from app.modules.capture import web_clip  # noqa: E402
from app.modules.llm import service  # noqa: E402
from app.server import main  # noqa: E402


class WaitingProcessModel(StubChatModel):
    async def _astream(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> AsyncIterator[ChatGenerationChunk]:
        previous = next((m for m in reversed(messages) if isinstance(m, ToolMessage)), None)
        if previous is None:
            type(self).replies = [
                ToolCallReply(
                    "plan_batch_operations",
                    {
                        "items": [
                            {
                                "action": "ingest_library_item",
                                "url": "https://example.com/background",
                            }
                        ]
                    },
                    "plan-call",
                )
            ]
        elif previous.name == "plan_batch_operations":
            run_id = json.loads(str(previous.content))["run"]["run_id"]
            type(self).replies = [
                ToolCallReply(
                    "wait_for_task",
                    {
                        "target_type": "RUN",
                        "target_id": run_id,
                    },
                    "wait-call",
                )
            ]
        else:
            result = json.loads(str(previous.content))
            assert result["ok"] and result["operations"][0]["background_result"]["title"]
            type(self).replies = [["原任务恢复完成"]]
        async for chunk in super()._astream(messages, stop, run_manager, **kwargs):
            yield chunk


class GatedClipAdapter:
    async def fetch_and_extract(self, url: str) -> web_clip.ClipContent:
        data_dir = Path(sys.argv[sys.argv.index("--data-dir") + 1])
        while not (data_dir / "release-fetch").exists():
            await asyncio.sleep(0.1)
        return web_clip.ClipContent(
            text="强杀后真实写回。" * 20, title="恢复资料", metadata={"url": url}
        )


if __name__ == "__main__":
    service.ChatOpenAI = WaitingProcessModel  # type: ignore[assignment]
    web_clip.WebClipAdapter = GatedClipAdapter  # type: ignore[assignment]
    main()
