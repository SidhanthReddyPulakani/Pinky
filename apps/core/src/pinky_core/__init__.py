from datetime import UTC, datetime, timezone

import pytest
from pydantic import ValidationError

from pinky_core.event.models import Event


def test_event_generates_id():
    event = Event(
        event_type="test.event",
        source="test",
        occurred_at=datetime.now(UTC),
        received_at=datetime.now(UTC),
        payload={"value": 42},
    )

    assert event.event_id is not None


def test_event_is_immutable():
    event = Event(
        event_type="test.event",
        source="test",
        occurred_at=datetime.now(UTC),
        received_at=datetime.now(UTC),
        payload={"value": 42},
    )

    with pytest.raises(ValidationError):
        event.source = "changed"


def test_naive_datetime_is_rejected():
    with pytest.raises(ValidationError):
        Event(
            event_type="test.event",
            source="test",
            occurred_at=datetime.now(),
            received_at=datetime.now(),
            payload={},
        )


def test_timestamps_are_normalized_to_utc():
    event = Event(
        event_type="test.event",
        source="test",
        occurred_at=datetime(
            2026,
            9,
            16,
            14,
            0,
            tzinfo=UTC,
        ),
        received_at=datetime(
            2026,
            9,
            16,
            14,
            1,
            tzinfo=UTC,
        ),
        payload={},
    )

    assert event.occurred_at.tzinfo == UTC
    assert event.received_at.tzinfo == UTC
