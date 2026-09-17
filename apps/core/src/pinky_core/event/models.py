from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IncomingEvent(BaseModel):
    """
    Event data submitted by an Event Reader before Pinky assigns
    final Event metadata.
    """

    model_config = ConfigDict(frozen=True)

    event_type: str
    source: str

    source_event_id: str | None = None
    dedupe_key: str | None = None

    occurred_at: datetime
    payload: dict[str, Any]

    schema_version: int = 1

    @field_validator("occurred_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Event timestamps must be timezone-aware")

        return value.astimezone(timezone.utc)


class Event(BaseModel):
    """
    Immutable representation of a historical event observed by Pinky.
    """

    model_config = ConfigDict(frozen=True)

    event_id: UUID = Field(default_factory=uuid4)

    event_type: str
    source: str

    source_event_id: str | None = None
    dedupe_key: str | None = None

    occurred_at: datetime
    received_at: datetime

    payload: dict[str, Any]

    schema_version: int = 1

    @field_validator("occurred_at", "received_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Event timestamps must be timezone-aware")

        return value.astimezone(timezone.utc)

    @classmethod
    def from_incoming(
        cls,
        incoming: IncomingEvent,
        *,
        received_at: datetime,
    ) -> "Event":
        return cls(
            event_type=incoming.event_type,
            source=incoming.source,
            source_event_id=incoming.source_event_id,
            dedupe_key=incoming.dedupe_key,
            occurred_at=incoming.occurred_at,
            received_at=received_at,
            payload=incoming.payload,
            schema_version=incoming.schema_version,
        )