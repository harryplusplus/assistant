import asyncio
import contextlib
import logging
from collections.abc import AsyncIterable

import discord
from dishka import Provider, Scope

from assistant.config import Config
from assistant.dishka_typing import provide

logger = logging.getLogger(__name__)


class Discord(discord.Client):
    def __init__(self, *, config: Config) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.members = True
        intents.guild_messages = True
        intents.message_content = True

        super().__init__(intents=intents)
        self._config = config

    async def on_ready(self) -> None:
        logger.info("Logged in as %s", self.user)

    async def on_message(self, message: discord.Message) -> None:
        logger.debug("Received message %s", message)


class DiscordProvider(Provider):
    scope = Scope.APP

    @provide()
    async def get_discord(self, config: Config) -> AsyncIterable[Discord]:
        discord = Discord(config=config)
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
