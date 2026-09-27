from datetime import UTC, datetime
from uuid import uuid4

from pinky_core.event.models import Event
from pinky_core.task.trigger_registry import TriggerRegistry
from pinky_core.task.triggers import (
    ConditionOperator,
    EventTriggerDefinition,
    TaskTrigger,
    TriggerCondition,
    TriggerType,
)


def make_event(payload: dict) -> Event:
    now = datetime.now(UTC)

    return Event(
        event_type="email.received",
        source="test",
        occurred_at=now,
        received_at=now,
        payload=payload,
    )


def make_trigger(
    task_id,
    *,
    sender: str | None = None,
) -> TaskTrigger:
    conditions = ()

    if sender is not None:
        conditions = (
            TriggerCondition(
                field="sender",
                operator=ConditionOperator.EQ,
                value=sender,
            ),
        )

    return TaskTrigger(
        task_id=task_id,
        trigger_type=TriggerType.EVENT,
        definition=EventTriggerDefinition(
            event_type="email.received",
            conditions=conditions,
        ),
    )


def test_registry_returns_matching_triggers() -> None:
    registry = TriggerRegistry()

    task_a = uuid4()
    task_b = uuid4()

    registry.register(make_trigger(task_a, sender="alice@example.com"))
    registry.register(make_trigger(task_b, sender="bob@example.com"))

    matches = registry.matching_task_ids(
        make_event({"sender": "alice@example.com"})
    )

    assert matches == [task_a]


def test_multiple_matching_triggers_for_same_task_return_one_task() -> None:
    registry = TriggerRegistry()

    task_id = uuid4()

    registry.register(make_trigger(task_id))
    registry.register(make_trigger(task_id, sender="alice@example.com"))

    matches = registry.matching_task_ids(
        make_event({"sender": "alice@example.com"})
    )

    assert matches == [task_id]


def test_unrelated_event_type_is_not_scanned_as_match() -> None:
    registry = TriggerRegistry()

    task_id = uuid4()
    registry.register(make_trigger(task_id))

    now = datetime.now(UTC)

    event = Event(
        event_type="file.created",
        source="test",
        occurred_at=now,
        received_at=now,
        payload={},
    )

    assert registry.matching_task_ids(event) == []


def test_unregister_removes_trigger() -> None:
    registry = TriggerRegistry()

    trigger = make_trigger(uuid4())
    registry.register(trigger)

    assert registry.matching_triggers(
        make_event({"sender": "alice@example.com"})
    )

    registry.unregister(trigger.trigger_id)

    assert registry.matching_triggers(
        make_event({"sender": "alice@example.com"})
    ) == []