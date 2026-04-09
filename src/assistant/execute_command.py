import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum

_GRACEFUL_WAIT_TIMEOUT = 60
_FORCE_WAIT_TIMEOUT = 5
_READ_CHUNK_SIZE = 64 * 1024
_MAX_PENDING_LINE_BYTES = 8 * 1024 * 1024


class Kind(StrEnum):
    STDOUT = "stdout"
    STDERR = "stderr"


@dataclass(frozen=True, slots=True, kw_only=True)
class Event:
    kind: Kind
    data: bytes


@dataclass(frozen=True, slots=True, kw_only=True)
class RawEvent:
    kind: Kind
    data: bytes | None


async def _read(
    reader: asyncio.StreamReader, kind: Kind, queue: asyncio.Queue[RawEvent]
) -> None:
    buffer = bytearray()

    try:
        while True:
            chunk = await reader.read(_READ_CHUNK_SIZE)
            if chunk == b"":
                if buffer:
                    queue.put_nowait(RawEvent(kind=kind, data=bytes(buffer)))
                break

            buffer.extend(chunk)

            while True:
                newline_index = buffer.find(b"\n")
                if newline_index < 0:
                    break

                end = newline_index + 1
                queue.put_nowait(RawEvent(kind=kind, data=bytes(buffer[:end])))
                del buffer[:end]

            if len(buffer) > _MAX_PENDING_LINE_BYTES:
                msg = (
                    f"{kind} produced a line longer than "
                    f"{_MAX_PENDING_LINE_BYTES} bytes without newline"
                )
                raise RuntimeError(msg)
    finally:
        await queue.put(RawEvent(kind=kind, data=None))


async def _cleanup(
    process: asyncio.subprocess.Process,
    read_tasks: list[asyncio.Task[None]],
    *,
    read_done: bool,
) -> None:
    if process.returncode is None:
        try:
            timeout = (
                _GRACEFUL_WAIT_TIMEOUT if read_done else _FORCE_WAIT_TIMEOUT
            )
            await asyncio.wait_for(process.wait(), timeout=timeout)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                process.terminate()
            try:
                await asyncio.wait_for(
                    process.wait(), timeout=_FORCE_WAIT_TIMEOUT
                )
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                await process.wait()

    if read_tasks:
        results = await asyncio.gather(*read_tasks, return_exceptions=True)
        errors = [x for x in results if isinstance(x, BaseException)]
        if errors:
            msg = f"Failed to read from stdout and stderr: {len(errors)} errors"
            raise BaseExceptionGroup(msg, errors)


async def execute_command(  # noqa: C901, PLR0912, PLR0915
    command: tuple[str, ...],
    *,
    input_: str | None = None,
) -> AsyncIterator[Event]:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE if input_ is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdin_error: Exception | None = None
    read_tasks: list[asyncio.Task[None]] = []
    read_done = False
    try:
        stdout = process.stdout
        stderr = process.stderr
        if stdout is None or stderr is None:
            msg = "Failed to create subprocess with pipes"
            raise RuntimeError(msg)

        queue: asyncio.Queue[RawEvent] = asyncio.Queue()
        read_tasks.append(
            asyncio.create_task(_read(stdout, Kind.STDOUT, queue))
        )
        read_tasks.append(
            asyncio.create_task(_read(stderr, Kind.STDERR, queue))
        )

        if input_ is not None:
            stdin = process.stdin
            if stdin is None:
                msg = "Failed to create subprocess with stdin pipe"
                raise RuntimeError(msg)

            try:
                stdin.write(input_.encode())
                await stdin.drain()
            except (BrokenPipeError, ConnectionResetError) as e:
                stdin_error = e
            finally:
                stdin.close()
                with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                    await stdin.wait_closed()

        stdout_running = True
        stderr_running = True
        while stdout_running or stderr_running:
            event = await queue.get()
            if event.data is None:
                if event.kind == Kind.STDOUT:
                    stdout_running = False
                else:
                    stderr_running = False
                continue

            yield Event(kind=event.kind, data=event.data)

        read_done = True
    finally:
        cleanup_task = asyncio.create_task(
            _cleanup(process, read_tasks, read_done=read_done)
        )
        try:
            await asyncio.shield(cleanup_task)
        except asyncio.CancelledError:
            await cleanup_task
            raise

    returncode = process.returncode
    if returncode != 0:
        msg = f"Process exited with code {returncode}"
        raise RuntimeError(msg)

    if stdin_error is not None:
        msg = "Failed to write to process stdin"
        raise RuntimeError(msg) from stdin_error
