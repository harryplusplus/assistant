import asyncio
import logging
from contextlib import suppress
from importlib.metadata import version
from typing import Final

from pydantic import TypeAdapter, ValidationError

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
_jsonrpc_message_adapter: TypeAdapter[JsonrpcMessage] = TypeAdapter(JsonrpcMessage)


class AppServerResponseError(Exception):
    def __init__(self, code: int, message: str, data: object | None = None) -> None:
        super().__init__(f"Request failed: {code} {message}")
        self.code = code
        self.message = message
        self.data = data


_APP_SERVER_COMMAND: Final[tuple[str, ...]] = (
    "codex",
    "app-server",
)
_INITIALIZE_TIMEOUT_SECONDS: Final = 10.0
_SHUTDOWN_TIMEOUT_SECONDS: Final = 5.0


class AppServer:
    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._next_request_id = 0
        self._pending: dict[int, asyncio.Future[JsonrpcResponse | JsonrpcError]] = {}

    async def start(self) -> None:
        if self._process is not None:
            msg = "AppServer is already running."
            raise RuntimeError(msg)

        self._process = await asyncio.create_subprocess_exec(
            *_APP_SERVER_COMMAND,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            self._stdout_task = asyncio.create_task(self._read_stdout())
            self._stderr_task = asyncio.create_task(self._read_stderr())

            await self._initialize()
            await self._initialized()
        except Exception:
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
        await self._await_background_tasks()
        logger.info("Stopped")

    async def _send_request(self, request: ClientRequest) -> JsonrpcResponse:
        request_id = request.id
        if not isinstance(request_id, int):
            msg = f"Client request id must be int: got {request_id!r}"
            raise TypeError(msg)

        future: asyncio.Future[JsonrpcResponse | JsonrpcError] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending[request_id] = future

        try:
            await self._write(request)
            response = await future
        except BaseException:
            self._pending.pop(request_id, None)
            if not future.done():
                future.cancel()
            raise

        if isinstance(response, JsonrpcError):
            error = response.error
            raise AppServerResponseError(
                code=error.code,
                message=error.message,
                data=error.data,
            )

        return response

    async def _write(self, payload: ClientRequest | ClientNotification) -> None:
        process = self._process
        if process is None:
            msg = "Not running."
            raise RuntimeError(msg)

        stdin = process.stdin
        if stdin is None or stdin.is_closing():
            msg = "Stdin is not available."
            raise RuntimeError(msg)

        stdin.write((payload.model_dump_json() + "\n").encode())
        await stdin.drain()

    def _get_next_request_id(self) -> int:
        request_id = self._next_request_id
        self._next_request_id += 1
        return request_id

    async def _read_stdout(self) -> None:
        try:
            if self._process is None:
                return

            stdout = self._process.stdout
            if stdout is None:
                return

            while True:
                line = await stdout.readline()
                if line == b"":
                    break

                try:
                    message = _jsonrpc_message_adapter.validate_json(line.rstrip())
                except ValidationError:
                    logger.exception(
                        "Failed to parse RPC message: %s",
                        line.decode(errors="replace").rstrip(),
                    )
                    continue

                self._handle_rpc_message(message)
        finally:
            self._fail_pending(RuntimeError("stdout closed."))

    def _handle_rpc_message(self, message: JsonrpcMessage) -> None:
        if isinstance(message, (JsonrpcResponse, JsonrpcError)):
            future = self._pop_pending_client_request(message)
            if future is None:
                return

            if future.done():
                logger.warning(
                    "Received response for already completed request: %s", message.id
                )
                return

            future.set_result(message)
        elif isinstance(message, JsonrpcRequest):
            logger.warning(
                "Received unexpected request from server: %s", message.method
            )
            # TODO: Implement server requests.
        else:  # JsonrpcNotification
            logger.warning(
                "Received unexpected notification from server: %s", message.method
            )
            # TODO: Implement server notifications.

    def _pop_pending_client_request(
        self,
        response: JsonrpcResponse | JsonrpcError,
    ) -> asyncio.Future[JsonrpcResponse | JsonrpcError] | None:
        request_id = response.id
        if not isinstance(request_id, int):
            logger.warning(
                "Received response with non-client request id: %r", request_id
            )
            return None

        future = self._pending.pop(request_id, None)
        if future is None:
            logger.warning("Received response with unknown id: %s", request_id)

        return future

    async def _read_stderr(self) -> None:
        if self._process is None:
            return

        stderr = self._process.stderr
        if stderr is None:
            return

        while True:
            line = await stderr.readline()
            if line == b"":
                break

            stderr_logger.warning("%s", line.decode(errors="replace").rstrip())

    def _fail_pending(self, error: Exception) -> None:
        pending = list(self._pending.values())
        self._pending.clear()

        for future in pending:
            if future.done():
                continue

            future.set_exception(error)

    async def _await_background_tasks(self) -> None:
        tasks = [self._stdout_task, self._stderr_task]
        self._stdout_task = None
        self._stderr_task = None

        for task in tasks:
            if task is None:
                continue

            if not task.done():
                task.cancel()

            with suppress(asyncio.CancelledError):
                await task

    async def _initialize(self) -> None:
        request_id = self._get_next_request_id()
        response = await asyncio.wait_for(
            self._send_request(
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
                )
            ),
            timeout=_INITIALIZE_TIMEOUT_SECONDS,
        )

        initialize_response = InitializeResponse.model_validate(response.result)
        logger.info("Initialized: user_agent=%s", initialize_response.userAgent)

    async def _initialized(self) -> None:
        await self._write(InitializedNotification(method="initialized"))
