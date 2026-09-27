from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pinky_core.event.models import Event


class TriggerType(StrEnum):
    EVENT = "EVENT"


class ConditionOperator(StrEnum):
    EQ = "eq"
    CONTAINS = "contains"


class TriggerCondition(BaseModel):
    model_config = ConfigDict(frozen=True)

    field: str
    operator: ConditionOperator
    value: Any


class EventTriggerDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_type: str
    conditions: tuple[TriggerCondition, ...] = ()

    def matches(self, event: Event) -> bool:
        if event.event_type != self.event_type:
            return False

        return all(
            condition_matches(condition, event.payload)
            for condition in self.conditions
        )


def condition_matches(
    condition: TriggerCondition,
    payload: dict[str, Any],
) -> bool:
    value = payload.get(condition.field)

    if condition.operator is ConditionOperator.EQ:
        return value == condition.value

    if condition.operator is ConditionOperator.CONTAINS:
        if not isinstance(value, str):
            return False

        return str(condition.value) in value

    return False


class TaskTrigger(BaseModel):
    model_config = ConfigDict(frozen=True)

    trigger_id: UUID = Field(default_factory=uuid4)
    task_id: UUID

    trigger_type: TriggerType
    definition: EventTriggerDefinition

    enabled: bool = True

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Trigger timestamps must be timezone-aware")

        return value.astimezone(UTC)

    def matches(self, event: Event) -> bool:
        if not self.enabled:
            return False

        return self.definition.matches(event)