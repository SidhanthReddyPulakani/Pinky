from abc import ABC, abstractmethod
from uuid import UUID

from pinky_core.event.models import Event
from pinky_core.persistence.event_record import StoredEvent


class EventRepository(ABC):
    @abstractmethod
    async def get(self, event_id: UUID) -> Event | None:
        ...

    @abstractmethod
    async def find_by_source_event(
        self,
        source: str,
        source_event_id: str,
    ) -> Event | None:
        ...

    @abstractmethod
    async def find_by_dedupe_key(
        self,
        source: str,
        dedupe_key: str,
    ) -> Event | None:
        ...

    @abstractmethod
    async def read_after(
        self,
        event_seq: int,
        *,
        limit: int = 100,
    ) -> list[StoredEvent]:
        ...