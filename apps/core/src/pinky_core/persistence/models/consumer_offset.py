from sqlalchemy import CheckConstraint, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ConsumerOffsetORM(Base):
    __tablename__ = "consumer_offsets"

    __table_args__ = (
        CheckConstraint(
            "last_processed_event_seq >= 0",
            name="ck_consumer_offsets_last_processed_event_seq",
        ),
    )

    consumer_id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
    )

    last_processed_event_seq: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    updated_at: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
