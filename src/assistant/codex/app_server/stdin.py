import asyncio

from assistant.codex.schemas.codex_app_server_protocol_schemas import (
    ClientNotification,
    ClientRequest,
    JsonrpcError,
    JsonrpcResponse,
)


class StdinWriter:
    def __init__(self, stdin: asyncio.StreamWriter) -> None:
        self._stdin = stdin

    async def __call__(
        self,
        message: ClientRequest
        | ClientNotification
        | JsonrpcResponse
        | JsonrpcError,
    ) -> None:
        stdin = self._stdin
        if stdin.is_closing():
            msg = "Stdin is closed"
            raise RuntimeError(msg)

        stdin.write((message.model_dump_json() + "\n").encode())
        await stdin.drain()
