import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from importlib.metadata import version
from typing import Final, TypeVar

from pydantic import BaseModel, TypeAdapter, ValidationError

from .schemas.codex_app_server_protocol_schemas import (
    ClientInfo,
    ClientNotification,
    ClientRequest,
    InitializedNotification,
    InitializeParams,
    InitializeRequest,
    InitializeResponse,
    JsonrpcError,
    JsonrpcMessage,
    JsonrpcRequest,
    JsonrpcResponse,
)

logger = logging.getLogger(__name__)
stderr_logger = logging.getLogger(f"{__name__}.stderr")


_MESSAGE_ADAPTER: TypeAdapter[JsonrpcMessage] = TypeAdapter(JsonrpcMessage)

ModelType = TypeVar("ModelType", bound=BaseModel)


@dataclass(slots=True, init=False)
class MessageError(Exception):
    code: int
    message: str
    data: object | None = None

    def __init__(self, code: int, message: str, data: object | None = None) -> None:
        super().__init__(f"Message error: code={code}, message={message}")
        self.code = code
        self.message = message
        self.data = data


_APP_SERVER_COMMAND: Final[tuple[str, ...]] = (
    "codex",
    "app-server",
)
_REQUEST_TIMEOUT_SECONDS: Final = 10.0
_SHUTDOWN_TIMEOUT_SECONDS: Final = 5.0


class AppServer:
    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._next_request_id = 0
        self._pending: dict[int, asyncio.Future[object]] = {}

    async def start(self) -> None:
        if self._process is not None:
            msg = "AppServer is already running."
            raise RuntimeError(msg)

        try:
            self._process = await asyncio.create_subprocess_exec(
                *_APP_SERVER_COMMAND,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._stdout_task = asyncio.create_task(self._stdout_loop())
            self._stderr_task = asyncio.create_task(self._stderr_loop())
            await self._initialize()
            await self._initialized()
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        if self._process is None:
            return

        process = self._process
        self._process = None

        stdin = process.stdin
        if stdin is not None and not stdin.is_closing():
            stdin.close()
            with suppress(BrokenPipeError):
                await stdin.wait_closed()

        try:
            await asyncio.wait_for(process.wait(), timeout=_SHUTDOWN_TIMEOUT_SECONDS)
        except TimeoutError:
            logger.warning("Did not exit after stdin close; sending SIGTERM")
            process.terminate()

            try:
                await asyncio.wait_for(
                    process.wait(),
                    timeout=_SHUTDOWN_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                logger.warning("Did not exit after SIGTERM; sending SIGKILL")
                process.kill()

                await process.wait()

        self._fail_pending(RuntimeError("shut down."))
        await self._close_tasks()
        logger.info("Stopped")

    async def send_request(
        self,
        request: ClientRequest,
        result_type: type[ModelType],
        *,
        timeout: float | None = _REQUEST_TIMEOUT_SECONDS,
    ) -> ModelType:
        self._check_can_send_messages()
        async with asyncio.timeout(timeout):
            return await self._send_request_without_timeout(
                request,
                result_type,
            )

    async def _send_request_without_timeout(
        self, request: ClientRequest, result_type: type[ModelType]
    ) -> ModelType:
        request_id = request.id
        if not isinstance(request_id, int):
            msg = f"Client request ID must be int: got {request_id!r}"
            raise TypeError(msg)

        future: asyncio.Future[object] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future

        try:
            await self._write(request)
            result = await future
        except BaseException:
            self._pending.pop(request_id, None)
            if not future.done():
                future.cancel()
            raise

        return result_type.model_validate(result)

    async def send_notification(self, notification: ClientNotification) -> None:
        self._check_can_send_messages()
        await self._write(notification)

    def _get_process(self) -> asyncio.subprocess.Process:
        process = self._process
        if process is None:
            msg = "Not running."
            raise RuntimeError(msg)

        return process

    def _check_can_send_messages(self) -> None:
        self._get_process()

        stdout_task = self._stdout_task
        if stdout_task is None or stdout_task.done():
            msg = "Cannot send more messages."
            raise RuntimeError(msg)

    def _get_stdin(self) -> asyncio.StreamWriter:
        process = self._get_process()

        stdin = process.stdin
        if stdin is None or stdin.is_closing():
            msg = "Stdin is not available."
            raise RuntimeError(msg)

        return stdin

    def _get_stdout(self) -> asyncio.StreamReader:
        process = self._get_process()

        stdout = process.stdout
        if stdout is None:
            msg = "Stdout is not available."
            raise RuntimeError(msg)

        return stdout

    def _get_stderr(self) -> asyncio.StreamReader:
        process = self._get_process()

        stderr = process.stderr
        if stderr is None:
            msg = "Stderr is not available."
            raise RuntimeError(msg)

        return stderr

    def _increase_request_id(self) -> int:
        request_id = self._next_request_id
        self._next_request_id += 1
        return request_id

    async def _write(self, message: ClientRequest | ClientNotification) -> None:
        stdin = self._get_stdin()
        stdin.write((message.model_dump_json() + "\n").encode())
        await stdin.drain()

    async def _stdout_loop(self) -> None:
        try:
            stdout = self._get_stdout()

            while True:
                line = await stdout.readline()
                if line == b"":
                    break

                json_bytes = line.rstrip()
                try:
                    message = _MESSAGE_ADAPTER.validate_json(json_bytes)
                except ValidationError:
                    logger.exception(
                        "Failed to parse message: %s",
                        json_bytes.decode(errors="replace"),
                    )
                    continue

                try:
                    self._handle_message(message)
                except Exception:
                    logger.exception(
                        "Failed to handle message: %s",
                        json_bytes.decode(errors="replace"),
                    )
        except Exception:
            logger.exception("Failed to read from stdout.")
        finally:
            self._fail_pending(RuntimeError("Stdout closed."))

    async def _stderr_loop(self) -> None:
        try:
            stderr = self._get_stderr()

            while True:
                line = await stderr.readline()
                if line == b"":
                    break

                stderr_logger.warning(line.decode(errors="replace").rstrip())
        except Exception:
            logger.exception("Failed to read from stderr.")

    def _handle_message(self, message: JsonrpcMessage) -> None:
        if isinstance(message, JsonrpcResponse):
            future = self._pop_pending(message)
            if future is None:
                return

            future.set_result(message.result)
        elif isinstance(message, JsonrpcError):
            future = self._pop_pending(message)
            if future is None:
                return

            future.set_exception(
                MessageError(
                    code=message.error.code,
                    message=message.error.message,
                    data=message.error.data,
                )
            )
        elif isinstance(message, JsonrpcRequest):
            logger.warning(
                "Received unexpected request from server: %s", message.method
            )
            # TODO: Implement server requests.
        else:  # JsonrpcNotification
            logger.warning(
                "Received unexpected notification from server: %s",
                message.method,
            )
            # TODO: Implement server notifications.

    def _pop_pending(
        self,
        message: JsonrpcResponse | JsonrpcError,
    ) -> asyncio.Future[object] | None:
        request_id = message.id
        if not isinstance(request_id, int):
            logger.warning(
                "Received response for non-client request ID: %r",
                message.id,
            )
            return None

        future = self._pending.pop(request_id, None)
        if future is None:
            logger.warning("Received response for unknown request ID: %s", message.id)
            return None

        if future.done():
            logger.warning(
                "Received response for already completed request ID: %s",
                message.id,
            )
            return None

        return future

    def _fail_pending(self, error: Exception) -> None:
        pending = list(self._pending.values())
        self._pending.clear()

        for future in pending:
            if future.done():
                continue

            future.set_exception(error)

    async def _close_tasks(self) -> None:
        tasks = [
            ("stdout", self._stdout_task),
            ("stderr", self._stderr_task),
        ]
        self._stdout_task = None
        self._stderr_task = None

        for task_name, task in tasks:
            if task is None:
                continue

            try:
                await asyncio.wait_for(
                    asyncio.shield(task),
                    timeout=_SHUTDOWN_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                logger.warning(
                    "Did not drain %s task after process shutdown; cancelling",
                    task_name,
                )
                task.cancel()

                with suppress(asyncio.CancelledError):
                    await task

    async def _initialize(self) -> None:
        request_id = self._increase_request_id()
        result = await self.send_request(
            InitializeRequest(
                id=request_id,
                method="initialize",
                params=InitializeParams(
                    clientInfo=ClientInfo(
                        name="assistant",
                        title="Assistant",
                        version=version("assistant"),
                    )
                ),
            ),
            InitializeResponse,
        )

        logger.info("Initialized: user_agent=%s", result.userAgent)

    async def _initialized(self) -> None:
        await self.send_notification(InitializedNotification(method="initialized"))
