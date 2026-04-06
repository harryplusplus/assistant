import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from typing import override

from dishka import Provider, Scope

from assistant.config import Config
from assistant.dishka_typing import provide


class Iso8601Formatter(logging.Formatter):
    @override
    def formatTime(
        self,
        record: logging.LogRecord,
        datefmt: str | None = None,
    ) -> str:
        return (
            datetime.fromtimestamp(
                record.created,
                tz=UTC,
            )
            .astimezone()
            .isoformat(timespec="milliseconds")
        )


class LogInitToken:
    pass


class LogProvider(Provider):
    scope = Scope.APP

    @provide()
    def init_log(self, config: Config) -> LogInitToken:
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        handler = RotatingFileHandler(
            config.logs_dir / "assistant.log",
            maxBytes=10_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(
            Iso8601Formatter(
                "%(asctime)s %(levelname)s [%(name)s] %(message)s"
            ),
        )
        root_logger.addHandler(handler)

        level = logging.getLevelNamesMapping().get(config.log_level.upper())
        if level is None:
            msg = f"Invalid log level: {config.log_level}"
            raise ValueError(msg)

        root_logger.setLevel(level)
        return LogInitToken()
