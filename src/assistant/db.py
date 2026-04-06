from collections.abc import AsyncIterable

import aiosqlite
from dishka import Provider, Scope

from assistant.config import Config
from assistant.dishka_typing import provide


class DbProvider(Provider):
    scope = Scope.APP

    @provide()
    async def get_db(
        self, config: Config
    ) -> AsyncIterable[aiosqlite.Connection]:
        async with aiosqlite.connect(config.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA busy_timeout=5000;")
            await db.execute("PRAGMA synchronous=NORMAL;")
            await db.execute("PRAGMA foreign_keys=ON;")

            await db.execute("""
                CREATE TABLE IF NOT EXISTS discord_thread_links (
                    id INTEGER PRIMARY KEY,
                    discord_thread_id INTEGER NOT NULL UNIQUE,
                    codex_session_id TEXT NOT NULL UNIQUE
                );
            """)
            await db.commit()
            yield db
