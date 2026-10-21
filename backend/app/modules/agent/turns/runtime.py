"""ChatTurn 运行时协作件：新事件通知（降延迟）与在途执行登记。

两者均为进程内状态（sidecar 单进程先例：ChatStreamRegistry）：
- Broadcaster 只降低订阅端延迟，丢失通知由订阅端超时补拉兜底（规格 §5）；
- ActiveRegistry 供 cancel 判定「RUNNING 但无在途执行」（槽位收口失败残留）
  时直接终态收口，不永久占用会话。
"""

import asyncio
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.agent.turns.models import ChatTurn

CANCEL_POLL_INTERVAL_SECONDS = 0.4


async def watch_turn_stop(
    factory: async_sessionmaker[AsyncSession],
    turn_id: str,
    cancel: asyncio.Event,
    stopped: asyncio.Event,
) -> None:
    while not cancel.is_set() and not stopped.is_set():
        async with factory() as session:
            turn = await session.get(ChatTurn, turn_id)
            if (
                turn is None
                or turn.cancel_requested
                or turn.status in ("CANCELLED", "FAILED", "COMPLETED")
            ):
                cancel.set()
                return
        await asyncio.sleep(CANCEL_POLL_INTERVAL_SECONDS)


class TurnEventBroadcaster:
    """轮次新事件通知：publish 永不阻塞生成（满即丢，订阅端超时兜底）。"""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[None]]] = {}

    def subscribe(self, turn_id: str) -> asyncio.Queue[None]:
        queue: asyncio.Queue[None] = asyncio.Queue(maxsize=1)
        self._subscribers.setdefault(turn_id, set()).add(queue)
        return queue

    def unsubscribe(self, turn_id: str, queue: asyncio.Queue[None]) -> None:
        subscribers = self._subscribers.get(turn_id)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(turn_id, None)

    def publish(self, turn_id: str) -> None:
        for queue in list(self._subscribers.get(turn_id, ())):
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                pass


class ActiveTurnRegistry:
    """在途执行登记：execute 期间注册，cancel 据此区分「通知停止」与「直接收口」。"""

    def __init__(self) -> None:
        self._active: set[str] = set()

    def __contains__(self, turn_id: str) -> bool:
        return turn_id in self._active

    def register(self, turn_id: str) -> None:
        self._active.add(turn_id)

    def unregister(self, turn_id: str) -> None:
        self._active.discard(turn_id)


class ChatTurnRecovery:
    """启动对账一次性闸门：双执行槽各调 recover_interrupted，只允许首跑全量扫描。

    先置位再执行扫描：后到的第二槽 no-op，避免「槽 0 已领取新轮次、槽 1 的
    全局扫描把 RUNNING 误翻 INTERRUPTED」的启动竞态（多实例槽位禁全局恢复）。
    """

    def __init__(self) -> None:
        self._done = False

    async def run_once(self, recover: Callable[[], Awaitable[None]]) -> None:
        if self._done:
            return
        self._done = True
        await recover()
