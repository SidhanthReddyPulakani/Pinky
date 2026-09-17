from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Event(BaseModel):
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

        return value.astimezone(UTC)
