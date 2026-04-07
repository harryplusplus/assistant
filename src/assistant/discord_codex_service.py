import logging

import discord

from assistant.codex_executor import CodexExecutor
from assistant.discord_thread_links_service import DiscordThreadLinksService

logger = logging.getLogger(__name__)


DISCORD_MESSAGE_MAX_LENGTH = 2000


class DiscordCodexService:
    def __init__(
        self,
        discord_thread_links_service: DiscordThreadLinksService,
        codex_executor: CodexExecutor,
    ) -> None:
        self._discord_thread_links_service = discord_thread_links_service
        self._codex_executor = codex_executor

    async def respond(  # noqa: C901, PLR0912
        self,
        user: discord.ClientUser,
        message: discord.Message,
        thread: discord.Thread,
    ) -> None:
        try:
            await message.add_reaction("👀")
            async with thread.typing():
                discord_thread_id = thread.id
                discord_thread_link = (
                    await self._discord_thread_links_service.find(
                        discord_thread_id=discord_thread_id
                    )
                )
                codex_session_id = (
                    discord_thread_link.codex_session_id
                    if discord_thread_link is not None
                    else None
                )

                async for data in self._codex_executor.execute(
                    message.clean_content,
                    session_id=codex_session_id,
                    metadata={"discord_thread_id": discord_thread_id},
                ):
                    type_ = data["type"]
                    if type_ == "thread.started":
                        if discord_thread_link is None:
                            await self._discord_thread_links_service.create(
                                discord_thread_id=discord_thread_id,
                                codex_session_id=data["thread_id"],
                            )
                    elif type_ == "item.completed":
                        item = data["item"]
                        item_type = item["type"]
                        if item_type == "agent_message":
                            await self._send_text_split(thread, item["text"])
                        elif item_type == "web_search":
                            text = f"🔍 **{item_type}** {item['query'][:100]}"
                            await self._send_text_split(thread, text)
                        elif item_type == "mcp_tool_call":
                            text = f"🛠️ **{item_type}** {item['tool']}"
                            await self._send_text_split(thread, text)
                        elif item_type == "collab_tool_call":
                            text = f"🤝 **{item_type}** {item['tool']}"
                            await self._send_text_split(thread, text)
                        elif item_type == "command_execution":
                            text = (
                                f"⌨️ **{item_type}** `{item['command'][:100]}`"
                            )
                            await self._send_text_split(thread, text)
                        else:
                            await self._send_text_split(
                                thread, f"❓ Unknown item type: {item_type}"
                            )
                    elif type_ == "turn.completed":
                        usage = data["usage"]
                        input_tokens = usage["input_tokens"]
                        cached_input_tokens = usage["cached_input_tokens"]
                        output_tokens = usage["output_tokens"]
                        inout_tokens = input_tokens + output_tokens
                        text = (
                            f"💵 **토큰 사용량**\n"
                            f"- 입력: {input_tokens}\n"
                            f"- 🌟 캐시된 입력: {cached_input_tokens}\n"
                            f"- 출력: {output_tokens}\n"
                            f"- 입력+출력: {inout_tokens}"
                        )
                        await self._send_text_split(thread, text)
                    elif type_ in {"turn.started", "item.started"}:
                        pass
                    else:
                        await self._send_text_split(
                            thread, f"❓ Unknown event type: {type_}"
                        )
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

    async def _send_text_split(self, thread: discord.Thread, text: str) -> None:
        for i in range(0, len(text), DISCORD_MESSAGE_MAX_LENGTH):
            await thread.send(text[i : i + DISCORD_MESSAGE_MAX_LENGTH])
