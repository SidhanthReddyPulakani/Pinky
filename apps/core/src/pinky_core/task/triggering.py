from dataclasses import dataclass
from uuid import UUID

from pinky_core.event.models import Event
from pinky_core.event.repository import EventRepository
from pinky_core.persistence.consumer_offset_repository import (
    ConsumerOffsetRepository,
)
from pinky_core.task.trigger_registry import TriggerRegistry


@dataclass(frozen=True)
class TaskActivationCandidate:
    """
    Describes a Task that should be activated because an Event matched
    one or more of its triggers.

    This is intentionally NOT an Occurrence yet.
    """

    task_id: UUID
    event: Event
    event_seq: int


class TaskTriggering:
    """
    Consumes persisted Events and identifies Tasks whose triggers match.

    The Event Store remains the source of truth.
    The consumer offset makes processing resumable.
    """

    def __init__(
        self,
        *,
        event_repository: EventRepository,
        consumer_offset_repository: ConsumerOffsetRepository,
        trigger_registry: TriggerRegistry,
        consumer_id: str = "task-triggering",
    ) -> None:
        self._event_repository = event_repository
        self._consumer_offset_repository = consumer_offset_repository
        self._trigger_registry = trigger_registry
        self._consumer_id = consumer_id

    async def process_event(
        self,
        *,
        event_seq: int,
        event: Event,
    ) -> list[TaskActivationCandidate]:
        task_ids = self._trigger_registry.matching_task_ids(event)

        candidates = [
            TaskActivationCandidate(
                task_id=task_id,
                event=event,
                event_seq=event_seq,
            )
            for task_id in task_ids
        ]

        await self._consumer_offset_repository.advance(
            consumer_id=self._consumer_id,
            event_seq=event_seq,
        )

        return candidates

    async def process_available(
        self,
        *,
        limit: int = 100,
    ) -> list[TaskActivationCandidate]:
        offset = await self._consumer_offset_repository.get(
            self._consumer_id,
        )

        last_processed_seq = (
            offset.last_processed_event_seq
            if offset is not None
            else 0
        )

        stored_events = await self._event_repository.read_after(
            last_processed_seq,
            limit=limit,
        )

        candidates: list[TaskActivationCandidate] = []

        for stored_event in stored_events:
            event_candidates = await self.process_event(
                event_seq=stored_event.event_seq,
                event=stored_event.event,
            )
            candidates.extend(event_candidates)

        return candidates