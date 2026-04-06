import asyncio
import contextlib
import logging

from assistant import event
from assistant.codex.app_server.consumer import JsonlConsumer
from assistant.codex.app_server.stderr import create_stderr_consumer
from assistant.codex.app_server.stdin import StdinWriter
from assistant.codex.app_server.stdout import create_stdout_consumer

logger = logging.getLogger(__name__)


_WAIT_TIMEOUT = 5


class Process:
    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None

    async def start(
        self, event_emitter: event.Emitter
    ) -> tuple[StdinWriter, JsonlConsumer, JsonlConsumer]:
        if self._process is not None:
            msg = "Already started"
            raise RuntimeError(msg)

        try:
            self._process = await asyncio.create_subprocess_exec(
                "codex",
                "app-server",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            if (
                self._process.stdin is None
                or self._process.stdout is None
                or self._process.stderr is None
            ):
                msg = "Failed to capture stdin, stdout, or stderr"
                raise RuntimeError(msg)

            stdin_writer = StdinWriter(self._process.stdin)
            stdout_consumer = create_stdout_consumer(
                stdout=self._process.stdout,
                event_emitter=event_emitter,
            )
            stderr_consumer = create_stderr_consumer(
                stderr=self._process.stderr
            )

            return stdin_writer, stdout_consumer, stderr_consumer
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        process = self._process
        if process is None:
            return

        stdin = process.stdin
        if stdin is not None and not stdin.is_closing():
            stdin.close()
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                await stdin.wait_closed()

        if process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), timeout=_WAIT_TIMEOUT)
            except TimeoutError:
                logger.warning(
                    "Did not exit after sending EOF, sending SIGTERM"
                )
                with contextlib.suppress(ProcessLookupError):
                    process.terminate()

                try:
                    await asyncio.wait_for(
                        process.wait(), timeout=_WAIT_TIMEOUT
                    )
                except TimeoutError:
                    logger.warning(
                        "Did not exit after sending SIGTERM, sending SIGKILL"
                    )

                    with contextlib.suppress(ProcessLookupError):
                        process.kill()

                    await process.wait()

        self._process = None

    @property
    def running(self) -> bool:
        return self._process is not None
