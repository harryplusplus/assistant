import asyncio
import logging
from typing import Any, Final, Protocol

from .events import Event

logger = logging.getLogger(__name__)

Queue = asyncio.Queue[Event]


class Emitter:
    def __init__(self, queue: Queue) -> None:
        self._queue = queue

    def emit(self, event: Event) -> None:
        self._queue.put_nowait(event)


class Handler[T: Event](Protocol):
    def type(self) -> type[T]: ...
    async def __call__(self, event: T) -> None: ...


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[type[Event], Handler[Any]] = {}

    def register[T: Event](self, handler: Handler[T]) -> None:
        type_ = handler.type()
        if type_ in self._handlers:
            msg = f"Handler for {type_} is already registered"
            raise RuntimeError(msg)

        self._handlers[type_] = handler

    def get(self, type_: type[Event]) -> Handler[Any] | None:
        return self._handlers.get(type_)


class Consumer:
    def __init__(self, queue: Queue, handler_registry: HandlerRegistry) -> None:
        self._queue = queue
        self._handler_registry = handler_registry
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None:
            msg = f"{self.__class__.__name__} is already started"
            raise RuntimeError(msg)

        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        while True:
            event = await self._queue.get()
            event_type = type(event)
            handler = self._handler_registry.get(event_type)
            if handler is None:
                logger.warning("Not found handler for type: %s", event_type)
                continue

            try:
                await handler(event)
            except Exception:
                logger.exception("Failed to handle event: %s", event)


class Service:
    def __init__(self) -> None:
        self._queue = Queue()
        self._handler_registry = HandlerRegistry()
        self._consumer = Consumer(self._queue, self._handler_registry)
        self.emitter: Final = Emitter(self._queue)

    def start(self) -> None:
        self._consumer.start()

    def register_handler[T: Event](self, handler: Handler[T]) -> None:
        self._handler_registry.register(handler)
