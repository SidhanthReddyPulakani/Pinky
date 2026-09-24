from pathlib import Path
from uuid import uuid4

import pytest

from pinky_core.event.models import Event
from pinky_core.persistence.consumer_offset_repository import (
    ConsumerOffsetRepository,
)
from pinky_core.persistence.database import (
    create_engine,
    create_session_factory,
)
from pinky_core.persistence.event_repository import SQLiteEventRepository
from pinky_core.persistence.event_store import EventStore
from pinky_core.persistence.models import Base


@pytest.fixture
async def session_factory(tmp_path: Path):
    database_path = tmp_path / "test.db"

    engine = create_engine(database_path)
    factory = create_session_factory(engine)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield factory

    await engine.dispose()


def make_event() -> Event:
    from datetime import UTC, datetime

    now = datetime.now(UTC)

    return Event(
        event_id=uuid4(),
        event_type="TEST_EVENT",
        source="test",
        occurred_at=now,
        received_at=now,
        payload={"value": 1},
        event_metadata={},
        schema_version=1,
    )


@pytest.mark.asyncio
async def test_consumer_replays_event_when_offset_commit_is_skipped(
    session_factory,
):
    event_store = EventStore(session_factory)
    offset_repository = ConsumerOffsetRepository(session_factory)

    event = make_event()

    await event_store.append(event)
    event_repository = SQLiteEventRepository(session_factory)

    stored_events = await event_repository.read_after(0)
    assert len(stored_events) == 1
    assert stored_events[0].event.event_id == event.event_id
    assert stored_events[0].event_seq > 0
    processed_events: list[str] = []

    async def process_event(processed_event: Event) -> None:
        processed_events.append(str(processed_event.event.event_id))

    # First processing succeeds.
    await process_event(stored_events[0])

    # Simulate a crash before the offset is advanced.
    #
    # The processing happened, but there is intentionally
    # no call to offset_repository.advance() here.
    offset = await offset_repository.get("test-consumer")

    assert offset is None

    # Recovery/replay starts from the unchanged cursor.
    replay_offset = 0
    replayed_events = await event_repository.read_after(
        replay_offset,
    )

    assert len(replayed_events) == 1
    assert replayed_events[0].event.event_id == event.event_id

    # Consumer processes the replay.
    await process_event(replayed_events[0])

    assert processed_events == [
        str(event.event_id),
        str(event.event_id),
    ]
