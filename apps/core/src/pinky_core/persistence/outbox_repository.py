from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinky_core.persistence.models.outbox import OutboxORM


class OutboxRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def create_for_event(
        self,
        session: AsyncSession,
        event_id: UUID,
        *,
        created_at: str,
    ) -> None:
        row = OutboxORM(
            outbox_id=str(uuid4()),
            event_id=str(event_id),
            created_at=created_at,
            status="PENDING",
        )
        session.add(row)

    async def get_pending(
        self,
        *,
        limit: int = 100,
    ) -> list[OutboxORM]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(OutboxORM)
                .where(OutboxORM.status == "PENDING")
                .order_by(OutboxORM.created_at.asc())
                .limit(limit)
            )

            return list(result.scalars().all())
        
    async def mark_published(
        self,
        *,
        outbox_id: str,
        published_at: str,
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.get(OutboxORM, outbox_id)

                if row is None:
                    raise ValueError(f"Outbox entry not found: {outbox_id}")

                row.status = "PUBLISHED"
                row.published_at = published_at

    async def record_failure(
        self,
        *,
        outbox_id: str,
        attempt_count: int,
        last_attempt_at: str,
        next_attempt_at: str | None,
        last_error: str,
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.get(OutboxORM, outbox_id)

                if row is None:
                    raise ValueError(f"Outbox entry not found: {outbox_id}")

                row.attempt_count = attempt_count
                row.last_attempt_at = last_attempt_at
                row.next_attempt_at = next_attempt_at
                row.last_error = last_error