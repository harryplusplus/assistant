from collections.abc import AsyncIterator

from assistant.execute_command import Event, execute_command


def _build_opencode_command(
    prompt: str, *, session_id: str | None
) -> tuple[str, ...]:
    cmd = (
        "opencode",
        "run",
        "--dangerously-skip-permissions=true",
        "--thinking=true",
        "--format=json",
        "--model=ollama-cloud/glm-5.1",
    )

    if session_id is not None:
        cmd += ("--session", session_id)

    cmd += (prompt,)
    return cmd


async def execute_opencode(
    prompt: str, *, session_id: str | None
) -> AsyncIterator[Event]:
    command = _build_opencode_command(prompt, session_id=session_id)
    return execute_command(command)
