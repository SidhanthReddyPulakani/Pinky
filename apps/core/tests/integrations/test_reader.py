from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pinky_core.event.intake import EventIntake
from pinky_core.event.intake_result import Accepted, Rejected
from pinky_core.event.models import IncomingEvent
from pinky_core.integrations.filesystem.reader import (
    FilesystemReader,
    _FilesystemChange,
    _FilesystemEventHandler,
)


class RecordingIntake:
    def __init__(self) -> None:
        self.events: list[IncomingEvent] = []
        self.reject = False

    async def accept(self, event: IncomingEvent):
        self.events.append(event)

        if self.reject:
            return Rejected("test rejection")

        return Accepted(
            event=event.model_copy(),
        )


@pytest.fixture
def intake() -> RecordingIntake:
    return RecordingIntake()


@pytest.mark.asyncio
async def test_reader_rejects_missing_root(
    tmp_path: Path,
    intake: RecordingIntake,
) -> None:
    root = tmp_path / "missing"

    reader = FilesystemReader(
        root=root,
        intake=intake,  # type: ignore[arg-type]
    )

    with pytest.raises(FileNotFoundError):
        await reader.run()


@pytest.mark.asyncio
async def test_reader_rejects_file_as_root(
    tmp_path: Path,
    intake: RecordingIntake,
) -> None:
    root = tmp_path / "file.txt"
    root.write_text("hello")

    reader = FilesystemReader(
        root=root,
        intake=intake,  # type: ignore[arg-type]
    )

    with pytest.raises(NotADirectoryError):
        await reader.run()


@pytest.mark.asyncio
async def test_created_file_produces_event(
    tmp_path: Path,
    intake: RecordingIntake,
) -> None:
    reader = FilesystemReader(
        root=tmp_path,
        intake=intake,  # type: ignore[arg-type]
    )

    task = asyncio.create_task(reader.run())

    try:
        await asyncio.sleep(0.2)

        path = tmp_path / "created.txt"
        path.write_text("hello")

        await _wait_until(
            lambda: len(intake.events) >= 1,
        )

        event = next(
            event
            for event in intake.events
            if event.event_type == "file.created"
        )

        assert event.source == "filesystem"
        assert event.payload["path"] == str(path)
        assert event.payload["relative_path"] == "created.txt"
    finally:
        await reader.stop()
        await task


@pytest.mark.asyncio
async def test_modified_file_produces_event(
    tmp_path: Path,
    intake: RecordingIntake,
) -> None:
    path = tmp_path / "modified.txt"
    path.write_text("before")

    reader = FilesystemReader(
        root=tmp_path,
        intake=intake,  # type: ignore[arg-type]
    )

    task = asyncio.create_task(reader.run())

    try:
        await asyncio.sleep(0.2)

        path.write_text("after")

        await _wait_until(
            lambda: any(
                event.event_type == "file.modified"
                and event.payload["path"] == str(path)
                for event in intake.events
            )
        )
    finally:
        await reader.stop()
        await task


@pytest.mark.asyncio
async def test_deleted_file_produces_event(
    tmp_path: Path,
    intake: RecordingIntake,
) -> None:
    path = tmp_path / "deleted.txt"
    path.write_text("hello")

    reader = FilesystemReader(
        root=tmp_path,
        intake=intake,  # type: ignore[arg-type]
    )

    task = asyncio.create_task(reader.run())

    try:
        await asyncio.sleep(0.2)

        path.unlink()

        await _wait_until(
            lambda: any(
                event.event_type == "file.deleted"
                and event.payload["path"] == str(path)
                for event in intake.events
            )
        )
    finally:
        await reader.stop()
        await task


@pytest.mark.asyncio
async def test_moved_file_produces_event(
    tmp_path: Path,
    intake: RecordingIntake,
) -> None:
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"

    source.write_text("hello")

    reader = FilesystemReader(
        root=tmp_path,
        intake=intake,  # type: ignore[arg-type]
    )

    task = asyncio.create_task(reader.run())

    try:
        await asyncio.sleep(0.2)

        source.rename(destination)

        await _wait_until(
            lambda: any(
                event.event_type == "file.moved"
                and event.payload["path"] == str(source)
                and event.payload["destination_path"] == str(destination)
                for event in intake.events
            )
        )
    finally:
        await reader.stop()
        await task


@pytest.mark.asyncio
async def test_nested_file_is_observed(
    tmp_path: Path,
    intake: RecordingIntake,
) -> None:
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)

    reader = FilesystemReader(
        root=tmp_path,
        intake=intake,  # type: ignore[arg-type]
        recursive=True,
    )

    task = asyncio.create_task(reader.run())

    try:
        await asyncio.sleep(0.2)

        path = nested / "test.txt"
        path.write_text("hello")

        await _wait_until(
            lambda: any(
                event.payload.get("path") == str(path)
                for event in intake.events
            )
        )
    finally:
        await reader.stop()
        await task


@pytest.mark.asyncio
async def test_non_recursive_reader_ignores_nested_file(
    tmp_path: Path,
    intake: RecordingIntake,
) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()

    reader = FilesystemReader(
        root=tmp_path,
        intake=intake,  # type: ignore[arg-type]
        recursive=False,
    )

    task = asyncio.create_task(reader.run())

    try:
        await asyncio.sleep(0.2)

        path = nested / "test.txt"
        path.write_text("hello")

        await asyncio.sleep(0.5)

        assert not any(
            event.payload.get("path") == str(path)
            for event in intake.events
        )
    finally:
        await reader.stop()
        await task


@pytest.mark.asyncio
async def test_intake_failure_does_not_kill_reader(
    tmp_path: Path,
) -> None:
    class FailingIntake:
        calls = 0

        async def accept(self, event: IncomingEvent):
            self.calls += 1
            raise RuntimeError("database unavailable")

    intake = FailingIntake()

    reader = FilesystemReader(
        root=tmp_path,
        intake=intake,  # type: ignore[arg-type]
    )

    task = asyncio.create_task(reader.run())

    try:
        await asyncio.sleep(0.2)

        (tmp_path / "test.txt").write_text("hello")

        await _wait_until(lambda: intake.calls >= 1)

        assert not task.done()
    finally:
        await reader.stop()
        await task


@pytest.mark.asyncio
async def test_handler_enqueues_filesystem_change() -> None:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[_FilesystemChange | None] = asyncio.Queue()

    handler = _FilesystemEventHandler(
        root=Path("/tmp"),
        loop=loop,
        queue=queue,
        on_fault=lambda fault: None,
        logger=__import__("logging").getLogger(__name__),
    )

    path = Path("/tmp/test.txt")

    handler._enqueue(
        _FilesystemChange(
            event_type="file.created",
            source_path=path,
        )
    )

    change = await asyncio.wait_for(
        queue.get(),
        timeout=1,
    )

    assert change is not None
    assert change.event_type == "file.created"
    assert change.source_path == path


async def _wait_until(
    predicate,
    *,
    timeout: float = 3.0,
    interval: float = 0.05,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout

    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError("Condition was not satisfied before timeout")

        await asyncio.sleep(interval)

@pytest.mark.asyncio
async def test_queue_overflow_faults_reader() -> None:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[_FilesystemChange | None] = asyncio.Queue(
        maxsize=1,
    )

    faults: list[BaseException] = []

    def on_fault(fault: BaseException) -> None:
        faults.append(fault)

    handler = _FilesystemEventHandler(
        root=Path("/tmp"),
        loop=loop,
        queue=queue,
        on_fault=on_fault,
        logger=__import__("logging").getLogger(__name__),
    )

    handler._enqueue(
        _FilesystemChange(
            event_type="file.created",
            source_path=Path("/tmp/a.txt"),
        )
    )

    await asyncio.sleep(0)

    handler._enqueue(
        _FilesystemChange(
            event_type="file.created",
            source_path=Path("/tmp/b.txt"),
        )
    )

    await asyncio.sleep(0)

    assert queue.qsize() == 1
    assert len(faults) == 1
    assert isinstance(faults[0], RuntimeError)
    assert str(faults[0]) == "Filesystem reader event queue overflow"