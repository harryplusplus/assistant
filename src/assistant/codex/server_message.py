import asyncio
import logging
from dataclasses import dataclass
from typing import override

from assistant import event
from assistant.codex import client_request
from assistant.codex.schemas.codex_app_server_protocol_schemas import (
    JsonrpcError,
    JsonrpcRequest,
    JsonrpcResponse,
    V2RequestId,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True, init=False)
class Error(Exception):
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


class Handler(event.Handler[event.CodexServerMessage]):
    def __init__(self, client_request_registry: client_request.Context) -> None:
        self._client_request_registry = client_request_registry

    @override
    def type(self) -> type[event.CodexServerMessage]:
        return event.CodexServerMessage

    @override
    async def __call__(self, value: event.CodexServerMessage) -> None:
        message = value.message

        if isinstance(message, JsonrpcResponse):
            future = self._pop_client_request_future(message.id)
            if future is not None:
                future.set_result(message.result)

            return

        if isinstance(message, JsonrpcError):
            future = self._pop_client_request_future(message.id)
            if future is not None:
                error = message.error
                future.set_exception(
                    Error(
                        code=error.code, message=error.message, data=error.data
                    )
                )

            return

        if isinstance(message, JsonrpcRequest):
            logger.warning(
                "Received request from server, not supported, message: %s",
                message,
            )
            return

        logger.warning(
            "Received notification from server, not supported, message: %s",
            message,
        )

    def _pop_client_request_future(
        self, request_id: V2RequestId
    ) -> asyncio.Future[object] | None:
        if isinstance(request_id, str):
            logger.warning(
                "Client request id must be int, got str, id: %s", request_id
            )
            return None

        future = self._client_request_registry.pop_future(request_id)
        if future is None:
            logger.warning(
                "Not found future for client request id: %d", request_id
            )
            return None

        if future.done():
            logger.warning(
                "Already done future for client request id: %d", request_id
            )
            return None

        return future
