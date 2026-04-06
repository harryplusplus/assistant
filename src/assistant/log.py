import logging
import sys
from datetime import UTC, datetime
from typing import override

from assistant.config import LogLevel


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


def init_log() -> None:
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        Iso8601Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"),
    )
    root_logger.addHandler(handler)


def set_log_level(log_level: LogLevel) -> None:
    level = logging.getLevelNamesMapping().get(log_level.upper())
    if level is None:
        msg = f"Invalid log level: {log_level}"
        raise ValueError(msg)

    logging.getLogger().setLevel(level)
