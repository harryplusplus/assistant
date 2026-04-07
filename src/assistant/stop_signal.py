import asyncio
import logging
import signal
from collections.abc import Iterator
from contextlib import contextmanager

logger = logging.getLogger(__name__)


def _on_stop_signal(event: asyncio.Event, sig: signal.Signals) -> None:
    if event.is_set():
        return

    logger.info("Received stop signal: %s.", sig.name)
    event.set()


@contextmanager
def init_stop_signals(
    *,
    signals: tuple[signal.Signals, ...] = (signal.SIGINT, signal.SIGTERM),
) -> Iterator[asyncio.Event]:
    event = asyncio.Event()
    loop = asyncio.get_running_loop()
    try:
        for sig in signals:
            loop.add_signal_handler(sig, _on_stop_signal, event, sig)

        yield event
    finally:
        for sig in signals:
            loop.remove_signal_handler(sig)
