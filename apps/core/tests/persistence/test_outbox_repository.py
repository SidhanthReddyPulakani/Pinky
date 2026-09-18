from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from pinky_core.event.models import Event
from pinky_core.persistence.database import (
    create_engine,
    create_session_factory,
)
from pinky_core.persistence.event_repository import SQLiteEventRepository
from pinky_core.persistence.models import Base
from pinky_core.persistence.models.outbox import OutboxORM
from pinky_core.persistence.outbox_repository import OutboxRepository


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
            tzinfo=timezone.utc,
        ),
        received_at=datetime(
            2026,
            9,
            17,
            10,
            31,
            tzinfo=timezone.utc,
        ),
        payload={"path": "/tmp/test.txt"},
        event_metadata={"reader": "filesystem"},
        schema_version=1,
    )


@pytest.fixture
async def session_factory(tmp_path: Path):
    database_path = tmp_path / "test.db"

    engine = create_engine(database_path)
    factory = create_session_factory(engine)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield factory

    await engine.dispose()


@pytest.fixture
async def repositories(session_factory):
    return (
        OutboxRepository(session_factory),
        SQLiteEventRepository(session_factory),
    )


async def create_outbox_for_event(
    outbox_repository: OutboxRepository,
    session_factory,
    event_id,
) -> None:
    async with session_factory() as session:
        async with session.begin():
            await outbox_repository.create_for_event(
                session,
                event_id,
                created_at="2026-01-01T00:00:00+00:00",
            )


@pytest.mark.asyncio
async def test_create_for_event(
    session_factory,
    repositories,
):
    repository, event_repository = repositories
    event = make_event()

    await event_repository.append(event)
    await create_outbox_for_event(
        repository,
        session_factory,
        event.event_id,
    )

    rows = await repository.get_pending()

    assert len(rows) == 1
    assert rows[0].event_id == str(event.event_id)
    assert rows[0].status == "PENDING"
    assert rows[0].attempt_count == 0


@pytest.mark.asyncio
async def test_create_for_event_generates_unique_outbox_id(
    session_factory,
    repositories,
):
    repository, event_repository = repositories

    first_event = make_event()
    second_event = make_event()

    await event_repository.append(first_event)
    await event_repository.append(second_event)

    await create_outbox_for_event(
        repository,
        session_factory,
        first_event.event_id,
    )
    await create_outbox_for_event(
        repository,
        session_factory,
        second_event.event_id,
    )

    rows = await repository.get_pending()

    assert len(rows) == 2
    assert rows[0].outbox_id != rows[1].outbox_id


@pytest.mark.asyncio
async def test_get_pending_returns_only_pending_rows(
    session_factory,
    repositories,
):
    repository, event_repository = repositories
    event = make_event()

    await event_repository.append(event)
    await create_outbox_for_event(
        repository,
        session_factory,
        event.event_id,
    )

    rows = await repository.get_pending()

    assert len(rows) == 1
    assert rows[0].status == "PENDING"


@pytest.mark.asyncio
async def test_get_pending_respects_limit(
    session_factory,
    repositories,
):
    repository, event_repository = repositories
    events = [make_event() for _ in range(3)]

    for event in events:
        await event_repository.append(event)
        await create_outbox_for_event(
            repository,
            session_factory,
            event.event_id,
        )

    rows = await repository.get_pending(limit=2)

    assert len(rows) == 2


@pytest.mark.asyncio
async def test_create_for_event_requires_existing_event(
    session_factory,
):
    repository = OutboxRepository(session_factory)
    missing_event_id = uuid4()

    with pytest.raises(Exception):
        async with session_factory() as session:
            async with session.begin():
                await repository.create_for_event(
                    session,
                    missing_event_id,
                )


@pytest.mark.asyncio
async def test_outbox_has_foreign_key_to_event(
    session_factory,
):
    event = make_event()
    event_repository = SQLiteEventRepository(session_factory)
    repository = OutboxRepository(session_factory)

    await event_repository.append(event)

    await create_outbox_for_event(
        repository,
        session_factory,
        event.event_id,
    )

    async with session_factory() as session:
        result = await session.execute(
            select(OutboxORM).where(
                OutboxORM.event_id == str(event.event_id)
            )
        )

        row = result.scalar_one()

    assert row.event_id == str(event.event_id)