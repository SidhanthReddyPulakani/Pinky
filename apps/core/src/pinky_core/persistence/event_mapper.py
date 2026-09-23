import json
from datetime import UTC, datetime
from uuid import UUID

from pinky_core.event.models import Event
from pinky_core.persistence.models.event import EventORM


def _serialize_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def event_to_orm(event: Event) -> EventORM:
    return EventORM(
        event_id=str(event.event_id),
        event_type=event.event_type,
        source=event.source,
        occurred_at=_serialize_datetime(event.occurred_at),
        received_at=_serialize_datetime(event.received_at),
        payload=json.dumps(event.payload, separators=(",", ":")),
        event_metadata=json.dumps(event.event_metadata, separators=(",", ":")),
        causation_id=event.causation_id,
        correlation_id=event.correlation_id,
        source_event_id=event.source_event_id,
        dedupe_key=event.dedupe_key,
        schema_version=event.schema_version,
    )


def orm_to_event(row: EventORM) -> Event:
    return Event(
        event_id=UUID(row.event_id),
        event_type=row.event_type,
        source=row.source,
        occurred_at=datetime.fromisoformat(row.occurred_at),
        received_at=datetime.fromisoformat(row.received_at),
        payload=json.loads(row.payload),
        event_metadata=json.loads(row.event_metadata),
        causation_id=row.causation_id,
        correlation_id=row.correlation_id,
        source_event_id=row.source_event_id,
        dedupe_key=row.dedupe_key,
        schema_version=row.schema_version,
    )