from datetime import UTC, datetime
from uuid import uuid4

import pytest

from pinky_core.event.models import Event
from pinky_core.persistence.event_record import StoredEvent
from pinky_core.task.trigger_registry import TriggerRegistry
from pinky_core.task.triggering import TaskTriggering
from pinky_core.task.triggers import (
    EventTriggerDefinition,
    TaskTrigger,
    TriggerType,
)


class FakeEventRepository:
    def __init__(self, events: list[StoredEvent]) -> None:
        self.events = events

    async def read_after(
        self,
        event_seq: int,
        *,
        limit: int = 100,
    ) -> list[StoredEvent]:
        return [
            event
            for event in self.events
            if event.event_seq > event_seq
        ][:limit]


class FakeConsumerOffset:
    def __init__(self) -> None:
        self.offsets: dict[str, int] = {}

    async def get(self, consumer_id: str):
        value = self.offsets.get(consumer_id)

        if value is None:
            return None

        return type(
            "Offset",
            (),
            {"last_processed_event_seq": value},
        )()

    async def advance(
        self,
        *,
        consumer_id: str,
        event_seq: int,
        updated_at: str | None = None,
    ) -> None:
        current = self.offsets.get(consumer_id, 0)

        if event_seq < current:
            raise ValueError("consumer offset cannot move backwards")

        self.offsets[consumer_id] = event_seq


def make_event(event_type: str = "email.received") -> Event:
    now = datetime.now(UTC)

    return Event(
        event_type=event_type,
        source="test",
        occurred_at=now,
        received_at=now,
        payload={},
    )


def make_trigger(task_id) -> TaskTrigger:
    return TaskTrigger(
        task_id=task_id,
        trigger_type=TriggerType.EVENT,
        definition=EventTriggerDefinition(
            event_type="email.received",
        ),
    )


@pytest.mark.asyncio
async def test_process_event_returns_activation_candidate() -> None:
    task_id = uuid4()
    event = make_event()

    registry = TriggerRegistry()
    registry.register(make_trigger(task_id))

    offsets = FakeConsumerOffset()

    triggering = TaskTriggering(
        event_repository=FakeEventRepository([]),
        consumer_offset_repository=offsets,
        trigger_registry=registry,
    )

    candidates = await triggering.process_event(
        event_seq=42,
        event=event,
    )

    assert len(candidates) == 1
    assert candidates[0].task_id == task_id
    assert candidates[0].event == event
    assert candidates[0].event_seq == 42
    assert offsets.offsets["task-triggering"] == 42


@pytest.mark.asyncio
async def test_unmatched_event_produces_no_candidates() -> None:
    task_id = uuid4()
    event = make_event("file.created")

    registry = TriggerRegistry()
    registry.register(make_trigger(task_id))

    offsets = FakeConsumerOffset()

    triggering = TaskTriggering(
        event_repository=FakeEventRepository([]),
        consumer_offset_repository=offsets,
        trigger_registry=registry,
    )

    candidates = await triggering.process_event(
        event_seq=10,
        event=event,
    )

    assert candidates == []
    assert offsets.offsets["task-triggering"] == 10


@pytest.mark.asyncio
async def test_process_available_reads_after_offset() -> None:
    task_a = uuid4()
    task_b = uuid4()

    event_a = make_event()
    event_b = make_event("file.created")

    repository = FakeEventRepository(
        [
            StoredEvent(event_seq=1, event=event_a),
            StoredEvent(event_seq=2, event=event_b),
        ]
    )

    registry = TriggerRegistry()
    registry.register(make_trigger(task_a))

    offsets = FakeConsumerOffset()
    offsets.offsets["task-triggering"] = 0

    triggering = TaskTriggering(
        event_repository=repository,
        consumer_offset_repository=offsets,
        trigger_registry=registry,
    )

    candidates = await triggering.process_available()

    assert [candidate.task_id for candidate in candidates] == [task_a]
    assert offsets.offsets["task-triggering"] == 2

    assert task_b not in [
        candidate.task_id
        for candidate in candidates
    ]


@pytest.mark.asyncio
async def test_process_available_resumes_from_consumer_offset() -> None:
    task_id = uuid4()

    repository = FakeEventRepository(
        [
            StoredEvent(event_seq=1, event=make_event()),
            StoredEvent(event_seq=2, event=make_event()),
        ]
    )

    registry = TriggerRegistry()
    registry.register(make_trigger(task_id))

    offsets = FakeConsumerOffset()
    offsets.offsets["task-triggering"] = 1

    triggering = TaskTriggering(
        event_repository=repository,
        consumer_offset_repository=offsets,
        trigger_registry=registry,
    )

    candidates = await triggering.process_available()

    assert len(candidates) == 1
    assert candidates[0].event_seq == 2
    assert offsets.offsets["task-triggering"] == 2