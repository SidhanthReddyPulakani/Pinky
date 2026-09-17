from sqlalchemy import Index, Integer, String, Text
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
        Text,
        nullable=False,
    )

    source: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    occurred_at: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    received_at: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    payload: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    event_metadata: Mapped[str] = mapped_column(
        "metadata",
        Text,
        nullable=False,
        default="{}",
    )
    causation_id: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    correlation_id: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    source_event_id: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    dedupe_key: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    schema_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )


Index(
    "uq_events_source_event",
    EventORM.source,
    EventORM.source_event_id,
    unique=True,
    sqlite_where=EventORM.source_event_id.is_not(None),
)

Index(
    "uq_events_source_dedupe",
    EventORM.source,
    EventORM.dedupe_key,
    unique=True,
    sqlite_where=EventORM.dedupe_key.is_not(None),
)
