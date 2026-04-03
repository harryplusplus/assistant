import asyncio
import logging
import signal
from contextlib import suppress
from dataclasses import dataclass
from functools import partial
from typing import TypeGuard

import discord
from dotenv import load_dotenv
from typing_extensions import override

from .codex.app_server import (
    CodexAppServer,
    ServerMessage,
    ServerRequestResponse,
)
from .codex.client import CodexClient
from .codex.schemas.codex_app_server_protocol_schemas import (
    ItemCompletedNotification,
    JsonrpcError,
    JsonrpcErrorError,
    ServerRequest,
    TextUserInput,
    TurnCompletedNotification,
    V2ThreadStartParams,
    V2TurnStartParams,
)
from .config import Config
from .logger import configure_logger
from .state_store import MemoryStateStore

logger = logging.getLogger(__name__)
_DISCORD_MESSAGE_LIMIT = 2000
_THREAD_TITLE_LIMIT = 60


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
    codex_client: CodexClient
    state_store: MemoryStateStore


class MentionPrinterClient(discord.Client):
    def __init__(self, *, context: Context) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.guild_messages = True
        intents.message_content = True
        super().__init__(intents=intents)
        self.context = context
        self.ready_event = asyncio.Event()
        self._turn_typing_tasks: dict[str, asyncio.Task[None]] = {}

    async def on_ready(self) -> None:
        if self.user is None:
            return
        logger.info("Logged in as %s (%s)", self.user, self.user.id)
        logger.info(
            "Watching guild id=%s", self.context.config.discord_guild_id
        )
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
            codex_thread_id = await self._ensure_codex_thread_id(
                discord_thread_id=discord_thread.id
            )

            async with discord_thread.typing():
                turn_response = await self.context.codex_client.start_turn(
                    V2TurnStartParams(
                        approvalPolicy="never",
                        threadId=codex_thread_id,
                        input=[TextUserInput(type="text", text=prompt)],
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

    @override
    async def close(self) -> None:
        typing_tasks = list(self._turn_typing_tasks.values())
        self._turn_typing_tasks.clear()
        for task in typing_tasks:
            task.cancel()
        for task in typing_tasks:
            with suppress(asyncio.CancelledError):
                await task
        await super().close()


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
    return f"{title[:_THREAD_TITLE_LIMIT - 3]}..."


def _render_output_text(text: str) -> str:
    if len(text) <= _DISCORD_MESSAGE_LIMIT:
        return text
    suffix = "\n...[truncated]"
    return f"{text[: _DISCORD_MESSAGE_LIMIT - len(suffix)]}{suffix}"


def _is_server_request(message: ServerMessage) -> TypeGuard[ServerRequest]:
    return hasattr(message, "id")


async def _get_discord_thread(
    *,
    client: MentionPrinterClient,
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


async def _handle_server_request(
    *,
    message: ServerMessage,
    server_request_response_queue: asyncio.Queue[ServerRequestResponse],
) -> None:
    if not _is_server_request(message):
        return

    logger.warning("Unsupported Codex server request: %s", message.method)
    server_request_response_queue.put_nowait(
        JsonrpcError(
            id=message.id,
            error=JsonrpcErrorError(
                code=-32000,
                message=f"Unsupported server request: {message.method}",
            ),
        )
    )


async def _handle_item_completed(
    *,
    client: MentionPrinterClient,
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
    client: MentionPrinterClient,
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
    client: MentionPrinterClient,
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


def _handle_shutdown_signal(
    stop_event: asyncio.Event, signum: signal.Signals
) -> None:
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
    state_store = MemoryStateStore()
    stop_event = asyncio.Event()
    server_message_queue: asyncio.Queue[ServerMessage] = asyncio.Queue()
    server_request_response_queue: asyncio.Queue[ServerRequestResponse] = (
        asyncio.Queue()
    )
    app_server = CodexAppServer(
        server_message_queue=server_message_queue,
        server_request_response_queue=server_request_response_queue,
    )
    codex_client = CodexClient(app_server=app_server)
    context = Context(
        config=config,
        codex_client=codex_client,
        state_store=state_store,
    )
    client = MentionPrinterClient(context=context)
    codex_server_message_task: asyncio.Task[None] | None = None
    discord_task: asyncio.Task[None] | None = None

    _install_signal_handlers(stop_event)

    try:
        await app_server.start()
        logger.info("Internal initialization completed")

        codex_server_message_task = asyncio.create_task(
            _consume_codex_server_messages(
                client=client,
                state_store=state_store,
                server_message_queue=server_message_queue,
                server_request_response_queue=server_request_response_queue,
            ),
            name="codex-server-messages",
        )

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
            await app_server.close()


def main() -> None:
    load_dotenv()
    config = Config.from_env()
    configure_logger(config)
    asyncio.run(_async_main(config))


if __name__ == "__main__":
    main()
