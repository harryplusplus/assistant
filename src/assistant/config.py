import os
from dataclasses import dataclass
from typing import Self


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        msg = f"{name} environment variable is required."
        raise RuntimeError(msg)
    return value


def _parse_log_level(*, value: str, env_name: str) -> str:
    log_level = value.lower()
    if log_level not in {"debug", "info", "warning", "error"}:
        msg = f"{env_name} must be one of debug, info, warning, error: got {value!r}."
        raise ValueError(msg)
    return log_level


def _get_log_level_from_env(env_name: str) -> str:
    return _parse_log_level(
        value=os.getenv(env_name, "info"),
        env_name=env_name,
    )


@dataclass(frozen=True, slots=True)
class Config:
    discord_token: str
    discord_guild_id: int
    discord_log_level: str
    assistant_log_level: str

    @classmethod
    def from_env(cls) -> Self:
        return cls(
            discord_token=_require_env("DISCORD_TOKEN"),
            discord_guild_id=int(_require_env("DISCORD_GUILD_ID")),
            discord_log_level=_get_log_level_from_env("DISCORD_LOG_LEVEL"),
            assistant_log_level=_get_log_level_from_env("ASSISTANT_LOG_LEVEL"),
        )
