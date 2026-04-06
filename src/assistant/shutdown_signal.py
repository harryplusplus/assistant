import asyncio
import logging
import signal

logger = logging.getLogger(__name__)


class ShutdownSignal:
    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._signals = (signal.SIGINT, signal.SIGTERM)

    def install(self) -> None:
        loop = asyncio.get_running_loop()
        for signum in self._signals:
            loop.add_signal_handler(signum, self._on_signal, signum)

    async def wait(self) -> None:
        await self._event.wait()

    def _on_signal(self, signum: signal.Signals) -> None:
        if self._event.is_set():
            return

        logger.info("Received shutdown signal: %s", signum.name)
        self._event.set()
