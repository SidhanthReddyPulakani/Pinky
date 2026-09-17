from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IncomingEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_type: str
    source: str

    source_event_id: str | None = None
    dedupe_key: str | None = None

    occurred_at: datetime
    payload: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)

    causation_id: str | None = None
    correlation_id: str | None = None

    schema_version: int = 1
    
    @field_validator("occurred_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Event timestamps must be timezone-aware")

        return value.astimezone(timezone.utc)


class Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: UUID = Field(default_factory=uuid4)

    event_type: str
    source: str

    occurred_at: datetime
    received_at: datetime

    payload: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)

    causation_id: str | None = None
    correlation_id: str | None = None

    source_event_id: str | None = None
    dedupe_key: str | None = None

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
            occurred_at=incoming.occurred_at,
            received_at=received_at,
            payload=incoming.payload,
            metadata=incoming.metadata,
            causation_id=incoming.causation_id,
            correlation_id=incoming.correlation_id,
            source_event_id=incoming.source_event_id,
            dedupe_key=incoming.dedupe_key,
            schema_version=incoming.schema_version,
        )