import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from assistant.execute_command import Event

logger = logging.getLogger(__name__)


async def parse_command_event(
    events: AsyncIterator[Event],
    *,
    metadata: dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    async for event in events:
        if event.kind == "stderr":
            logger.error(
                "metadata=%s, error=%s",
                metadata,
                event.data.rstrip().decode(errors="replace"),
            )
            continue

        json_str = event.data.rstrip().decode(errors="replace")
        logger.info("metadata=%s, event=%s", metadata, json_str)

        yield json.loads(json_str)
