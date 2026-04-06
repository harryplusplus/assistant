from dishka import AsyncContainer, Provider, Scope, make_async_container

from assistant.config import ConfigProvider
from assistant.db import DbProvider
from assistant.discord import DiscordProvider
from assistant.discord_service import DiscordService
from assistant.discord_thread_links_repo import DiscordThreadLinksRepo
from assistant.dishka_typing import provide


class AppProvider(Provider):
    scope = Scope.APP

    discord_thread_links_repo = provide(DiscordThreadLinksRepo)
    discord_service = provide(DiscordService)


def create_container() -> AsyncContainer:
    return make_async_container(
        ConfigProvider(),
        DiscordProvider(),
        DbProvider(),
        AppProvider(),
    )
