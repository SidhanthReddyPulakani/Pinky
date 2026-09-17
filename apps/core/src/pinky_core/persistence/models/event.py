from datetime import datetime

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from . import Base


class EventORM(Base):
    __tablename__ = "events"

    event_seq: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    event_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
    )

    event_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    source: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    occurred_at: Mapped[datetime] = mapped_column(
        nullable=False,
    )

    received_at: Mapped[datetime] = mapped_column(
        nullable=False,
    )

    payload: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    metadata: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )

    causation_id: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    correlation_id: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    source_event_id: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    dedupe_key: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    schema_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )