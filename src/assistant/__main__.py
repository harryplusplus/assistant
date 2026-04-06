import asyncio
import logging
from contextlib import suppress
from pathlib import Path

import discord
from dotenv import load_dotenv

from assistant import codex, event
from assistant.shutdown_signal import ShutdownSignal

from .codex.schemas.codex_app_server_protocol_schemas import (
    ItemCompletedNotification,
    TextUserInput,
    TurnCompletedNotification,
    V2ThreadStartParams,
    V2TurnStartParams,
)
from .config import Config
from .logging_ import setup_logging
from .state_store import DiscordMentionTarget, MemoryStateStore

logger = logging.getLogger(__name__)
_DISCORD_MESSAGE_LIMIT = 2000
_THREAD_TITLE_LIMIT = 60
_GUILD_MEMBER_CHUNK_TIMEOUT_SECONDS = 5.0


def _mentions_bot_user(*, message: discord.Message, bot_user_id: int) -> bool:
    return any(user.id == bot_user_id for user in message.mentions)


def _preview_text(text: str, *, limit: int = 30) -> str:
    preview = text.replace("\n", "\\n")
    if len(preview) <= limit:
        return preview
    return f"{preview[:limit]}..."


class Discord(discord.Client):
    def __init__(self, event_emitter: event.Emitter) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.members = True
        intents.guild_messages = True
        intents.message_content = True
        super().__init__(intents=intents)

        self._event_emitter = event_emitter

    def on_ready(self) -> None:
        self._event_emitter.emit(event.DiscordReady())

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

        prompt = _strip_bot_mention(
            content=message.content,
            bot_user_id=self.user.id,
        )
        if not prompt:
            await message.reply(
                "멘션 뒤에 메시지 내용을 넣어주세요.",
                mention_author=False,
            )
            return

        discord_thread: discord.Thread | None = None
        try:
            discord_thread = await self._ensure_discord_thread(
                message=message,
                prompt=prompt,
            )
            codex_prompt = _build_codex_prompt(
                message=message,
                prompt=prompt,
                bot_user_id=self.user.id,
                guild_mention_targets=(
                    await self.context.state_store.get_discord_mention_targets()
                ),
            )
            codex_thread_id = await self._ensure_codex_thread_id(
                discord_thread_id=discord_thread.id
            )

            async with discord_thread.typing():
                turn_response = await self.context.codex_client.start_turn(
                    V2TurnStartParams(
                        approvalPolicy="never",
                        threadId=codex_thread_id,
                        input=[TextUserInput(type="text", text=codex_prompt)],
                    )
                )
            await self.context.state_store.create_turn(
                codex_turn_id=turn_response.turn.id,
                codex_thread_id=codex_thread_id,
                discord_thread_id=discord_thread.id,
            )
            self.start_turn_typing(
                codex_turn_id=turn_response.turn.id,
                discord_thread=discord_thread,
            )
            logger.info(
                "Started Codex turn: discord_thread_id=%s "
                "codex_thread_id=%s codex_turn_id=%s",
                discord_thread.id,
                codex_thread_id,
                turn_response.turn.id,
            )
        except Exception:
            logger.exception("Failed to handle Discord mention.")
            if discord_thread is not None:
                await discord_thread.send("요청을 시작하지 못했습니다.")
            else:
                await message.reply(
                    "요청을 시작하지 못했습니다.",
                    mention_author=False,
                )

    async def _ensure_discord_thread(
        self, *, message: discord.Message, prompt: str
    ) -> discord.Thread:
        if isinstance(message.channel, discord.Thread):
            return message.channel

        return await message.create_thread(name=_build_thread_name(prompt))

    async def _ensure_codex_thread_id(self, *, discord_thread_id: int) -> str:
        codex_thread_id = await self.context.state_store.get_codex_thread_id(
            discord_thread_id=discord_thread_id
        )
        if codex_thread_id is not None:
            return codex_thread_id

        thread_response = await self.context.codex_client.start_thread(
            V2ThreadStartParams(approvalPolicy="never")
        )
        codex_thread_id = thread_response.thread.id
        await self.context.state_store.set_codex_thread_id(
            discord_thread_id=discord_thread_id,
            codex_thread_id=codex_thread_id,
        )
        logger.info(
            "Bound Discord thread to Codex thread: "
            "discord_thread_id=%s codex_thread_id=%s",
            discord_thread_id,
            codex_thread_id,
        )
        return codex_thread_id

    async def _refresh_guild_mention_targets(self) -> None:
        guild = self.get_guild(self.context.config.discord_guild_id)
        if guild is None:
            logger.warning(
                "Target guild is not available in cache: guild_id=%s",
                self.context.config.discord_guild_id,
            )
            return

        try:
            members = await asyncio.wait_for(
                guild.chunk(cache=True),
                timeout=_GUILD_MEMBER_CHUNK_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.warning(
                "Timed out while chunking guild members: guild_id=%s. "
                "Using cached guild.members snapshot instead. "
                "Check that Server Members Intent is enabled in the "
                "Discord Developer Portal.",
                guild.id,
            )
            members = guild.members
        mention_targets = tuple(
            sorted(
                (
                    DiscordMentionTarget(
                        discord_user_id=member.id,
                        display_name=member.display_name,
                        global_name=member.global_name,
                        user_name=member.name,
                        is_bot=member.bot,
                    )
                    for member in members
                ),
                key=lambda member: (
                    member.display_name.casefold(),
                    member.user_name.casefold(),
                    member.discord_user_id,
                ),
            )
        )
        await self.context.state_store.replace_discord_mention_targets(
            mention_targets=mention_targets
        )
        logger.info(
            "Loaded guild mention targets: guild_id=%s count=%s targets=%s",
            guild.id,
            len(mention_targets),
            _format_discord_mention_targets_log(mention_targets),
        )

    def start_turn_typing(
        self, *, codex_turn_id: str, discord_thread: discord.Thread
    ) -> None:
        existing_task = self._turn_typing_tasks.pop(codex_turn_id, None)
        if existing_task is not None:
            existing_task.cancel()

        self._turn_typing_tasks[codex_turn_id] = asyncio.create_task(
            self._typing_loop(discord_thread=discord_thread),
            name=f"discord-typing-{codex_turn_id}",
        )

    async def stop_turn_typing(self, *, codex_turn_id: str) -> None:
        task = self._turn_typing_tasks.pop(codex_turn_id, None)
        if task is None:
            return

        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def _typing_loop(self, *, discord_thread: discord.Thread) -> None:
        try:
            async with discord_thread.typing():
                await asyncio.get_running_loop().create_future()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Failed to send typing indicator: discord_thread_id=%s",
                discord_thread.id,
            )


def _strip_bot_mention(*, content: str, bot_user_id: int) -> str:
    stripped = content.replace(f"<@{bot_user_id}>", "").replace(
        f"<@!{bot_user_id}>",
        "",
    )
    return stripped.strip()


def _build_thread_name(prompt: str) -> str:
    title = prompt.replace("\n", " ").strip()
    if not title:
        return "assistant"
    if len(title) <= _THREAD_TITLE_LIMIT:
        return title
    return f"{title[: _THREAD_TITLE_LIMIT - 3]}..."


def _build_codex_prompt(
    *,
    message: discord.Message,
    prompt: str,
    bot_user_id: int,
    guild_mention_targets: tuple[DiscordMentionTarget, ...],
) -> str:
    mention_lines = [
        f"- {user.display_name}: <@{user.id}>"
        for user in message.mentions
        if user.id not in {message.author.id, bot_user_id}
    ]
    mention_targets = "\n".join(mention_lines) if mention_lines else "- none"
    guild_mention_target_lines = [
        _format_discord_mention_target(mention_target)
        for mention_target in guild_mention_targets
    ]
    guild_mention_targets_text = (
        "\n".join(guild_mention_target_lines)
        if guild_mention_target_lines
        else "- none"
    )

    return (
        "디스코드 문맥:\n"
        f"- 현재 발화자의 Discord user id는 {message.author.id} 입니다.\n"
        f"- 현재 발화자는 {'봇' if message.author.bot else '사람'} 입니다.\n"
        "- 현재 발화자가 사람이라면 자동으로 멘션하지 마세요.\n"
        "- 현재 발화자가 다른 봇이라면, 그 봇에게 직접 답하는 경우 답변의 "
        "첫머리에서 <@발화자ID>로 멘션하세요.\n"
        "- 이 메시지는 이미 너에게 전달된 메시지입니다. 호출용으로 붙은 "
        "너 자신의 멘션은 무시하고, 답변에 다시 자기 자신을 멘션하지 마세요.\n"
        "- 사용자가 특정 길드 멤버에게 말을 걸라고 하면, 아래 "
        "'길드 멘션 대상 목록'의 실제 Discord 멘션 <@ID>를 사용하세요.\n"
        "- 사용자가 특정 대상에게 말을 걸라고 했다면, 답변의 첫머리에서 그 "
        "대상을 실제 Discord 멘션 <@ID>로 부르세요.\n"
        "- 이름 문자열이나 @이름 형태만 쓰지 말고 실제 Discord 멘션 "
        "<@ID>를 사용하세요.\n"
        "- 실제 Discord 멘션은 사용자가 명시적으로 누군가를 지목했을 때만 "
        "사용하세요.\n"
        "- 현재 발화자를 멘션해야 할 때는 "
        f"<@{message.author.id}> 를 사용하세요.\n"
        "- display name 문자열만으로는 실제 멘션이 되지 않습니다.\n"
        "예시:\n"
        "- 현재 발화자가 다른 봇이고, 그 봇에게 직접 응답하는 상황이면 "
        "'<@발화자ID> ...'처럼 답변을 시작하세요.\n"
        "- 사용자가 'Hermes한테 인사해봐'라고 했고, 길드 멘션 대상 목록에 "
        "'Hermes: <@123>'가 있다면, 답변은 'Hermes 안녕!'이 아니라 "
        "'<@123> 안녕!'처럼 실제 멘션을 사용하세요.\n"
        "- 사용자가 'Hermes랑 이야기좀해봐'라고 했고, 길드 멘션 대상 목록에 "
        "'Hermes: <@123>'가 있다면, 답변은 '<@123> 안녕하세요. 잠깐 "
        "이야기 가능하시면 답해주세요.'처럼 대상 멘션으로 시작하세요.\n"
        "- 사용자가 'B에게 현재 상태 물어봐'라고 했고, 길드 멘션 대상 "
        "목록에 'B: <@456>'가 있다면, '<@456> 현재 상태 어때?'처럼 "
        "답하세요.\n"
        "현재 메시지에서 이미 멘션된 대상:\n"
        f"{mention_targets}\n"
        "길드 멘션 대상 목록:\n"
        f"{guild_mention_targets_text}\n"
        "\n"
        "사용자 메시지:\n"
        f"{prompt}"
    )


def _get_discord_mention_target_aliases(
    mention_target: DiscordMentionTarget,
) -> tuple[str, ...]:
    aliases = [mention_target.display_name]
    if mention_target.global_name is not None:
        aliases.append(mention_target.global_name)
    if mention_target.user_name not in aliases:
        aliases.append(mention_target.user_name)
    return tuple(aliases)


def _format_discord_mention_target(
    mention_target: DiscordMentionTarget,
) -> str:
    aliases = list(_get_discord_mention_target_aliases(mention_target))
    primary_name = aliases.pop(0)
    alias_suffix = ""
    if aliases:
        alias_suffix = f" (aliases: {', '.join(aliases)})"
    bot_suffix = " (bot)" if mention_target.is_bot else ""
    return (
        f"- {primary_name}{alias_suffix}{bot_suffix}: "
        f"<@{mention_target.discord_user_id}>"
    )


def _format_discord_mention_targets_log(
    mention_targets: tuple[DiscordMentionTarget, ...],
) -> str:
    if not mention_targets:
        return "-"

    return ", ".join(
        f"{mention_target.display_name}(<@{mention_target.discord_user_id}>)"
        for mention_target in mention_targets
    )


def _render_output_text(text: str) -> str:
    if len(text) <= _DISCORD_MESSAGE_LIMIT:
        return text
    suffix = "\n...[truncated]"
    return f"{text[: _DISCORD_MESSAGE_LIMIT - len(suffix)]}{suffix}"


async def _get_discord_thread(
    *,
    client: Discord,
    discord_thread_id: int,
) -> discord.Thread | None:
    channel = client.get_channel(discord_thread_id)
    if channel is None:
        channel = await client.fetch_channel(discord_thread_id)

    if not isinstance(channel, discord.Thread):
        logger.warning(
            "Expected Discord thread channel: id=%s type=%s",
            discord_thread_id,
            type(channel).__name__,
        )
        return None

    return channel


async def _handle_item_completed(
    *,
    client: Discord,
    state_store: MemoryStateStore,
    notification: ItemCompletedNotification,
) -> None:
    item = notification.params.item
    if getattr(item, "type", None) != "agentMessage":
        return

    text = getattr(item, "text", None)
    if not isinstance(text, str):
        return

    if not text:
        return

    turn = await state_store.get_turn(codex_turn_id=notification.params.turnId)
    if turn is None:
        return

    discord_thread = await _get_discord_thread(
        client=client,
        discord_thread_id=turn.discord_thread_id,
    )
    if discord_thread is None:
        return

    await discord_thread.send(_render_output_text(text))
    await state_store.mark_turn_sent_agent_message(
        codex_turn_id=notification.params.turnId
    )


async def _handle_turn_completed(
    *,
    client: Discord,
    state_store: MemoryStateStore,
    notification: TurnCompletedNotification,
) -> None:
    turn = await state_store.get_turn(codex_turn_id=notification.params.turn.id)
    if turn is None:
        return

    await client.stop_turn_typing(codex_turn_id=notification.params.turn.id)

    turn_error = notification.params.turn.error
    if turn_error is not None and not turn.has_sent_agent_message:
        discord_thread = await _get_discord_thread(
            client=client,
            discord_thread_id=turn.discord_thread_id,
        )
        if discord_thread is not None:
            await discord_thread.send(
                _render_output_text(f"Error: {turn_error.message}")
            )

    await state_store.delete_turn(codex_turn_id=notification.params.turn.id)


async def _consume_codex_server_messages(
    *,
    client: Discord,
    state_store: MemoryStateStore,
    server_message_queue: asyncio.Queue[ServerMessage],
    server_request_response_queue: asyncio.Queue[ServerRequestResponse],
) -> None:
    while True:
        message = await server_message_queue.get()

        try:
            if isinstance(message, ItemCompletedNotification):
                await _handle_item_completed(
                    client=client,
                    state_store=state_store,
                    notification=message,
                )
            elif isinstance(message, TurnCompletedNotification):
                await _handle_turn_completed(
                    client=client,
                    state_store=state_store,
                    notification=message,
                )
            else:
                await _handle_server_request(
                    message=message,
                    server_request_response_queue=server_request_response_queue,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Failed to handle Codex server message: %s",
                getattr(message, "method", type(message).__name__),
            )


async def _wait_for_discord_ready(
    *,
    client: Discord,
    discord_task: asyncio.Task[None],
    stop_event: asyncio.Event,
) -> bool:
    ready_task = asyncio.create_task(
        client.ready_event.wait(), name="discord-ready"
    )
    stop_task = asyncio.create_task(stop_event.wait(), name="shutdown-wait")
    done, pending = await asyncio.wait(
        {ready_task, stop_task, discord_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in (ready_task, stop_task):
        if task in pending:
            task.cancel()
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

    if stop_task in pending:
        stop_task.cancel()
        with suppress(asyncio.CancelledError):
            await stop_task

    if discord_task in done:
        await discord_task
        msg = "discord client exited unexpectedly."
        raise RuntimeError(msg)


async def _async_main(config: Config) -> None:
    shutdown_signal = ShutdownSignal()
    shutdown_signal.install()

    event_service = event.Service()
    codex_app_server = codex.AppServer(event_emitter=event_service.emitter)
    codex_client_request_registry = codex.client_request.Context()

    event_service.register_handler(
        codex.server_message.Handler(codex_client_request_registry),
    )

    try:
        event_service.start()
        await codex_app_server.start()
        codex_client = codex.create_client(
            app_server=codex_app_server,
            client_request_registry=codex_client_request_registry,
        )
        client = Discord(context=context)

        codex_server_message_task = asyncio.create_task(
            _consume_codex_server_messages(
                client=client,
                state_store=state_store,
                server_message_queue=server_message_queue,
                server_request_response_queue=server_request_response_queue,
            ),
            name="codex-server-messages",
        )

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

        await shutdown_signal.wait()
        logger.info("Shutdown signal received, starting graceful shutdown")
    finally:
        try:
            if codex_server_message_task is not None:
                codex_server_message_task.cancel()
                with suppress(asyncio.CancelledError):
                    await codex_server_message_task

            if discord_task is not None:
                logger.info("Starting external graceful shutdown")
                await client.close()
                await discord_task
        finally:
            logger.info("Starting internal graceful shutdown")
            await codex_app_server.close()


def main() -> None:
    load_dotenv(dotenv_path=Path.cwd() / ".env")
    config = Config.from_env()
    setup_logging(config)
    asyncio.run(_async_main(config))


if __name__ == "__main__":
    main()
