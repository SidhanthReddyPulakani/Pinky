from dataclasses import dataclass

from pinky_core.event.models import Event


@dataclass(frozen=True)
class Accepted:
    event: Event


@dataclass(frozen=True)
class Duplicate:
    existing_event: Event


@dataclass(frozen=True)
class Rejected:
    reason: str


type IntakeResult = Accepted | Duplicate | Rejected