from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class TurnOutputState:
    codex_turn_id: str
    codex_thread_id: str
    discord_thread_channel_id: int
    discord_message_id: int
    agent_message_item_id: str | None = None
    text: str = ""


class MemoryStateStore:
    def __init__(self) -> None:
        self._codex_thread_ids_by_discord_thread_channel_id: dict[int, str] = (
            {}
        )
        self._turn_outputs_by_codex_turn_id: dict[str, TurnOutputState] = {}

    async def get_codex_thread_id(
        self, *, discord_thread_channel_id: int
    ) -> str | None:
        return self._codex_thread_ids_by_discord_thread_channel_id.get(
            discord_thread_channel_id
        )

    async def set_codex_thread_id(
        self, *, discord_thread_channel_id: int, codex_thread_id: str
    ) -> None:
        self._codex_thread_ids_by_discord_thread_channel_id[
            discord_thread_channel_id
        ] = codex_thread_id

    async def create_turn_output(
        self,
        *,
        codex_turn_id: str,
        codex_thread_id: str,
        discord_thread_channel_id: int,
        discord_message_id: int,
    ) -> TurnOutputState:
        turn_output = TurnOutputState(
            codex_turn_id=codex_turn_id,
            codex_thread_id=codex_thread_id,
            discord_thread_channel_id=discord_thread_channel_id,
            discord_message_id=discord_message_id,
        )
        self._turn_outputs_by_codex_turn_id[codex_turn_id] = turn_output
        return turn_output

    async def get_turn_output(
        self, *, codex_turn_id: str
    ) -> TurnOutputState | None:
        return self._turn_outputs_by_codex_turn_id.get(codex_turn_id)

    async def append_turn_output_delta(
        self, *, codex_turn_id: str, item_id: str, delta: str
    ) -> TurnOutputState | None:
        turn_output = self._turn_outputs_by_codex_turn_id.get(codex_turn_id)
        if turn_output is None:
            return None

        agent_message_item_id = turn_output.agent_message_item_id
        if (
            agent_message_item_id is not None
            and agent_message_item_id != item_id
        ):
            return turn_output

        turn_output = replace(
            turn_output,
            agent_message_item_id=item_id,
            text=turn_output.text + delta,
        )
        self._turn_outputs_by_codex_turn_id[codex_turn_id] = turn_output
        return turn_output

    async def set_turn_output_text(
        self,
        *,
        codex_turn_id: str,
        item_id: str | None,
        text: str,
    ) -> TurnOutputState | None:
        turn_output = self._turn_outputs_by_codex_turn_id.get(codex_turn_id)
        if turn_output is None:
            return None

        turn_output = replace(
            turn_output,
            agent_message_item_id=item_id or turn_output.agent_message_item_id,
            text=text,
        )
        self._turn_outputs_by_codex_turn_id[codex_turn_id] = turn_output
        return turn_output

    async def delete_turn_output(self, *, codex_turn_id: str) -> None:
        self._turn_outputs_by_codex_turn_id.pop(codex_turn_id, None)
