from datetime import datetime, timezone

import pytest

from pinky_core.event.intake import EventIntake
from pinky_core.event.models import IncomingEvent
from pinky_core.event.validation import EventValidation
from pinky_core.persistence.event_repository import SQLiteEventRepository
from pinky_core.persistence.event_store import EventStore

from pathlib import Path

from pinky_core.persistence.database import (
    create_engine,
    create_session_factory,
)
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

@pytest.mark.asyncio
async def test_event_flows_from_intake_to_persistence(
    session_factory,
):
    occurred_at = datetime(
        2026,
        9,
        18,
        10,
        0,
        tzinfo=timezone.utc,
    )

    received_at = datetime(
        2026,
        9,
        18,
        10,
        0,
        1,
        tzinfo=timezone.utc,
    )

    incoming = IncomingEvent(
        event_type="FILE_CHANGED",
        source="filesystem",
        source_event_id="file-123",
        dedupe_key="filesystem:file-123",
        occurred_at=occurred_at,
        payload={
            "path": "/tmp/example.txt",
        },
        event_metadata={
            "reader": "filesystem",
        },
    )

    intake = EventIntake(
        clock=lambda: received_at,
    )

    event = await intake.accept(incoming)

    validator = EventValidation()
    validator.validate(event)

    store = EventStore(
        session_factory,
        clock=lambda: received_at,
    )

    await store.append(event)

    repository = SQLiteEventRepository(session_factory)

    stored = await repository.get(event.event_id)

    assert stored is not None
    assert stored.event_id == event.event_id
    assert stored.event_type == "FILE_CHANGED"
    assert stored.source == "filesystem"
    assert stored.occurred_at == occurred_at
    assert stored.received_at == received_at
    assert stored.payload == {
        "path": "/tmp/example.txt",
    }
    assert stored.event_metadata == {
        "reader": "filesystem",
    }

    by_source_event = await repository.find_by_source_event(
        "filesystem",
        "file-123",
    )

    assert by_source_event is not None
    assert by_source_event.event_id == event.event_id

    by_dedupe_key = await repository.find_by_dedupe_key(
        "filesystem",
        "filesystem:file-123",
    )

    assert by_dedupe_key is not None
    assert by_dedupe_key.event_id == event.event_id

    replay = await repository.read_after(0)

    assert len(replay) == 1
    assert replay[0].event_seq > 0
    assert replay[0].event.event_id == event.event_id