from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinky_core.event.models import Event
from pinky_core.persistence.event_mapper import event_to_orm
from pinky_core.persistence.models.outbox import OutboxORM


class EventStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def append(self, event: Event) -> None:
        event_row = event_to_orm(event)

        outbox_row = OutboxORM(
            outbox_id=str(uuid4()),
            event_id=str(event.event_id),
            created_at=event.received_at.isoformat(),
            status="PENDING",
        )

        async with self._session_factory() as session:
            async with session.begin():
                session.add(event_row)
                session.add(outbox_row)