from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pinky_core.persistence.models.consumer_offset import ConsumerOffsetORM


class ConsumerOffsetRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def get(
        self,
        consumer_id: str,
    ) -> ConsumerOffsetORM | None:
        async with self._session_factory() as session:
            return await session.get(
                ConsumerOffsetORM,
                consumer_id,
            )

    async def advance(
        self,
        *,
        consumer_id: str,
        event_seq: int,
        updated_at: str | None = None,
    ) -> None:
        if event_seq < 0:
            raise ValueError("event_seq must be >= 0")

        timestamp = updated_at or datetime.now(UTC).isoformat()

        async with self._session_factory() as session:
            async with session.begin():
                row = await session.get(
                    ConsumerOffsetORM,
                    consumer_id,
                )

                if row is None:
                    row = ConsumerOffsetORM(
                        consumer_id=consumer_id,
                        last_processed_event_seq=event_seq,
                        updated_at=timestamp,
                    )
                    session.add(row)
                    return

                if event_seq < row.last_processed_event_seq:
                    raise ValueError("consumer offset cannot move backwards")

                row.last_processed_event_seq = event_seq
                row.updated_at = timestamp
