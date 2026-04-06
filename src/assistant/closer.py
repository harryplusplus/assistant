import asyncio
from typing import Protocol


class Handler(Protocol):
    async def __call__(self) -> None: ...


class Closer:
    def __init__(self, handler: Handler) -> None:
        self._handler = handler
        self._task: asyncio.Task[None] | None = None

    async def __call__(self) -> None:
        task = self._task
        if task is None:
            task = asyncio.create_task(self._close())
            self._task = task

        await asyncio.shield(task)

    async def _close(self) -> None:
        try:
            await self._handler()
        except (asyncio.CancelledError, Exception):
            self._task = None
            raise
