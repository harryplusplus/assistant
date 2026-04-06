import logging
import sys
from datetime import UTC, datetime
from typing import override


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


def setup_logging(config: Config) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        Iso8601Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"),
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(_to_logging_level(config.log_level))
