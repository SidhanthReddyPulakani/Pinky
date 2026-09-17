from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from .event import EventORM
from .outbox import OutboxORM

__all__ = [
    "Base",
    "EventORM",
    "OutboxORM",
]