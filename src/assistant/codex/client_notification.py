from assistant.codex import app_server
from assistant.codex.schemas.codex_app_server_protocol_schemas import (
    ClientNotification,
)


class Sender:
    def __init__(
        self,
        app_server_running_checker: app_server.RunningChecker,
        app_server_stdin_writer: app_server.StdinWriter,
    ) -> None:
        self._app_server_running_checker = app_server_running_checker
        self._app_server_stdin_writer = app_server_stdin_writer

    async def __call__(self, notification: ClientNotification) -> None:
        self._app_server_running_checker()
        await self._app_server_stdin_writer(notification)
