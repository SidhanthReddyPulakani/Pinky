from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from pinky_core.event.intake import EventIntake
from pinky_core.event.models import IncomingEvent
from pinky_core.event.reader import EventReader

_WINDOWS_PROTECTED_RELATIVE_ROOTS = (
    "Windows",
    "Program Files",
    "Program Files (x86)",
    "ProgramData",
    "$Recycle.Bin",
    "System Volume Information",
    "Recovery",
    "Config.Msi",
    "Documents and Settings",
    "New-Folder\\Pinky",
    "Users\\sidha",
)


def _windows_protected_roots(root: Path) -> tuple[Path, ...]:
    if os.name != "nt":
        return ()

    return tuple(
        root / relative_path
        for relative_path in _WINDOWS_PROTECTED_RELATIVE_ROOTS
    )

@dataclass(frozen=True)
class _FilesystemChange:
    event_type: str
    source_path: Path
    destination_path: Path | None = None


class FilesystemReader(EventReader):
    """Observe filesystem changes and ingest them as Pinky Events."""

    def __init__(
        self,
        *,
        root: Path,
        intake: EventIntake,
        recursive: bool = True,
        queue_size: int = 1_000,
    ) -> None:
        if queue_size <= 0:
            raise ValueError("queue_size must be greater than zero")

        self._root = root.resolve()
        self._intake = intake
        self._recursive = recursive
        self._queue_size = queue_size
        self._ignored_roots = _windows_protected_roots(self._root)

        self._observer: Observer | None = None
        self._queue: asyncio.Queue[_FilesystemChange | None] | None = None
        self._consumer_task: asyncio.Task[None] | None = None

        self._running = False
        self._fault: BaseException | None = None
        self._stop_lock = asyncio.Lock()

        self._logger = logging.getLogger(__name__)
        

    async def run(self) -> None:
        if self._running:
            raise RuntimeError("Reader is already running")

        if not self._root.exists():
            raise FileNotFoundError(self._root)

        if not self._root.is_dir():
            raise NotADirectoryError(self._root)

        self._running = True
        self._fault = None
        self._queue = asyncio.Queue(maxsize=self._queue_size)

        loop = asyncio.get_running_loop()

        handler = _FilesystemEventHandler(
            root=self._root,
            loop=loop,
            queue=self._queue,
            on_fault=self._on_fault,
            logger=self._logger,
            ignored_roots=self._ignored_roots,
        )

        observer = Observer()
        observer.schedule(
            handler,
            str(self._root),
            recursive=self._recursive,
        )

        self._observer = observer
        self._consumer_task = asyncio.create_task(
            self._consume(),
            name="filesystem-reader-consumer",
        )

        observer.start()

        self._logger.info(
            "Filesystem reader started root=%s recursive=%s",
            self._root,
            self._recursive,
        )

        try:
            await self._consumer_task

            if self._fault is not None:
                raise self._fault
        finally:
            await self.stop()

    async def stop(self) -> None:
        async with self._stop_lock:
            observer = self._observer
            consumer_task = self._consumer_task
            queue = self._queue

            self._running = False
            self._observer = None
            self._consumer_task = None

            if observer is not None:
                observer.stop()

            if queue is not None:
                try:
                    queue.put_nowait(None)
                except asyncio.QueueFull:
                    # A full queue means the reader has already faulted.
                    # Do not block shutdown waiting for capacity.
                    pass

        if observer is not None:
            await asyncio.to_thread(observer.join)

        if (
            consumer_task is not None
            and consumer_task is not asyncio.current_task()
        ):
            await consumer_task

        self._queue = None

        self._logger.info(
            "Filesystem reader stopped root=%s",
            self._root,
        )

    def _on_fault(self, fault: BaseException) -> None:
        if self._fault is not None:
            return

        self._fault = fault

        self._logger.error(
            "Filesystem reader faulted: %s",
            fault,
        )

        self._running = False

        observer = self._observer
        if observer is not None:
            observer.stop()

        queue = self._queue
        if queue is not None:
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                # The consumer will eventually observe _fault after
                # processing the currently queued item.
                pass
            
    def _is_ignored_path(self, path: Path) -> bool:
        normalized = os.path.normcase(
            os.path.abspath(os.fspath(path))
        )

        return any(
            normalized == os.path.normcase(os.fspath(ignored_root))
            or normalized.startswith(
                os.path.normcase(os.fspath(ignored_root)) + os.sep
            )
            for ignored_root in self._ignored_roots
        )
    
    async def _consume(self) -> None:
        assert self._queue is not None

        while True:
            change = await self._queue.get()

            try:
                if change is None:
                    return

                await self._process(change)
            finally:
                self._queue.task_done()

    async def _process(self, change: _FilesystemChange) -> None:
        event = self._to_event(change)

        try:
            result = await self._intake.accept(event)
        except Exception:
            self._logger.exception(
                "Filesystem event ingestion failed "
                "type=%s path=%s",
                event.event_type,
                change.source_path,
            )
            return

        self._logger.info(
            "Filesystem event processed "
            "type=%s path=%s result=%s",
            event.event_type,
            change.source_path,
            type(result).__name__,
        )

    def _to_event(self, change: _FilesystemChange) -> IncomingEvent:
        payload = self._build_payload(change)

        return IncomingEvent(
            event_type=change.event_type,
            source="filesystem",
            dedupe_key=self._dedupe_key(
                change=change,
                payload=payload,
            ),
            occurred_at=datetime.now(UTC),
            payload=payload,
            event_metadata={
                "root": str(self._root),
            },
        )

    def _build_payload(
        self,
        change: _FilesystemChange,
    ) -> dict[str, Any]:
        source_path = change.source_path

        payload: dict[str, Any] = {
            "path": str(source_path),
            "relative_path": self._relative_path(source_path),
        }

        if change.destination_path is not None:
            payload["destination_path"] = str(change.destination_path)
            payload["destination_relative_path"] = (
                self._relative_path(change.destination_path)
            )

        try:
            stat = source_path.stat()
        except (FileNotFoundError, PermissionError):
            return payload

        payload.update(
            {
                "is_directory": source_path.is_dir(),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )

        return payload

    def _relative_path(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self._root))
        except ValueError:
            return str(path)

    def _dedupe_key(
        self,
        *,
        change: _FilesystemChange,
        payload: dict[str, Any],
    ) -> str:
        source = self._relative_path(change.source_path)

        destination = (
            self._relative_path(change.destination_path)
            if change.destination_path is not None
            else ""
        )

        return (
            f"filesystem:{change.event_type}:"
            f"{source}:{destination}:"
            f"{payload.get('mtime_ns', '')}:"
            f"{payload.get('size', '')}"
        )


class _FilesystemEventHandler(FileSystemEventHandler):
    """Translate watchdog callbacks into queued filesystem changes."""

    def __init__(
        self,
        *,
        root: Path,
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue[_FilesystemChange | None],
        on_fault: Any,
        logger: logging.Logger,
        ignored_roots: tuple[Path, ...] = (),
    ) -> None:
        self._root = root
        self._loop = loop
        self._queue = queue
        self._on_fault = on_fault
        self._logger = logger
        self._ignored_roots = ignored_roots

    def _is_ignored_path(self, path: Path) -> bool:
        normalized = os.path.normcase(
            os.path.abspath(os.fspath(path))
        )

        return any(
            normalized == os.path.normcase(os.fspath(ignored_root))
            or normalized.startswith(
                os.path.normcase(os.fspath(ignored_root)) + os.sep
            )
            for ignored_root in self._ignored_roots
        )
    
    def on_created(self, event: FileSystemEvent) -> None:
        if isinstance(event, FileCreatedEvent):
            self._enqueue(
                _FilesystemChange(
                    event_type="file.created",
                    source_path=Path(event.src_path),
                )
            )

    def on_modified(self, event: FileSystemEvent) -> None:
        if isinstance(event, FileModifiedEvent):
            self._enqueue(
                _FilesystemChange(
                    event_type="file.modified",
                    source_path=Path(event.src_path),
                )
            )

    def on_deleted(self, event: FileSystemEvent) -> None:
        if isinstance(event, FileDeletedEvent):
            self._enqueue(
                _FilesystemChange(
                    event_type="file.deleted",
                    source_path=Path(event.src_path),
                )
            )

    def on_moved(self, event: FileSystemEvent) -> None:
        if isinstance(event, FileMovedEvent):
            self._enqueue(
                _FilesystemChange(
                    event_type="file.moved",
                    source_path=Path(event.src_path),
                    destination_path=Path(event.dest_path),
                )
            )

    def _enqueue(self, change: _FilesystemChange) -> None:
        if self._is_ignored_path(change.source_path):
            self._logger.debug(
                "Filesystem event ignored protected path "
                "type=%s path=%s",
                change.event_type,
                change.source_path,
            )
            return

        if (
            change.destination_path is not None
            and self._is_ignored_path(change.destination_path)
        ):
            self._logger.debug(
                "Filesystem event ignored protected destination "
                "type=%s path=%s destination=%s",
                change.event_type,
                change.source_path,
                change.destination_path,
            )
            return
        
        def enqueue() -> None:
            try:
                self._queue.put_nowait(change)
            except asyncio.QueueFull:
                fault = RuntimeError(
                    "Filesystem reader event queue overflow"
                )

                self._logger.error(
                    "Filesystem reader queue overflow "
                    "type=%s path=%s",
                    change.event_type,
                    change.source_path,
                )

                self._on_fault(fault)

        try:
            self._loop.call_soon_threadsafe(enqueue)
        except RuntimeError:
            self._logger.debug(
                "Filesystem event ignored because reader loop stopped "
                "path=%s",
                change.source_path,
            )