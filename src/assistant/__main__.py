import asyncio
import logging
from contextlib import AsyncExitStack

from assistant.config import init_config
from assistant.db import init_engine, init_sessionmaker
from assistant.discord import init_discord
from assistant.discord_codex_service import DiscordCodexService
from assistant.discord_thread_links_service import DiscordThreadLinksService
from assistant.logging_ import init_logging
from assistant.parse_command_event import CommandExecutor
from assistant.stop_signal import init_stop_signals

logger = logging.getLogger(__name__)


async def main() -> None:
    async with AsyncExitStack() as stack:
        stop_event = stack.enter_context(init_stop_signals())
        config = await init_config()
        init_logging(config)
        engine = await stack.enter_async_context(init_engine(config))
        sessionmaker = init_sessionmaker(engine)
        discord_thread_links_service = DiscordThreadLinksService(sessionmaker)
        codex_executor = CommandExecutor()
        discord_codex_service = DiscordCodexService(
            discord_thread_links_service, codex_executor
        )
        await stack.enter_async_context(
            init_discord(config, discord_codex_service)
        )
        logger.info("Started.")
        await stop_event.wait()

    logger.info("Stopped.")


if __name__ == "__main__":
    asyncio.run(main())
