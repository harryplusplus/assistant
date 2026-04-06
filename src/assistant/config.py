import asyncio
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dishka import Provider, Scope
from dotenv import load_dotenv
from pydantic import BaseModel

from assistant.dishka_typing import provide


def _get_assistant_home() -> Path:
    assistant_home = os.getenv("ASSISTANT_HOME")
    if assistant_home:
        return Path(assistant_home).expanduser().resolve()
    return Path.home() / ".assistant"


def _ensure_assistant_home(assistant_home: Path) -> None:
    if not assistant_home.exists():
        assistant_home.mkdir(parents=True, exist_ok=True)


class Dotenv(BaseModel):
    DISCORD_TOKEN: str
    DISCORD_GUILD_ID: int


def _load_dotenv(assistant_home: Path) -> Dotenv:
    load_dotenv(dotenv_path=assistant_home / ".env")
    return Dotenv.model_validate(os.environ)


LogLevel = Literal["debug", "info", "warn", "warning", "error"]


class ConfigToml(BaseModel):
    log_level: LogLevel = "info"


def _load_config_toml(assistant_home: Path) -> ConfigToml:
    config_path = assistant_home / "config.toml"
    if not config_path.is_file():
        return ConfigToml()

    with config_path.open("rb") as f:
        return ConfigToml.model_validate(tomllib.load(f))


@dataclass(frozen=True, slots=True, kw_only=True)
class Config:
    assistant_home: Path
    discord_token: str
    discord_guild_id: int
    log_level: LogLevel
    db_path: Path


def _load_config() -> Config:
    assistant_home = _get_assistant_home()
    _ensure_assistant_home(assistant_home)
    dotenv = _load_dotenv(assistant_home)
    config_toml = _load_config_toml(assistant_home)
    return Config(
        assistant_home=assistant_home,
        discord_token=dotenv.DISCORD_TOKEN,
        discord_guild_id=dotenv.DISCORD_GUILD_ID,
        log_level=config_toml.log_level,
        db_path=assistant_home / "state.db",
    )


class ConfigProvider(Provider):
    scope = Scope.APP

    @provide()
    async def get_config(self) -> Config:
        return await asyncio.to_thread(_load_config)
