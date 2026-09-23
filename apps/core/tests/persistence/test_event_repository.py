from datetime import UTC, datetime
from uuid import uuid4

import pytest

from pinky_core.event.models import Event
from pinky_core.persistence.database import create_engine, create_session_factory
from pinky_core.persistence.event_repository import SQLiteEventRepository
from pinky_core.persistence.event_store import EventStore
from pinky_core.persistence.models import Base


def make_event(
    *,
    source_event_id: str | None = None,
    dedupe_key: str | None = None,
) -> Event:
    now = datetime.now(UTC)

    return Event(
        event_id=uuid4(),
        event_type="test.event",
        source="test-source",
        occurred_at=now,
        received_at=now,
        payload={"value": "test"},
        source_event_id=source_event_id,
        dedupe_key=dedupe_key,
    )


@pytest.fixture
async def session_factory(tmp_path):
    database_path = tmp_path / "test.db"

    engine = create_engine(database_path)
    factory = create_session_factory(engine)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield factory

    await engine.dispose()


@pytest.fixture
async def repository(session_factory):
    return SQLiteEventRepository(session_factory)


@pytest.fixture
async def event_store(session_factory):
    return EventStore(session_factory)


@pytest.mark.asyncio
async def test_get_missing_event_returns_none(repository):
    result = await repository.get(uuid4())

    assert result is None


@pytest.mark.asyncio
async def test_find_by_source_event(repository, event_store):
    event = make_event(source_event_id="source-123")

    await event_store.append(event)

    result = await repository.find_by_source_event(
        event.source,
        "source-123",
    )

    assert result == event


@pytest.mark.asyncio
async def test_find_by_dedupe_key(repository, event_store):
    event = make_event(dedupe_key="dedupe-123")

    await event_store.append(event)

    result = await repository.find_by_dedupe_key(
        event.source,
        "dedupe-123",
    )

    assert result == event


@pytest.mark.asyncio
async def test_read_after_returns_events_in_sequence_order(
    repository,
    event_store,
):
    first = make_event()
    second = make_event()
    third = make_event()

    await event_store.append(first)
    await event_store.append(second)
    await event_store.append(third)

    events = await repository.read_after(0)

    assert [stored.event.event_id for stored in events] == [
        first.event_id,
        second.event_id,
        third.event_id,
    ]


@pytest.mark.asyncio
async def test_read_after_excludes_given_sequence(
    repository,
    event_store,
):
    first = make_event()
    second = make_event()

    await event_store.append(first)
    await event_store.append(second)

    all_events = await repository.read_after(0)

    assert len(all_events) == 2

    first_seq = all_events[0].event_seq

    remaining = await repository.read_after(first_seq)

    assert len(remaining) == 1
    assert remaining[0].event.event_id == second.event_id