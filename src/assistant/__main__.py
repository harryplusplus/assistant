import asyncio
import logging

from assistant.config import Config
from assistant.container import create_container
from assistant.discord import Discord
from assistant.log import init_log, set_log_level
from assistant.stop_signal import install_stop_signal_handlers

logger = logging.getLogger(__name__)


async def _run() -> None:
    stop_event = asyncio.Event()
    install_stop_signal_handlers(stop_event)

    async with create_container() as container:
        config = await container.get(Config)
        set_log_level(config.log_level)

        await container.get(Discord)
        logger.info("Started.")

        await stop_event.wait()

    logger.info("Stopped.")


def main() -> None:
    init_log()
    asyncio.run(_run())


if __name__ == "__main__":
    main()
