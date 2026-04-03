import pytest

from assistant.codex import Codex


@pytest.mark.asyncio
async def test_codex_start_and_close() -> None:
    codex = Codex()

    await codex.start()

    process = codex._process
    assert process is not None
    assert process.returncode is None

    await codex.close()

    assert codex._process is None
    assert codex._stdout_task is None
    assert codex._stderr_task is None
