import asyncio
from typing import override

from pydantic import TypeAdapter

from assistant import event
from assistant.codex.app_server import consumer
from assistant.codex.schemas.codex_app_server_protocol_schemas import (
    JsonrpcMessage,
)

_MESSAGE_ADAPTER: TypeAdapter[JsonrpcMessage] = TypeAdapter(JsonrpcMessage)


class StdoutHandler(consumer.Handler):
    def __init__(
        self,
        event_emitter: event.Emitter,
    ) -> None:
        self._event_emitter = event_emitter

    @override
    def __call__(self, context: consumer.HandlerContext, json: bytes) -> None:
        message = _MESSAGE_ADAPTER.validate_json(json)
        self._event_emitter.emit(event.CodexServerMessage(message=message))


def create_stdout_consumer(
    stdout: asyncio.StreamReader, event_emitter: event.Emitter
) -> consumer.JsonlConsumer:
    handler = StdoutHandler(event_emitter=event_emitter)
    return consumer.JsonlConsumer(
        name="StdoutConsumer", reader=stdout, handler=handler
    )
