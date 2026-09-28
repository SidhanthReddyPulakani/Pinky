from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from uuid import UUID, uuid4

from pinky_core.event.intake import EventIntake
from pinky_core.event.validation import EventValidation
from pinky_core.integrations.filesystem.reader import FilesystemReader
from pinky_core.persistence.consumer_offset_repository import (
    ConsumerOffsetRepository,
)
from pinky_core.persistence.database import (
    create_engine,
    create_session_factory,
)
from pinky_core.persistence.event_repository import SQLiteEventRepository
from pinky_core.persistence.event_store import EventStore
from pinky_core.persistence.models import Base
from pinky_core.task.trigger_registry import TriggerRegistry
from pinky_core.task.triggering import TaskTriggering
from pinky_core.task.triggers import (
    ConditionOperator,
    EventTriggerDefinition,
    TaskTrigger,
    TriggerCondition,
    TriggerType,
)


LOGGER = logging.getLogger("task-triggering-smoke")

CONSUMER_ID = "smoke-task-triggering"
POLL_INTERVAL = 0.5
EVENT_BATCH_SIZE = 100


def make_trigger(
    *,
    task_id: UUID,
    filename: str,
) -> TaskTrigger:
    return TaskTrigger(
        task_id=task_id,
        trigger_type=TriggerType.EVENT,
        definition=EventTriggerDefinition(
            event_type="file.created",
            conditions=(
                TriggerCondition(
                    field="path",
                    operator=ConditionOperator.CONTAINS,
                    value=filename,
                ),
            ),
        ),
    )


def build_registry() -> tuple[TriggerRegistry, UUID, UUID]:
    registry = TriggerRegistry()

    task_1_id = uuid4()
    task_2_id = uuid4()

    # Task 1 has exactly ONE trigger.
    registry.register(
        make_trigger(
            task_id=task_1_id,
            filename="invoice.txt",
        )
    )

    # Task 2 has THREE triggers.
    registry.register(
        make_trigger(
            task_id=task_2_id,
            filename="test_D1.txt",
        )
    )

    registry.register(
        make_trigger(
            task_id=task_2_id,
            filename="test_D2.txt",
        )
    )

    registry.register(
        make_trigger(
            task_id=task_2_id,
            filename="test_D3.txt",
        )
    )

    return registry, task_1_id, task_2_id


def trigger_description(trigger: TaskTrigger) -> str:
    definition = trigger.definition

    if not definition.conditions:
        return definition.event_type

    condition_text = " AND ".join(
        (
            f"{condition.field} "
            f"{condition.operator.value} "
            f"{condition.value}"
        )
        for condition in definition.conditions
    )

    return f"{definition.event_type} + {condition_text}"


def print_event(
    *,
    event,
    event_seq: int,
) -> None:
    print()
    print("=" * 72)
    print("EVENT CAPTURED")
    print("=" * 72)

    print(f"event_id:        {event.event_id}")
    print(f"event_type:      {event.event_type}")
    print(f"source:          {event.source}")
    print(f"source_event_id: {event.source_event_id}")
    print(f"dedupe_key:      {event.dedupe_key}")
    print(f"occurred_at:     {event.occurred_at}")
    print(f"received_at:     {event.received_at}")
    print(f"event_metadata:  {event.event_metadata}")
    print(f"causation_id:    {event.causation_id}")
    print(f"correlation_id:  {event.correlation_id}")
    print(f"schema_version:  {event.schema_version}")
    print(f"event_seq:       {event_seq}")
    print(f"payload:         {event.payload}")


def print_trigger_results(
    *,
    event,
    registry: TriggerRegistry,
) -> None:
    print()
    print("TRIGGER EVALUATION")
    print("-" * 72)

    all_triggers = registry.matching_triggers(event)

    # Get every registered trigger for this event type so that the
    # smoke test can explicitly show MATCH / NO MATCH.
    event_type_triggers = []

    for trigger in registry._by_event_type.get(event.event_type, []):
        event_type_triggers.append(trigger)

    if not event_type_triggers:
        print("No triggers registered for this event type.")
        return

    matching_ids = {trigger.trigger_id for trigger in all_triggers}

    for trigger in event_type_triggers:
        status = (
            "MATCH"
            if trigger.trigger_id in matching_ids
            else "NO MATCH"
        )

        print(
            f"{status:8} "
            f"task_id={trigger.task_id} "
            f"trigger_id={trigger.trigger_id}"
        )
        print(f"         {trigger_description(trigger)}")


async def process_events(
    *,
    triggering: TaskTriggering,
    event_repository: SQLiteEventRepository,
    offset_repository: ConsumerOffsetRepository,
    registry: TriggerRegistry,
    stop_event: asyncio.Event,
) -> None:
    while not stop_event.is_set():
        offset = await offset_repository.get(CONSUMER_ID)

        last_processed_seq = (
            offset.last_processed_event_seq
            if offset is not None
            else 0
        )

        events = await event_repository.read_after(
            last_processed_seq,
            limit=EVENT_BATCH_SIZE,
        )

        if not events:
            await asyncio.sleep(POLL_INTERVAL)
            continue

        for event in events:
            # The event is already persisted. We display the exact
            # Event object that the triggering subsystem receives.
            print_event(
                event=event.event,
                event_seq=event.event_seq,
            )

            print_trigger_results(
                event=event.event,
                registry=registry,
            )

            # Use the real TaskTriggering implementation to perform
            # the actual trigger evaluation and advance the consumer.
            candidates = await triggering.process_event(
                event_seq=event.event_seq,
                event=event.event,
            )

            print()
            print("ACTIVATION")
            print("-" * 72)

            if not candidates:
                print("No Task activation.")
                continue

            for candidate in candidates:
                print(
                    f"TASK ACTIVATION CANDIDATE: "
                    f"task_id={candidate.task_id} "
                    f"event_seq={candidate.event_seq}"
                )


async def main() -> None:
    project_root = Path(__file__).resolve().parents[1]

    database_path = project_root / "pinky_task_triggering_smoke.db"

    # Keep the smoke-test database out of normal logging.
    print(f"Database: {database_path}")
    print("Filesystem root: C:\\")
    print("Filesystem recursive: True")

    engine = create_engine(database_path)
    session_factory = create_session_factory(engine)

    # Smoke-test database: create the current schema directly.
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    event_repository = SQLiteEventRepository(
        session_factory,
    )

    event_store = EventStore(
        session_factory,
    )

    intake = EventIntake(
        validator=EventValidation(),
        repository=event_repository,
        event_store=event_store,
    )

    offset_repository = ConsumerOffsetRepository(
        session_factory,
    )

    registry, task_1_id, task_2_id = build_registry()

    triggering = TaskTriggering(
        event_repository=event_repository,
        consumer_offset_repository=offset_repository,
        trigger_registry=registry,
        consumer_id=CONSUMER_ID,
    )
    ignored_paths = {
        database_path,
        database_path.with_name(database_path.name + "-wal"),
        database_path.with_name(database_path.name + "-shm"),
    }
    reader = FilesystemReader(
        root=Path("C:/"),
        intake=intake,
        recursive=True,
    )

    stop_event = asyncio.Event()

    reader_task = asyncio.create_task(
        reader.run(),
        name="filesystem-reader",
    )

    processing_task = asyncio.create_task(
        process_events(
            triggering=triggering,
            event_repository=event_repository,
            offset_repository=offset_repository,
            registry=registry,
            stop_event=stop_event,
        ),
        name="event-trigger-processing",
    )

    print()
    print("=" * 72)
    print("TASK TRIGGERING SMOKE TEST")
    print("=" * 72)
    print()
    print(f"Task 1: {task_1_id}")
    print("  file.created + path contains invoice.txt")
    print()
    print(f"Task 2: {task_2_id}")
    print("  file.created + path contains test_D1.txt")
    print("  file.created + path contains test_D2.txt")
    print("  file.created + path contains test_D3.txt")
    print()
    print("Create these files ANYWHERE under C:\\")
    print()
    print("  invoice.txt")
    print("  test_D1.txt")
    print("  test_D2.txt")
    print("  test_D3.txt")
    print()
    print("For every captured event the test will show:")
    print("  1. Event attributes")
    print("  2. Trigger MATCH / NO MATCH")
    print("  3. Task activation candidate")
    print()
    print("Press Ctrl+C to stop.")
    print()

    try:
        await reader_task

    except asyncio.CancelledError:
        pass

    finally:
        stop_event.set()

        await reader.stop()

        processing_task.cancel()

        try:
            await processing_task
        except asyncio.CancelledError:
            pass

        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass