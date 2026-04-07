import json
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import cast

from deepagents import (
    create_deep_agent,  # pyright: ignore[reportUnknownVariableType]
)
from langchain_core.messages import BaseMessage
from langgraph.graph.state import (  # pyright: ignore[reportMissingTypeStubs]
    CompiledStateGraph,
)


@dataclass
class UnknownState:
    pass


@dataclass
class UnknownInput:
    pass


@dataclass
class UnknownOutput:
    pass


DeepAgent = CompiledStateGraph[UnknownState, None, UnknownInput, UnknownOutput]
OUTPUT_PATH = Path(__file__).resolve().parents[2] / "test.txt"


type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def _json_default(value: object) -> JsonValue:
    if isinstance(value, BaseMessage):
        return {
            "type": value.type,
            "data": cast("JsonValue", value.model_dump()),
        }

    if is_dataclass(value) and not isinstance(value, type):
        return cast("JsonValue", asdict(value))

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return cast("JsonValue", model_dump())

    msg = f"Object of type {type(value).__name__} is not JSON serializable"
    raise TypeError(msg)


def init_deep_agent() -> DeepAgent:
    return create_deep_agent("ollama:qwen3.5:4b-128k")  # pyright: ignore[reportUnknownVariableType]


async def main() -> None:
    agent = init_deep_agent()
    with OUTPUT_PATH.open("w", encoding="utf-8") as stream:
        async for event in agent.astream_events(
            {"messages": [{"role": "user", "content": "What is langgraph?"}]},
        ):
            payload = json.dumps(
                event,
                indent=2,
                ensure_ascii=False,
                default=_json_default,
            )
            stream.write(payload)
            stream.write("\n\n")
            stream.flush()

    print(f"Wrote stream events to {OUTPUT_PATH}")  # noqa: T201


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
