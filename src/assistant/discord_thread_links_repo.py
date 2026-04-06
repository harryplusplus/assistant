import aiosqlite


class DiscordThreadLinksRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def get_codex_session_id(
        self, *, discord_thread_id: int
    ) -> str | None:
        cursor = await self._db.execute(
            "SELECT codex_session_id "
            "FROM discord_thread_links "
            "WHERE discord_thread_id = ?",
            (discord_thread_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def create(
        self, *, discord_thread_id: int, codex_session_id: str
    ) -> None:
        await self._db.execute(
            "INSERT INTO discord_thread_links "
            "(discord_thread_id, codex_session_id) "
            "VALUES (?, ?)",
            (discord_thread_id, codex_session_id),
        )
        await self._db.commit()
