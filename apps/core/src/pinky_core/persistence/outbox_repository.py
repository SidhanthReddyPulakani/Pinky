from datetime import datetime, timezone
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
    ) -> None:
        row = OutboxORM(
            outbox_id=str(uuid4()),
            event_id=str(event_id),
            created_at=datetime.now(timezone.utc).isoformat(),
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