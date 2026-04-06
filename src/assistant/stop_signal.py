import asyncio
import logging
import signal

logger = logging.getLogger(__name__)


def _on_stop_signal(stop_event: asyncio.Event, signum: signal.Signals) -> None:
    if stop_event.is_set():
        return

    logger.info("Received stop signal: %s.", signum.name)
    stop_event.set()


def install_stop_signal_handlers(
    stop_event: asyncio.Event,
    *,
    signals: tuple[signal.Signals, ...] = (signal.SIGINT, signal.SIGTERM),
) -> None:
    loop = asyncio.get_running_loop()
    for signum in signals:
        loop.add_signal_handler(signum, _on_stop_signal, stop_event, signum)
