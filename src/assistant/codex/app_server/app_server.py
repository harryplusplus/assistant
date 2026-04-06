from typing import TYPE_CHECKING

from assistant import event
from assistant.codex.app_server.process import Process
from assistant.codex.app_server.running_checker import RunningChecker
from assistant.codex.app_server.stdin import StdinWriter

if TYPE_CHECKING:
    from assistant.codex.app_server.consumer import JsonlConsumer


class AppServer:
    def __init__(
        self,
        event_emitter: event.Emitter,
    ) -> None:
        self._event_emitter = event_emitter
        self._process = Process()
        self._stdin_writer: StdinWriter | None = None
        self._stdout_consumer: JsonlConsumer | None = None
        self._stderr_consumer: JsonlConsumer | None = None

    async def start(self) -> None:
        (
            self._stdin_writer,
            self._stdout_consumer,
            self._stderr_consumer,
        ) = await self._process.start(self._event_emitter)

        self._stdout_consumer.start()
        self._stderr_consumer.start()

    async def close(self) -> None:
        await self._process.close()

        if self._stdout_consumer is not None:
            await self._stdout_consumer.wait_for()

        if self._stderr_consumer is not None:
            await self._stderr_consumer.wait_for()

    @property
    def stdin_writer(self) -> StdinWriter:
        if self._stdin_writer is None:
            msg = "App server is not started"
            raise RuntimeError(msg)

        return self._stdin_writer

    def create_running_checker(self) -> RunningChecker:
        if self._stdout_consumer is None:
            msg = "App server is not started"
            raise RuntimeError(msg)

        return RunningChecker(
            process=self._process,
            stdout_consumer=self._stdout_consumer,
        )
