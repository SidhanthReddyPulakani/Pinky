from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pinky_core.event.models import Event


def make_event(**overrides) -> Event:
    values = {
        "event_type": "test.event",
        "source": "test",
        "occurred_at": datetime.now(UTC),
        "received_at": datetime.now(UTC),
        "payload": {"value": 42},
    }

    values.update(overrides)

    return Event(**values)


def test_event_generates_id():
    event = make_event()

    assert event.event_id is not None


def test_event_ids_are_unique():
    first = make_event()
    second = make_event()

    assert first.event_id != second.event_id


def test_event_is_immutable():
    event = make_event()

    with pytest.raises(ValidationError):
        event.source = "changed"


def test_naive_datetime_is_rejected():
    with pytest.raises(ValidationError):
        make_event(
            occurred_at=datetime.now(),
        )


def test_timestamps_are_normalized_to_utc():
    event = make_event()

    assert event.occurred_at.tzinfo == UTC
    assert event.received_at.tzinfo == UTC


def test_optional_metadata_defaults_to_none():
    event = make_event()

    assert event.source_event_id is None
    assert event.dedupe_key is None


def test_payload_is_preserved():
    payload = {
        "path": "/tmp/example.txt",
        "size": 1234,
        "modified": True,
    }

    event = make_event(payload=payload)

    assert event.payload == payload


def test_schema_version_defaults_to_one():
    event = make_event()

    assert event.schema_version == 1
