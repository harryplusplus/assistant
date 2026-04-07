from collections.abc import AsyncIterable

from dishka import Provider, Scope
from sqlalchemy import event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from assistant.config import Config
from assistant.dishka_typing import provide
from assistant.models import Base

AsyncSessionmaker = async_sessionmaker[AsyncSession]


class DbProvider(Provider):
    scope = Scope.APP

    @provide()
    async def get_engine(self, config: Config) -> AsyncIterable[AsyncEngine]:
        engine = create_async_engine(f"sqlite+aiosqlite:///{config.db_path}")
        event.listen(engine.sync_engine, "connect", _set_sqlite_pragmas)

        async with engine.begin() as conn:
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            await conn.run_sync(Base.metadata.create_all)

        yield engine

        event.remove(engine.sync_engine, "connect", _set_sqlite_pragmas)
        await engine.dispose()

    @provide()
    def get_sessionmaker(self, engine: AsyncEngine) -> AsyncSessionmaker:
        return async_sessionmaker(engine, expire_on_commit=False)


def _set_sqlite_pragmas(dbapi_connection: DBAPIConnection, _: object) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()
