from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from pinky_core.event.models import Event
from pinky_core.persistence.database import (
    create_engine,
    create_session_factory,
)
from pinky_core.persistence.models import Base
from pinky_core.persistence.outbox_repository import OutboxRepository
from pinky_core.persistence.event_repository import (
        SQLiteEventRepository,
)

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
async def repository(tmp_path: Path):
    database_path = tmp_path / "test.db"

    engine = create_engine(database_path)
    session_factory = create_session_factory(engine)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    repository = OutboxRepository(session_factory)

    yield repository

    await engine.dispose()


@pytest.fixture
async def event_repository(tmp_path: Path):
    database_path = tmp_path / "test.db"

    engine = create_engine(database_path)
    session_factory = create_session_factory(engine)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)



    repository = SQLiteEventRepository(session_factory)

    yield repository

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_for_event(repository, event_repository):
    event = make_event()

    await event_repository.append(event)
    await repository.create_for_event(event.event_id)

    rows = await repository.get_pending()

    assert len(rows) == 1
    assert rows[0].event_id == str(event.event_id)
    assert rows[0].status == "PENDING"
    assert rows[0].attempt_count == 0


@pytest.mark.asyncio
async def test_create_for_event_generates_unique_outbox_id(
    repository,
    event_repository,
):
    first_event = make_event()
    second_event = make_event()

    await event_repository.append(first_event)
    await event_repository.append(second_event)

    await repository.create_for_event(first_event.event_id)
    await repository.create_for_event(second_event.event_id)

    rows = await repository.get_pending()

    assert len(rows) == 2
    assert rows[0].outbox_id != rows[1].outbox_id


@pytest.mark.asyncio
async def test_get_pending_returns_only_pending_rows(
    repository,
    event_repository,
):
    event = make_event()

    await event_repository.append(event)
    await repository.create_for_event(event.event_id)

    rows = await repository.get_pending()

    assert len(rows) == 1
    assert rows[0].status == "PENDING"


@pytest.mark.asyncio
async def test_get_pending_respects_limit(
    repository,
    event_repository,
):
    events = [make_event() for _ in range(3)]

    for event in events:
        await event_repository.append(event)
        await repository.create_for_event(event.event_id)

    rows = await repository.get_pending(limit=2)

    assert len(rows) == 2


@pytest.mark.asyncio
async def test_outbox_requires_existing_event(
    repository,
):
    missing_event_id = uuid4()

    with pytest.raises(Exception):
        await repository.create_for_event(missing_event_id)