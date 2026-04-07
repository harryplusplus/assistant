from sqlalchemy import select

from assistant.db import AsyncSessionmaker
from assistant.models import DiscordThreadLink


class DiscordThreadLinksService:
    def __init__(self, sessionmaker: AsyncSessionmaker) -> None:
        self._sessionmaker = sessionmaker

    async def find(self, *, discord_thread_id: int) -> DiscordThreadLink | None:
        stmt = select(DiscordThreadLink).where(
            DiscordThreadLink.discord_thread_id == discord_thread_id
        )
        async with self._sessionmaker() as session:
            return await session.scalar(stmt)

    async def create(
        self, *, discord_thread_id: int, codex_session_id: str
    ) -> None:
        async with self._sessionmaker.begin() as session:
            session.add(
                DiscordThreadLink(
                    discord_thread_id=discord_thread_id,
                    codex_session_id=codex_session_id,
                )
            )
