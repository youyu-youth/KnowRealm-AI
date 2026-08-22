import asyncio
from collections import defaultdict


class RecordInvalidationNotifier:
    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._versions: defaultdict[str, int] = defaultdict(int)

    def version(self, record_id: str) -> int:
        return self._versions[record_id]

    async def notify(self, record_id: str) -> None:
        async with self._condition:
            self._versions[record_id] += 1
            self._condition.notify_all()

    async def wait_for_change(self, record_id: str, version: int) -> int:
        async with self._condition:
            await self._condition.wait_for(lambda: self._versions[record_id] != version)
            return self._versions[record_id]
