import asyncio
import logging
from dataclasses import dataclass
from typing import Final, Protocol

_DEFAULT_TIMEOUT = 5


@dataclass(slots=True, frozen=True)
class HandlerContext:
    logger: logging.Logger


class Handler(Protocol):
    def __call__(self, context: HandlerContext, json: bytes) -> None: ...


class JsonlConsumer:
    def __init__(
        self, name: str, reader: asyncio.StreamReader, handler: Handler
    ) -> None:
        self.name: Final = name
        self._logger: Final = logging.getLogger(name)
        self._running = False
        self._reader = reader
        self._handler = handler
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None:
            msg = f"{self.name} is already started"
            raise RuntimeError(msg)

        self._task = asyncio.create_task(self._run())

    async def wait_for(self, timeout: float | None = _DEFAULT_TIMEOUT) -> None:
        if self._task is None:
            return

        task = self._task
        self._task = None

        await asyncio.wait_for(task, timeout=timeout)

    async def _run(self) -> None:
        try:
            self._running = True
            handler_context = HandlerContext(logger=self._logger)

            while True:
                line = await self._reader.readline()
                if line == b"":
                    break

                json = line.rstrip()

                try:
                    self._handler(handler_context, json)
                except Exception:
                    self._logger.exception(
                        "Unexpected error in handler of %s, json: %s",
                        self.name,
                        json,
                    )
        except Exception:
            self._logger.exception("Unexpected error in %s", self.name)
        finally:
            self._running = False

    @property
    def running(self) -> bool:
        return self._running
