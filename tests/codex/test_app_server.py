import pytest

from assistant.codex.app_server import CodexAppServer


@pytest.mark.asyncio
async def test_app_server_start_and_close() -> None:
    app_server = CodexAppServer()

    await app_server.start()

    process = app_server._process
    assert process is not None
    assert process.returncode is None

    await app_server.close()

    assert app_server._process is None
    assert app_server._stdout_task is None
    assert app_server._stderr_task is None
