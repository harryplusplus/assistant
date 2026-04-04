import asyncio
from typing import Protocol


class CloseHandler(Protocol):
    async def __call__(self) -> None: ...


class Closer:
    def __init__(self, handler: CloseHandler) -> None:
        self._handler = handler
        self._task: asyncio.Task[None] | None = None

    async def __call__(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._handler())

        try:
            await asyncio.shield(self._task)
        except Exception:
            self._task = None
            raise
