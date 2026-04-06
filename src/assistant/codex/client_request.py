import asyncio
from typing import Final

from pydantic import BaseModel

from assistant.codex import app_server
from assistant.codex.common import CLIENT_REQUEST_ID_PLACEHOLDER
from assistant.codex.schemas.codex_app_server_protocol_schemas import (
    ClientRequest,
)

_TIMEOUT_SECONDS: Final = 5.0


class Context:
    def __init__(self) -> None:
        self._response_futures: dict[int, asyncio.Future[object]] = {}
        self._request_id = 1

    def create_future(self) -> tuple[int, asyncio.Future[object]]:
        request_id = self._next_request_id()
        future: asyncio.Future[object] = (
            asyncio.get_running_loop().create_future()
        )
        self._response_futures[request_id] = future
        return request_id, future

    def pop_future(self, request_id: int) -> asyncio.Future[object] | None:
        return self._response_futures.pop(request_id, None)

    def _next_request_id(self) -> int:
        request_id = self._request_id
        self._request_id += 1
        return request_id


class Sender:
    def __init__(
        self,
        app_server_running_checker: app_server.RunningChecker,
        app_server_stdin_writer: app_server.StdinWriter,
        client_request_registry: Context,
    ) -> None:
        self._app_server_running_checker = app_server_running_checker
        self._app_server_stdin_writer = app_server_stdin_writer
        self._client_request_registry = client_request_registry

    async def __call__[T: BaseModel](
        self,
        request: ClientRequest,
        result_type: type[T],
        *,
        timeout: float | None = _TIMEOUT_SECONDS,
    ) -> T:
        if request.id != CLIENT_REQUEST_ID_PLACEHOLDER:
            msg = f"Client request id must be placeholder, got: {request.id}"
            raise ValueError(msg)

        self._app_server_running_checker()

        async with asyncio.timeout(timeout):
            request.id, future = self._client_request_registry.create_future()
            try:
                await self._app_server_stdin_writer(request)
                result = await future
            except (asyncio.CancelledError, Exception):
                self._client_request_registry.pop_future(request.id)
                future.cancel()
                raise

            return result_type.model_validate(result)
