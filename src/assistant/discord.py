import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

import discord

from assistant.config import Config
from assistant.discord_codex_service import DiscordCodexService

logger = logging.getLogger(__name__)


class Discord(discord.Client):
    def __init__(
        self,
        *,
        config: Config,
        discord_codex_service: DiscordCodexService,
    ) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.members = True
        intents.guild_messages = True
        intents.message_content = True

        super().__init__(intents=intents)
        self._config = config
        self._discord_codex_service = discord_codex_service

    async def on_ready(self) -> None:
        logger.info("Logged in as %s", self.user)

    async def on_message(self, message: discord.Message) -> None:
        if (
            self.user  # logged in
            and message.author.id != self.user.id  # not sent by self
            and message.guild  # in a guild (not a DM)
            and message.guild.id
            == self._config.discord_guild_id  # in the specified guild
            and any(
                user.id == self.user.id for user in message.mentions
            )  # mentioned directly
        ):
            if isinstance(
                message.channel, discord.Thread
            ):  # already in a thread
                thread = message.channel
                await self._discord_codex_service.respond(
                    self.user, message, thread
                )
            elif isinstance(
                message.channel, discord.TextChannel
            ):  # not in a thread, but in a text channel
                raw = message.clean_content.strip().replace("\n", " ")
                name = raw[:100] or f"{message.author.display_name} thread"
                thread = await message.create_thread(name=name)
                await self._discord_codex_service.respond(
                    self.user, message, thread
                )


@contextlib.asynccontextmanager
async def init_discord(
    config: Config, discord_codex_service: DiscordCodexService
) -> AsyncIterator[Discord]:
    discord = Discord(
        config=config, discord_codex_service=discord_codex_service
    )
    connect_task: asyncio.Task[None] | None = None
    try:
        await discord.login(config.discord_token)
        connect_task = asyncio.create_task(discord.connect())
        await discord.wait_until_ready()

        yield discord
    finally:
        close_error: Exception | None = None
        try:
            await discord.close()
        except Exception as e:  # noqa: BLE001
            close_error = e
            if connect_task is not None:
                connect_task.cancel()

        if connect_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await connect_task

        if close_error:
            raise close_error
