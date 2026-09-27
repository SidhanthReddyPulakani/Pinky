from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TaskStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"


class Task(BaseModel):
    model_config = ConfigDict(frozen=True)

    task_id: UUID = Field(default_factory=uuid4)

    name: str
    goal: str
    execution_blueprint: dict[str, Any] = Field(default_factory=dict)

    status: TaskStatus = TaskStatus.DRAFT
    priority: int = 0

    constraints: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Task timestamps must be timezone-aware")

        return value.astimezone(UTC)