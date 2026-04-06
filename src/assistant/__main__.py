import asyncio
import logging

from assistant.container import create_container
from assistant.discord import Discord
from assistant.log import LogInitToken
from assistant.stop_signal import install_stop_signal_handlers

logger = logging.getLogger(__name__)


async def _run() -> None:
    stop_event = asyncio.Event()
    install_stop_signal_handlers(stop_event)

    async with create_container() as container:
        await container.get(LogInitToken)
        await container.get(Discord)
        logger.info("Started.")

        await stop_event.wait()

    logger.info("Stopped.")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
