from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from pinky_core.event.models import Event
from pinky_core.persistence.database import (
    create_engine,
    create_session_factory,
)
from pinky_core.persistence.event_repository import SQLiteEventRepository
from pinky_core.persistence.models import Base
from pinky_core.persistence.models.event import EventORM


def make_event(
    *,
    source_event_id: str | None = None,
    dedupe_key: str | None = None,
) -> Event:
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
        source_event_id=source_event_id,
        dedupe_key=dedupe_key,
        schema_version=1,
    )
@pytest.fixture
async def repository(tmp_path: Path):
    database_path = tmp_path / "test.db"

    engine = create_engine(database_path)
    session_factory = create_session_factory(engine)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    repository = SQLiteEventRepository(session_factory)

    yield repository

    await engine.dispose()
@pytest.mark.asyncio
async def test_append_and_get(repository):
    event = make_event()

    await repository.append(event)

    result = await repository.get(event.event_id)

    assert result == event
@pytest.mark.asyncio
async def test_get_missing_event_returns_none(repository):
    result = await repository.get(uuid4())

    assert result is None
@pytest.mark.asyncio
async def test_find_by_source_event(repository):
    event = make_event(source_event_id="source-123")

    await repository.append(event)

    result = await repository.find_by_source_event(
        "filesystem",
        "source-123",
    )

    assert result == event
@pytest.mark.asyncio
async def test_find_by_dedupe_key(repository):
    event = make_event(dedupe_key="dedupe-123")

    await repository.append(event)

    result = await repository.find_by_dedupe_key(
        "filesystem",
        "dedupe-123",
    )

    assert result == event
@pytest.mark.asyncio
async def test_read_after_returns_events_in_sequence_order(repository):
    first = make_event()
    second = make_event()
    third = make_event()

    await repository.append(first)
    await repository.append(second)
    await repository.append(third)

    first_result = await repository.get(first.event_id)
    second_result = await repository.get(second.event_id)

    assert first_result is not None
    assert second_result is not None

    events = await repository.read_after(
        first_result.event_seq if hasattr(first_result, "event_seq") else 0
    )

    assert [event.event_id for event in events] == [
        first.event_id,
        second.event_id,
        third.event_id,
    ]

@pytest.mark.asyncio
async def test_read_after_returns_events_in_sequence_order(repository):
    first = make_event()
    second = make_event()
    third = make_event()

    await repository.append(first)
    await repository.append(second)
    await repository.append(third)

    stored_events = await repository.read_after(0)

    assert [stored.event.event_id for stored in stored_events] == [
        first.event_id,
        second.event_id,
        third.event_id,
    ]

    assert [
        stored.event_seq for stored in stored_events
    ] == sorted(
        stored.event_seq for stored in stored_events
    )

@pytest.mark.asyncio
async def test_read_after_excludes_given_sequence(repository):
    first = make_event()
    second = make_event()

    await repository.append(first)
    await repository.append(second)

    stored_events = await repository.read_after(1)

    assert [stored.event.event_id for stored in stored_events] == [
        second.event_id
    ]