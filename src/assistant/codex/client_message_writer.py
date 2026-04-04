import asyncio

from assistant.codex._app_server import ServerRequestResponse
from assistant.codex.schemas.codex_app_server_protocol_schemas import (
    ClientNotification,
    ClientRequest,
)


class ClientMessageWriter:
    def __init__(self, stdin: asyncio.StreamWriter) -> None:
        self._stdin = stdin

    async def __call__(
        self,
        message: ClientRequest | ClientNotification | ServerRequestResponse,
    ) -> None:
        stdin = self._stdin
        if stdin.is_closing():
            msg = "Stdin is closed"
            raise RuntimeError(msg)

        stdin.write((message.model_dump_json() + "\n").encode())
        await stdin.drain()
