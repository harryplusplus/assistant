from datetime import datetime

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class DiscordThreadLink(Base):
    __tablename__ = "discord_thread_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    discord_thread_id: Mapped[int] = mapped_column(nullable=False, unique=True)
    codex_session_id: Mapped[str] = mapped_column(nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
