from dishka import AsyncContainer, make_async_container

from assistant.config import ConfigProvider
from assistant.discord import DiscordProvider


def create_container() -> AsyncContainer:
    return make_async_container(ConfigProvider(), DiscordProvider())
