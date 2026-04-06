from assistant.codex.app_server.consumer import JsonlConsumer
from assistant.codex.app_server.process import Process


class RunningChecker:
    def __init__(
        self,
        process: Process,
        stdout_consumer: JsonlConsumer,
    ) -> None:
        self._process = process
        self._stdout_consumer = stdout_consumer

    def __call__(self) -> None:
        if not self._process.running or not self._stdout_consumer.running:
            msg = "App server process or stdout consumer is not running"
            raise RuntimeError(msg)
