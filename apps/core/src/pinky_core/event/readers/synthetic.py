from collections.abc import Awaitable, Callable

from pinky_core.event.models import IncomingEvent
from pinky_core.event.reader import EventReader


class SyntheticEventReader(EventReader):
    """Test reader that emits events into the Event ingestion pipeline."""

    def __init__(
        self,
        *,
        emit: Callable[[IncomingEvent], Awaitable[None]],
    ) -> None:
        self._emit = emit
        self._running = False

    async def run(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def emit(self, event: IncomingEvent):
        if not self._running:
            raise RuntimeError("Reader is not running")

        return await self._emit(event)