from datetime import UTC, datetime
from uuid import uuid4

from pinky_core.event.models import Event
from pinky_core.task.triggers import (
    ConditionOperator,
    EventTriggerDefinition,
    TaskTrigger,
    TriggerCondition,
    TriggerType,
)


def make_event(
    *,
    event_type: str = "email.received",
    payload: dict | None = None,
) -> Event:
    now = datetime.now(UTC)

    return Event(
        event_type=event_type,
        source="test",
        occurred_at=now,
        received_at=now,
        payload=payload or {},
    )


def test_event_trigger_matches_event_type() -> None:
    trigger = TaskTrigger(
        task_id=uuid4(),
        trigger_type=TriggerType.EVENT,
        definition=EventTriggerDefinition(
            event_type="email.received",
        ),
    )

    assert trigger.matches(make_event()) is True
    assert trigger.matches(make_event(event_type="file.created")) is False


def test_event_trigger_matches_conditions() -> None:
    trigger = TaskTrigger(
        task_id=uuid4(),
        trigger_type=TriggerType.EVENT,
        definition=EventTriggerDefinition(
            event_type="email.received",
            conditions=(
                TriggerCondition(
                    field="sender",
                    operator=ConditionOperator.EQ,
                    value="alice@example.com",
                ),
                TriggerCondition(
                    field="subject",
                    operator=ConditionOperator.CONTAINS,
                    value="invoice",
                ),
            ),
        ),
    )

    assert trigger.matches(
        make_event(
            payload={
                "sender": "alice@example.com",
                "subject": "March invoice",
            }
        )
    )

    assert not trigger.matches(
        make_event(
            payload={
                "sender": "bob@example.com",
                "subject": "March invoice",
            }
        )
    )


def test_disabled_trigger_does_not_match() -> None:
    trigger = TaskTrigger(
        task_id=uuid4(),
        trigger_type=TriggerType.EVENT,
        enabled=False,
        definition=EventTriggerDefinition(
            event_type="email.received",
        ),
    )

    assert trigger.matches(make_event()) is False