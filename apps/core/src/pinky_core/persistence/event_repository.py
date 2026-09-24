from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinky_core.event.models import Event
from pinky_core.event.repository import EventRepository
from pinky_core.persistence.event_mapper import orm_to_event
from pinky_core.persistence.event_record import StoredEvent
from pinky_core.persistence.models.event import EventORM


class SQLiteEventRepository(EventRepository):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def get(self, event_id: UUID) -> Event | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(EventORM).where(EventORM.event_id == str(event_id))
            )

            row = result.scalar_one_or_none()

            if row is None:
                return None

            return orm_to_event(row)

    async def find_by_source_event(
        self,
        source: str,
        source_event_id: str,
    ) -> Event | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(EventORM).where(
                    EventORM.source == source,
                    EventORM.source_event_id == source_event_id,
                )
            )

            row = result.scalar_one_or_none()

            if row is None:
                return None

            return orm_to_event(row)

    async def find_by_dedupe_key(
        self,
        source: str,
        dedupe_key: str,
    ) -> Event | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(EventORM).where(
                    EventORM.source == source,
                    EventORM.dedupe_key == dedupe_key,
                )
            )

            row = result.scalar_one_or_none()

            if row is None:
                return None

            return orm_to_event(row)

    async def read_after(
        self,
        event_seq: int,
        *,
        limit: int = 100,
    ) -> list[StoredEvent]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(EventORM)
                .where(EventORM.event_seq > event_seq)
                .order_by(EventORM.event_seq.asc())
                .limit(limit)
            )

            rows = result.scalars().all()

            return [
                StoredEvent(
                    event_seq=row.event_seq,
                    event=orm_to_event(row),
                )
                for row in rows
            ]
