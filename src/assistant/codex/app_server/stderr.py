import asyncio
from typing import override

from assistant.codex.app_server import consumer


class StderrHandler(consumer.Handler):
    @override
    def __call__(self, context: consumer.HandlerContext, json: bytes) -> None:
        context.logger.error(json.decode(errors="replace"))


def create_stderr_consumer(
    stderr: asyncio.StreamReader,
) -> consumer.JsonlConsumer:
    handler = StderrHandler()
    return consumer.JsonlConsumer(
        name="StderrConsumer", reader=stderr, handler=handler
    )
