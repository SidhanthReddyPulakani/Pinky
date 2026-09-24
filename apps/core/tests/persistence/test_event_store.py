from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from pinky_core.event.models import Event
from pinky_core.persistence.database import (
    create_engine,
    create_session_factory,
)
from pinky_core.persistence.event_store import EventStore
from pinky_core.persistence.models import Base
from pinky_core.persistence.models.event import EventORM
from pinky_core.persistence.models.outbox import OutboxORM


def make_event() -> Event:
    return Event(
        event_id=uuid4(),
        event_type="FILE_CHANGED",
        source="filesystem",
        occurred_at=datetime(
            2026,
            9,
            17,
            10,
            30,
            tzinfo=UTC,
        ),
        received_at=datetime(
            2026,
            9,
            17,
            10,
            31,
            tzinfo=UTC,
        ),
        payload={"path": "/tmp/test.txt"},
        event_metadata={"reader": "filesystem"},
        schema_version=1,
    )


@pytest.fixture
async def session_factory(tmp_path: Path):
    database_path = tmp_path / "test.db"

    engine = create_engine(database_path)
    session_factory = create_session_factory(engine)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield session_factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_append_persists_event_and_outbox(session_factory):
    event = make_event()
    store = EventStore(session_factory)

    await store.append(event)

    async with session_factory() as session:
        event_row = await session.scalar(
            select(EventORM).where(EventORM.event_id == str(event.event_id))
        )

        outbox_row = await session.scalar(
            select(OutboxORM).where(OutboxORM.event_id == str(event.event_id))
        )

    assert event_row is not None
    assert outbox_row is not None
    assert outbox_row.status == "PENDING"


@pytest.mark.asyncio
async def test_append_is_atomic_when_outbox_insert_fails(
    session_factory,
):
    event = make_event()

    async with session_factory() as session:
        async with session.begin():
            conflicting_event = EventORM(
                event_id=str(uuid4()),
                event_type="EXISTING_EVENT",
                source="test",
                occurred_at=event.occurred_at.isoformat(),
                received_at=event.received_at.isoformat(),
                payload="{}",
                event_metadata="{}",
                schema_version=1,
            )

            session.add(conflicting_event)

    with pytest.raises(Exception):
        async with session_factory() as session:
            async with session.begin():
                session.add(
                    EventORM(
                        event_id=str(event.event_id),
                        event_type=event.event_type,
                        source=event.source,
                        occurred_at=event.occurred_at.isoformat(),
                        received_at=event.received_at.isoformat(),
                        payload="{}",
                        event_metadata="{}",
                        schema_version=event.schema_version,
                    )
                )

                session.add(
                    OutboxORM(
                        outbox_id=str(uuid4()),
                        event_id=str(event.event_id),
                        created_at=event.received_at.isoformat(),
                        status="PENDING",
                    )
                )

                session.add(
                    OutboxORM(
                        outbox_id=str(uuid4()),
                        event_id=str(event.event_id),
                        created_at=event.received_at.isoformat(),
                        status="PENDING",
                    )
                )

    async with session_factory() as session:
        event_row = await session.scalar(
            select(EventORM).where(EventORM.event_id == str(event.event_id))
        )

        outbox_row = await session.scalar(
            select(OutboxORM).where(OutboxORM.event_id == str(event.event_id))
        )

    assert event_row is None
    assert outbox_row is None
