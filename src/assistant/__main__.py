import asyncio
import logging
import signal
from contextlib import suppress
from dataclasses import dataclass
from functools import partial

import discord
from dotenv import load_dotenv

from .codex import Codex
from .config import Config
from .logger import configure_logger

logger = logging.getLogger(__name__)


def _mentions_bot_user(*, message: discord.Message, bot_user_id: int) -> bool:
    return any(user.id == bot_user_id for user in message.mentions)


def _preview_text(text: str, *, limit: int = 30) -> str:
    preview = text.replace("\n", "\\n")
    if len(preview) <= limit:
        return preview
    return f"{preview[:limit]}..."


@dataclass(frozen=True, slots=True)
class Context:
    config: Config


class MentionPrinterClient(discord.Client):
    def __init__(self, *, context: Context) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.guild_messages = True
        intents.message_content = True
        super().__init__(intents=intents)
        self.context = context
        self.ready_event = asyncio.Event()

    async def on_ready(self) -> None:
        if self.user is None:
            return
        logger.info("Logged in as %s (%s)", self.user, self.user.id)
        logger.info("Watching guild id=%s", self.context.config.discord_guild_id)
        self.ready_event.set()

    async def on_message(self, message: discord.Message) -> None:
        logger.debug(
            "on_message: author=%s guild_id=%s guild_name=%s channel_id=%s "
            "channel_name=%s preview=%s",
            message.author,
            getattr(message.guild, "id", None),
            getattr(message.guild, "name", None),
            message.channel.id,
            getattr(message.channel, "name", None),
            _preview_text(message.content),
        )

        if self.user is None:
            return

        if message.guild is None:
            return

        if message.author.id == self.user.id:
            return

        if message.guild.id != self.context.config.discord_guild_id:
            return

        if not _mentions_bot_user(
            message=message,
            bot_user_id=self.user.id,
        ):
            return

        logger.info("[%s] %s: %s", message.channel, message.author, message.content)


def _handle_shutdown_signal(stop_event: asyncio.Event, signum: signal.Signals) -> None:
    if stop_event.is_set():
        return
    logger.info("Received shutdown signal: %s", signum.name)
    stop_event.set()


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(
                signum,
                partial(_handle_shutdown_signal, stop_event, signum),
            )
        except NotImplementedError:
            logger.warning("Signal handlers are not supported on this platform")
            return


async def _wait_for_discord_ready(
    *,
    client: MentionPrinterClient,
    discord_task: asyncio.Task[None],
    stop_event: asyncio.Event,
) -> bool:
    ready_task = asyncio.create_task(client.ready_event.wait(), name="discord-ready")
    stop_task = asyncio.create_task(stop_event.wait(), name="shutdown-wait")
    done, pending = await asyncio.wait(
        {ready_task, stop_task, discord_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        task.cancel()
    for task in pending:
        with suppress(asyncio.CancelledError):
            await task

    if discord_task in done:
        await discord_task
        msg = "discord client exited before initialization completed."
        raise RuntimeError(msg)

    return ready_task in done


async def _wait_for_shutdown(
    *,
    stop_event: asyncio.Event,
    discord_task: asyncio.Task[None],
) -> None:
    stop_task = asyncio.create_task(stop_event.wait(), name="shutdown-wait")
    done, pending = await asyncio.wait(
        {stop_task, discord_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        task.cancel()
    for task in pending:
        with suppress(asyncio.CancelledError):
            await task

    if discord_task in done:
        await discord_task
        msg = "discord client exited unexpectedly."
        raise RuntimeError(msg)


async def _async_main(config: Config) -> None:
    context = Context(config=config)
    stop_event = asyncio.Event()
    codex = Codex()
    client = MentionPrinterClient(context=context)
    discord_task: asyncio.Task[None] | None = None

    _install_signal_handlers(stop_event)

    try:
        await codex.start()
        logger.info("Internal initialization completed")

        if stop_event.is_set():
            return

        discord_task = asyncio.create_task(
            client.start(context.config.discord_token),
            name="discord-client",
        )
        discord_ready = await _wait_for_discord_ready(
            client=client,
            discord_task=discord_task,
            stop_event=stop_event,
        )
        if not discord_ready:
            return
        logger.info("External initialization completed")

        await _wait_for_shutdown(
            stop_event=stop_event,
            discord_task=discord_task,
        )
    finally:
        try:
            if discord_task is not None:
                logger.info("Starting external graceful shutdown")
                await client.close()
                await discord_task
        finally:
            logger.info("Starting internal graceful shutdown")
            await codex.close()


def main() -> None:
    load_dotenv()
    config = Config.from_env()
    configure_logger(config)
    asyncio.run(_async_main(config))


if __name__ == "__main__":
    main()
