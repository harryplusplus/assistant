import asyncio
from typing import Final, Protocol

from assistant.codex.schemas.codex_app_server_protocol_schemas import (
    ServerNotification,
    ServerRequest,
)

CLIENT_REQUEST_ID_PLACEHOLDER: Final = 0

ClientRequestResponseFutures = dict[int, asyncio.Future[object]]


class ServerRequestHandler(Protocol):
    async def __call__(self, request: ServerRequest) -> object: ...


class ServerNotificationHandler(Protocol):
    async def __call__(self, notification: ServerNotification) -> None: ...
