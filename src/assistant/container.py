from dishka import (
    AsyncContainer,
    Provider,
    Scope,
    from_context,
    make_async_container,
)

from assistant.config import Config
from assistant.db import DbProvider
from assistant.discord import DiscordProvider
from assistant.discord_service import DiscordService
from assistant.discord_thread_links_repo import DiscordThreadLinksRepo
from assistant.dishka_typing import provide


class AppProvider(Provider):
    scope = Scope.APP

    config = from_context(Config)
    discord_thread_links_repo = provide(DiscordThreadLinksRepo)
    discord_service = provide(DiscordService)


def create_container(config: Config) -> AsyncContainer:
    return make_async_container(
        DiscordProvider(),
        DbProvider(),
        AppProvider(),
        context={Config: config},
    )
