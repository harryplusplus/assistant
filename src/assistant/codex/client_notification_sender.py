from assistant.codex.client_message_writer import ClientMessageWriter
from assistant.codex.running_checker import RunningChecker
from assistant.codex.schemas.codex_app_server_protocol_schemas import (
    ClientNotification,
)


class ClientNotificationSender:
    def __init__(
        self,
        running_checker: RunningChecker,
        client_message_writer: ClientMessageWriter,
    ) -> None:
        self._running_checker = running_checker
        self._client_message_writer = client_message_writer

    async def __call__(self, notification: ClientNotification) -> None:
        self._running_checker()
        await self._client_message_writer(notification)
