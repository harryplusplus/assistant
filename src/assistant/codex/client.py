from .app_server import CLIENT_REQUEST_ID_PLACEHOLDER, CodexAppServer
from .schemas.codex_app_server_protocol_schemas import (
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


class CodexClient:
    def __init__(self, *, app_server: CodexAppServer) -> None:
        self._app_server = app_server

    async def start_thread(
        self,
        params: V2ThreadStartParams,
    ) -> V2ThreadStartResponse:
        return await self._app_server.send_request(
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
        return await self._app_server.send_request(
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
        return await self._app_server.send_request(
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
        return await self._app_server.send_request(
            TurnStartRequest(
                id=CLIENT_REQUEST_ID_PLACEHOLDER,
                method="turn/start",
                params=params,
            ),
            V2TurnStartResponse,
        )
