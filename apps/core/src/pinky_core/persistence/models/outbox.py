from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from . import Base


class OutboxORM(Base):
    __tablename__ = "outbox"

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'PUBLISHED')",
            name="ck_outbox_status",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_outbox_attempt_count",
        ),
        Index(
            "idx_outbox_pending",
            "status",
            "next_attempt_at",
            "created_at",
        ),
    )

    outbox_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )

    event_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("events.event_id"),
        nullable=False,
        unique=True,
    )

    created_at: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    last_attempt_at: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    next_attempt_at: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    published_at: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )