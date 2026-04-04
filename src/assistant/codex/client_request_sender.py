import asyncio
from typing import Final, TypeVar

from pydantic import BaseModel

from assistant.codex.client_message_writer import ClientMessageWriter
from assistant.codex.common import (
    CLIENT_REQUEST_ID_PLACEHOLDER,
    ClientRequestResponseFutures,
)
from assistant.codex.running_checker import RunningChecker
from assistant.codex.schemas.codex_app_server_protocol_schemas import (
    ClientRequest,
)

ModelType = TypeVar("ModelType", bound=BaseModel)


_REQUEST_TIMEOUT_SECONDS: Final = 10.0


class ClientRequestSender:
    def __init__(
        self,
        running_checker: RunningChecker,
        client_message_writer: ClientMessageWriter,
        client_request_response_futures: ClientRequestResponseFutures,
    ) -> None:
        self._running_checker = running_checker
        self._client_message_writer = client_message_writer
        self._client_request_response_futures = client_request_response_futures
        self._request_id = 1

    async def __call__(
        self,
        request: ClientRequest,
        result_type: type[ModelType],
        *,
        timeout: float | None = _REQUEST_TIMEOUT_SECONDS,
    ) -> ModelType:
        self._running_checker()
        async with asyncio.timeout(timeout):
            result = await self._send(request)
            return result_type.model_validate(result)

    def _next_request_id(self) -> int:
        request_id = self._request_id
        self._request_id += 1
        return request_id

    async def _send(self, request: ClientRequest) -> object:
        if request.id != CLIENT_REQUEST_ID_PLACEHOLDER:
            msg = "Request already has an id"
            raise ValueError(msg)

        request.id = self._next_request_id()

        future: asyncio.Future[object] = (
            asyncio.get_running_loop().create_future()
        )
        self._client_request_response_futures[request.id] = future

        try:
            await self._client_message_writer(request)
            return await future
        except BaseException:
            self._client_request_response_futures.pop(request.id, None)
            future.cancel()
            raise
