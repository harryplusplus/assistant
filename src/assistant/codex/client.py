import logging
from importlib.metadata import version

from assistant.codex import client_notification, client_request
from assistant.codex.app_server.app_server import AppServer
from assistant.codex.common import CLIENT_REQUEST_ID_PLACEHOLDER

from .schemas.codex_app_server_protocol_schemas import (
    ClientInfo,
    InitializedNotification,
    InitializeParams,
    InitializeRequest,
    InitializeResponse,
    ThreadReadRequest,
    ThreadResumeRequest,
    ThreadStartRequest,
    TurnStartRequest,
    V2ThreadReadParams,
    V2ThreadReadResponse,
    V2ThreadResumeParams,
    V2ThreadResumeResponse,
    V2ThreadStartParams,
    V2ThreadStartResponse,
    V2TurnStartParams,
    V2TurnStartResponse,
)

logger = logging.getLogger(__name__)


class Client:
    def __init__(
        self,
        client_request_sender: client_request.Sender,
        client_notification_sender: client_notification.Sender,
    ) -> None:
        self._client_request_sender = client_request_sender
        self._client_notification_sender = client_notification_sender

    async def initialize(self) -> InitializeResponse:
        return await self._client_request_sender(
            InitializeRequest(
                id=CLIENT_REQUEST_ID_PLACEHOLDER,
                method="initialize",
                params=InitializeParams(
                    clientInfo=ClientInfo(
                        name="assistant",
                        title="Assistant",
                        version=version("assistant"),
                    )
                ),
            ),
            InitializeResponse,
        )

    async def initialized(self) -> None:
        await self._client_notification_sender(
            InitializedNotification(method="initialized")
        )

    async def start_thread(
        self,
        params: V2ThreadStartParams,
    ) -> V2ThreadStartResponse:
        return await self._client_request_sender(
            ThreadStartRequest(
                id=CLIENT_REQUEST_ID_PLACEHOLDER,
                method="thread/start",
                params=params,
            ),
            V2ThreadStartResponse,
        )

    async def resume_thread(
        self,
        params: V2ThreadResumeParams,
    ) -> V2ThreadResumeResponse:
        return await self._client_request_sender(
            ThreadResumeRequest(
                id=CLIENT_REQUEST_ID_PLACEHOLDER,
                method="thread/resume",
                params=params,
            ),
            V2ThreadResumeResponse,
        )

    async def read_thread(
        self,
        *,
        thread_id: str,
        include_turns: bool = True,
    ) -> V2ThreadReadResponse:
        return await self._client_request_sender(
            ThreadReadRequest(
                id=CLIENT_REQUEST_ID_PLACEHOLDER,
                method="thread/read",
                params=V2ThreadReadParams(
                    includeTurns=include_turns,
                    threadId=thread_id,
                ),
            ),
            V2ThreadReadResponse,
        )

    async def start_turn(
        self,
        params: V2TurnStartParams,
    ) -> V2TurnStartResponse:
        return await self._client_request_sender(
            TurnStartRequest(
                id=CLIENT_REQUEST_ID_PLACEHOLDER,
                method="turn/start",
                params=params,
            ),
            V2TurnStartResponse,
        )


def create_client(
    app_server: AppServer, client_request_registry: client_request.Context
) -> Client:
    app_server_running_checker = app_server.create_running_checker()
    client_request_sender = client_request.Sender(
        app_server_running_checker,
        app_server.stdin_writer,
        client_request_registry,
    )
    client_notification_sender = client_notification.Sender(
        app_server_running_checker, app_server.stdin_writer
    )
    return Client(
        client_request_sender=client_request_sender,
        client_notification_sender=client_notification_sender,
    )
