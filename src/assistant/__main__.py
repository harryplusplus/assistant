from dataclasses import dataclass

import discord
from dotenv import load_dotenv

from .config import Config
from .logger import configure_logger, get_assistant_logger

logger = get_assistant_logger()


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

    async def on_ready(self) -> None:
        if self.user is None:
            return
        logger.info("Logged in as %s (%s)", self.user, self.user.id)
        logger.info("Watching guild id=%s", self.context.config.discord_guild_id)

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


def main() -> None:
    load_dotenv()
    config = Config.from_env()
    configure_logger(config)
    context = Context(config=config)

    client = MentionPrinterClient(context=context)
    client.run(context.config.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
