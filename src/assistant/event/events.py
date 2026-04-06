from dataclasses import dataclass

from assistant.codex.schemas.codex_app_server_protocol_schemas import (
    JsonrpcMessage,
)


@dataclass
class CodexServerMessage:
    message: JsonrpcMessage


Event = CodexServerMessage
