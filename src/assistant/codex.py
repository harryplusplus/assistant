from collections.abc import AsyncIterator

from assistant.execute_command import Event, execute_command


def _build_codex_command(session_id: str | None) -> tuple[str, ...]:
    cmd = (
        "codex",
        "exec",
        "--config",
        'model_reasoning_effort="xhigh"',
        "--config",
        'plan_mode_reasoning_effort="xhigh"',
        "--model",
        "gpt-5.4",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "--color",
        "never",
        "--json",
        "-",
    )

    if session_id is not None:
        cmd += ("resume", session_id)

    return cmd


def execute_codex(
    prompt: str, *, session_id: str | None
) -> AsyncIterator[Event]:
    command = _build_codex_command(session_id)
    return execute_command(command, input_=prompt)
