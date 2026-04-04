from assistant.codex.app_server import AppServer
from assistant.codex.server_message_reader import ServerMessageReader


class RunningChecker:
    def __init__(
        self,
        app_server: AppServer,
        server_message_reader: ServerMessageReader,
    ) -> None:
        self._app_server = app_server
        self._server_message_reader = server_message_reader

    def __call__(self) -> None:
        if (
            not self._app_server.running
            or not self._server_message_reader.running
        ):
            msg = "App server or server message reader is not running"
            raise RuntimeError(msg)
