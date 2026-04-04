from collections.abc import Sequence
from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class DiscordMentionTarget:
    discord_user_id: int
    display_name: str
    global_name: str | None
    user_name: str
    is_bot: bool = False


@dataclass(frozen=True, slots=True)
class TurnState:
    codex_turn_id: str
    codex_thread_id: str
    discord_thread_id: int
    has_sent_agent_message: bool = False


class MemoryStateStore:
    def __init__(self) -> None:
        self._codex_thread_ids_by_discord_thread_id: dict[int, str] = {}
        self._turns_by_codex_turn_id: dict[str, TurnState] = {}
        self._discord_mention_targets: tuple[DiscordMentionTarget, ...] = ()

    async def get_codex_thread_id(
        self, *, discord_thread_id: int
    ) -> str | None:
        return self._codex_thread_ids_by_discord_thread_id.get(
            discord_thread_id
        )

    async def set_codex_thread_id(
        self, *, discord_thread_id: int, codex_thread_id: str
    ) -> None:
        self._codex_thread_ids_by_discord_thread_id[discord_thread_id] = (
            codex_thread_id
        )

    async def create_turn(
        self,
        *,
        codex_turn_id: str,
        codex_thread_id: str,
        discord_thread_id: int,
    ) -> TurnState:
        turn = TurnState(
            codex_turn_id=codex_turn_id,
            codex_thread_id=codex_thread_id,
            discord_thread_id=discord_thread_id,
        )
        self._turns_by_codex_turn_id[codex_turn_id] = turn
        return turn

    async def get_turn(self, *, codex_turn_id: str) -> TurnState | None:
        return self._turns_by_codex_turn_id.get(codex_turn_id)

    async def mark_turn_sent_agent_message(
        self, *, codex_turn_id: str
    ) -> TurnState | None:
        turn = self._turns_by_codex_turn_id.get(codex_turn_id)
        if turn is None:
            return None

        turn = replace(turn, has_sent_agent_message=True)
        self._turns_by_codex_turn_id[codex_turn_id] = turn
        return turn

    async def delete_turn(self, *, codex_turn_id: str) -> None:
        self._turns_by_codex_turn_id.pop(codex_turn_id, None)

    async def replace_discord_mention_targets(
        self, *, mention_targets: Sequence[DiscordMentionTarget]
    ) -> None:
        self._discord_mention_targets = tuple(mention_targets)

    async def get_discord_mention_targets(
        self,
    ) -> tuple[DiscordMentionTarget, ...]:
        return self._discord_mention_targets
