from datetime import datetime, timezone
from uuid import uuid4

from pinky_core.event.models import Event
from pinky_core.persistence.event_mapper import (
    event_to_orm,
    orm_to_event,
)


def make_event() -> Event:
    return Event(
        event_id=uuid4(),
        event_type="FILE_CHANGED",
        source="filesystem",
        occurred_at=datetime(
            2026, 9, 17, 10, 30, tzinfo=timezone.utc
        ),
        received_at=datetime(
            2026, 9, 17, 10, 31, tzinfo=timezone.utc
        ),
        payload={"path": "/tmp/test.txt", "size": 42},
        event_metadata={"reader": "filesystem-reader"},
        causation_id="cause-123",
        correlation_id="corr-456",
        source_event_id="source-789",
        dedupe_key="dedupe-789",
        schema_version=1,
    )


def test_event_to_orm_serializes_event():
    event = make_event()

    row = event_to_orm(event)

    assert row.event_id == str(event.event_id)
    assert row.event_type == event.event_type
    assert row.source == event.source
    assert row.payload == '{"path":"/tmp/test.txt","size":42}'
    assert row.event_metadata == '{"reader":"filesystem-reader"}'
    assert row.causation_id == event.causation_id
    assert row.correlation_id == event.correlation_id
    assert row.source_event_id == event.source_event_id
    assert row.dedupe_key == event.dedupe_key


def test_orm_to_event_deserializes_event():
    event = make_event()

    row = event_to_orm(event)
    restored = orm_to_event(row)

    assert restored == event


def test_event_round_trip_preserves_payload_and_metadata():
    event = make_event()

    restored = orm_to_event(event_to_orm(event))

    assert restored.payload == event.payload
    assert restored.event_metadata == event.event_metadata