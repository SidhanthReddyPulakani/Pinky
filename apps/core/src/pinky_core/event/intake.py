from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

from pinky_core.event.intake_result import (
    Accepted,
    Duplicate,
    IntakeResult,
    Rejected,
)
from pinky_core.event.models import Event, IncomingEvent
from pinky_core.event.repository import EventRepository
from pinky_core.event.validation import EventValidation
from pinky_core.persistence.event_store import EventStore


class EventIntake:
    """
    Application-level Event ingestion orchestrator.

    EventIntake is the single entry point for accepting IncomingEvent
    instances into the Event subsystem.
    """

    def __init__(
        self,
        *,
        validator: EventValidation,
        repository: EventRepository,
        event_store: EventStore,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._validator = validator
        self._repository = repository
        self._event_store = event_store
        self._clock = clock or self._utc_now

    async def accept(self, incoming: IncomingEvent) -> IntakeResult:
        received_at = self._clock()

        event = Event.from_incoming(
            incoming,
            received_at=received_at,
        )

        try:
            self._validator.validate(event)
        except ValueError as exc:
            return Rejected(str(exc))

        # preliminary dedupe checks...
        if event.source_event_id is not None:
            existing_event = await self._repository.find_by_source_event(
                event.source,
                event.source_event_id,
            )
            if existing_event is not None:
                return Duplicate(existing_event)

        if event.dedupe_key is not None:
            existing_event = await self._repository.find_by_dedupe_key(
                event.source,
                event.dedupe_key,
            )
            if existing_event is not None:
                return Duplicate(existing_event)

        try:
            await self._event_store.append(event)
        except IntegrityError:
            existing_event = None

            if event.source_event_id is not None:
                existing_event = await self._repository.find_by_source_event(
                    event.source,
                    event.source_event_id,
                )

            if existing_event is None and event.dedupe_key is not None:
                existing_event = await self._repository.find_by_dedupe_key(
                    event.source,
                    event.dedupe_key,
                )

            if existing_event is not None:
                return Duplicate(existing_event)

            raise

        return Accepted(event)

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(UTC)
