import asyncio
import logging

from assistant.config import load_config
from assistant.container import create_container
from assistant.discord import Discord
from assistant.log import configure_logging
from assistant.stop_signal import install_stop_signal_handlers

logger = logging.getLogger(__name__)


async def _run() -> None:
    stop_event = asyncio.Event()
    install_stop_signal_handlers(stop_event)

    config = await load_config()
    configure_logging(config)

    async with create_container(config) as container:
        await container.get(Discord)
        logger.info("Started.")
        await stop_event.wait()

    logger.info("Stopped.")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
