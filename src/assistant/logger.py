import logging
import sys
from datetime import UTC, datetime

from typing_extensions import override

from .config import Config


def get_assistant_logger() -> logging.Logger:
    return logging.getLogger("assistant")


def _to_logging_level(value: str) -> int:
    return logging.getLevelNamesMapping()[value.upper()]


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


def configure_logger(config: Config) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        Iso8601Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"),
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.WARNING)

    get_assistant_logger().setLevel(_to_logging_level(config.assistant_log_level))
    logging.getLogger("discord").setLevel(_to_logging_level(config.discord_log_level))
