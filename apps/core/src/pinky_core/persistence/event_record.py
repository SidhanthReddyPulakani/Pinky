from dataclasses import dataclass

from pinky_core.event.models import Event


@dataclass(frozen=True)
class StoredEvent:
    event_seq: int
    event: Event
