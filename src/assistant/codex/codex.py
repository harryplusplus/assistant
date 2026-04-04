from assistant.closer import Closer
from assistant.codex.app_server import AppServer
from assistant.codex.client_message_writer import ClientMessageWriter
from assistant.codex.client_notification_sender import (
    ClientNotificationSender,
)
from assistant.codex.client_request_sender import ClientRequestSender
from assistant.codex.common import (
    ClientRequestResponseFutures,
    ServerNotificationHandler,
    ServerRequestHandler,
)
from assistant.codex.running_checker import RunningChecker
from assistant.codex.server_message_reader import (
    ServerErrorMessageReader,
    ServerMessageReader,
)


class Codex:
    def __init__(
        self,
        server_request_handler: ServerRequestHandler,
        server_notification_handler: ServerNotificationHandler,
    ) -> None:
        self._server_request_handler = server_request_handler
        self._server_notification_handler = server_notification_handler
        self._client_request_response_futures: ClientRequestResponseFutures = {}
        self._closer = Closer(self._on_close)
        self._app_server = AppServer()
        self._server_message_reader: ServerMessageReader | None = None
        self._server_error_message_reader: ServerErrorMessageReader | None = (
            None
        )
        self._client_request_sender: ClientRequestSender | None = None
        self._client_notification_sender: ClientNotificationSender | None = None

    async def start(self) -> None:
        stdin, stdout, stderr = await self._app_server.start()

        self._server_message_reader = ServerMessageReader(
            stdout=stdout,
            client_request_response_futures=self._client_request_response_futures,
            server_request_handler=self._server_request_handler,
            server_notification_handler=self._server_notification_handler,
        )
        self._server_message_reader.start()

        self._server_error_message_reader = ServerErrorMessageReader(
            stderr=stderr,
        )
        self._server_error_message_reader.start()

        client_message_writer = ClientMessageWriter(stdin=stdin)
        running_checker = RunningChecker(
            app_server=self._app_server,
            server_message_reader=self._server_message_reader,
        )

        self._client_request_sender = ClientRequestSender(
            running_checker=running_checker,
            client_message_writer=client_message_writer,
            client_request_response_futures=self._client_request_response_futures,
        )
        self._client_notification_sender = ClientNotificationSender(
            running_checker=running_checker,
            client_message_writer=client_message_writer,
        )

    async def close(self) -> None:
        await self._closer()

    async def _on_close(self) -> None:
        await self._app_server.close()

        if self._server_message_reader is not None:
            await self._server_message_reader.wait()

        if self._server_error_message_reader is not None:
            await self._server_error_message_reader.wait()

    @property
    def client_request_sender(self) -> ClientRequestSender:
        if self._client_request_sender is None:
            msg = "Not started"
            raise RuntimeError(msg)

        return self._client_request_sender

    @property
    def client_notification_sender(self) -> ClientNotificationSender:
        if self._client_notification_sender is None:
            msg = "Not started"
            raise RuntimeError(msg)

        return self._client_notification_sender
