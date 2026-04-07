import json
import logging
from collections.abc import AsyncIterable
from typing import Any

from assistant.codex import execute_codex

logger = logging.getLogger(__name__)


class CodexExecutor:
    async def execute(
        self,
        prompt: str,
        *,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterable[dict[str, Any]]:
        async for event in execute_codex(prompt, session_id=session_id):
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
