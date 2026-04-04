import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

from pydantic import TypeAdapter, ValidationError

from assistant.codex.common import (
    ClientRequestResponseFutures,
    ServerNotificationHandler,
    ServerRequestHandler,
)
from assistant.codex.schemas.codex_app_server_protocol_schemas import (
    JsonrpcError,
    JsonrpcMessage,
    JsonrpcResponse,
    ServerNotification,
    ServerRequest,
)

_MESSAGE_ADAPTER: TypeAdapter[JsonrpcMessage] = TypeAdapter(JsonrpcMessage)
_SERVER_NOTIFICATION_ADAPTER: TypeAdapter[ServerNotification] = TypeAdapter(
    ServerNotification
)
_SERVER_REQUEST_ADAPTER: TypeAdapter[ServerRequest] = TypeAdapter(ServerRequest)

_DEFAULT_TIMEOUT = 5


class _JsonHandler(Protocol):
    def __call__(self, json: bytes) -> None: ...


class _JsonlReader:
    def __init__(
        self, name: str, reader: asyncio.StreamReader, handler: _JsonHandler
    ) -> None:
        self._name = name
        self._reader = reader
        self._handler = handler
        self._task: asyncio.Task[None] | None = None
        self._logger = logging.getLogger(name)
        self._running = False

    def start(self) -> None:
        if self._task is not None:
            msg = f"{self.__class__.__name__} is already started"
            raise RuntimeError(msg)
        self._task = asyncio.create_task(self._run())

    async def wait_for(self, timeout: float | None) -> None:
        if self._task is None:
            return

        task = self._task
        self._task = None

        await asyncio.wait_for(task, timeout=timeout)

    async def _run(self) -> None:
        try:
            self._running = True

            while True:
                line = await self._reader.readline()
                if line == b"":
                    break

                self._handler(line.rstrip())
        except Exception:
            self._logger.exception("Unhandled exception in loop.")
        finally:
            self._running = False

    @property
    def running(self) -> bool:
        return self._running

    @property
    def logger(self) -> logging.Logger:
        return self._logger


@dataclass(slots=True, init=False)
class ServerMessageError(Exception):
    code: int
    message: str
    data: object | None = None

    def __init__(
        self, code: int, message: str, data: object | None = None
    ) -> None:
        super().__init__(
            f"Server message error: code={code}, message={message}"
        )
        self.code = code
        self.message = message
        self.data = data


class ServerMessageReader:
    def __init__(
        self,
        stdout: asyncio.StreamReader,
        client_request_response_futures: ClientRequestResponseFutures,
        server_request_handler: ServerRequestHandler,
        server_notification_handler: ServerNotificationHandler,
    ) -> None:
        self._reader = _JsonlReader(
            name=f"{__name__}.{self.__class__.__name__}",
            reader=stdout,
            handler=self._on_json,
        )
        self._logger = self._reader.logger
        self._client_request_response_futures = client_request_response_futures
        self._server_request_handler = server_request_handler
        self._server_notification_handler = server_notification_handler

    def start(self) -> None:
        self._reader.start()

    async def wait(self) -> None:
        await self._reader.wait_for(timeout=_DEFAULT_TIMEOUT)

    def _on_json(self, json: bytes) -> None:
        try:
            message = _MESSAGE_ADAPTER.validate_json(json)
        except ValidationError:
            self._logger.exception("Failed to parse json: %s", json)
            return

        if isinstance(message, JsonrpcResponse):
            future = self._pop_client_request_response_future(message)
            if future is not None:
                future.set_result(message.result)

            return

        if isinstance(message, JsonrpcError):
            future = self._pop_client_request_response_future(message)
            if future is not None:
                future.set_exception(
                    ServerMessageError(
                        code=message.error.code,
                        message=message.error.message,
                        data=message.error.data,
                    )
                )

            return

        if isinstance(message, ServerRequest):
            try:
                request = _SERVER_REQUEST_ADAPTER.validate_python(message)
            except ValidationError:
                self._logger.exception(
                    "Failed to parse server request: %s", json
                )
                return

            # TODO
            asyncio.create_task(self._server_request_handler(request))
            return

        # ServerNotification
        try:
            notification = _SERVER_NOTIFICATION_ADAPTER.validate_python(message)
        except ValidationError:
            self._logger.exception(
                "Failed to parse server notification: %s", json
            )
            return

        # TODO
        asyncio.create_task(self._server_notification_handler(notification))

    def _pop_client_request_response_future(
        self,
        message: JsonrpcResponse | JsonrpcError,
    ) -> asyncio.Future[object] | None:
        request_id = message.id
        if not isinstance(request_id, int):
            self._logger.warning(
                "Received response for non-client request ID: %r",
                message.id,
            )
            return None

        future = self._client_request_response_futures.pop(request_id, None)
        if future is None:
            self._logger.warning(
                "Received response for unknown request ID: %s",
                message.id,
            )
            return None

        if future.done():
            self._logger.warning(
                "Received response for already completed request ID: %s",
                message.id,
            )
            return None

        return future

    @property
    def running(self) -> bool:
        return self._reader.running


class ServerErrorMessageReader:
    def __init__(self, stderr: asyncio.StreamReader) -> None:
        self._reader = _JsonlReader(
            name=f"{__name__}.{self.__class__.__name__}",
            reader=stderr,
            handler=self._on_json,
        )
        self._logger = self._reader.logger

    def start(self) -> None:
        self._reader.start()

    async def wait(self) -> None:
        await self._reader.wait_for(timeout=_DEFAULT_TIMEOUT)

    def _on_json(self, json: bytes) -> None:
        self._logger.error(json.decode(errors="replace"))
