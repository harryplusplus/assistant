import json
import logging

import discord

from assistant.codex_exec import codex_exec
from assistant.discord_thread_links_repo import DiscordThreadLinksRepo

logger = logging.getLogger(__name__)


class DiscordService:
    def __init__(
        self, discord_thread_links_repo: DiscordThreadLinksRepo
    ) -> None:
        self._discord_thread_links_repo = discord_thread_links_repo

    async def respond(
        self,
        user: discord.ClientUser,
        message: discord.Message,
        thread: discord.Thread,
    ) -> None:
        try:
            await message.add_reaction("👀")
            async with thread.typing():
                codex_session_id = (
                    await self._discord_thread_links_repo.get_codex_session_id(
                        discord_thread_id=thread.id
                    )
                )

                response = ""
                async for event in codex_exec(
                    message.clean_content, session_id=codex_session_id
                ):
                    if event.kind == "stderr":
                        logger.error("Error from codex_exec: %s", event.data)
                        continue

                    if event.data is None:
                        continue

                    json_str = event.data.rstrip().decode(errors="replace")
                    logger.debug("Received event from codex_exec: %s", json_str)

                    json_data = json.loads(json_str)
                    type_ = json_data["type"]
                    if type_ == "thread.started":
                        if codex_session_id is None:
                            await self._discord_thread_links_repo.create(
                                discord_thread_id=thread.id,
                                codex_session_id=json_data["thread_id"],
                            )
                    elif type_ == "item.completed":
                        item = json_data["item"]
                        item_type = item["type"]
                        if item_type == "agent_message":
                            response += item["text"]

                await thread.send(response or "No response")
        except Exception as e:
            logger.exception("Error while responding to message")
            await thread.send(
                f"An error occurred while processing the message: {e}"
            )
            await message.add_reaction("❌")
        else:
            await message.add_reaction("✅")
        finally:
            await message.remove_reaction("👀", user)
