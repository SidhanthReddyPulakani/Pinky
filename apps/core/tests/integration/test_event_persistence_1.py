from datetime import UTC, datetime
from pathlib import Path

import pytest

from pinky_core.event.intake import EventIntake
from pinky_core.event.models import IncomingEvent
from pinky_core.event.validation import EventValidation
from pinky_core.persistence.database import create_engine, create_session_factory
from pinky_core.persistence.event_repository import SQLiteEventRepository
from pinky_core.persistence.event_store import EventStore
from pinky_core.persistence.models import Base
from pinky_core.persistence.outbox_repository import OutboxRepository


@pytest.fixture
async def session_factory(tmp_path: Path):
    database_path = tmp_path / "integration.db"

    engine = create_engine(database_path)
    factory = create_session_factory(engine)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_event_intake_validation_and_persistence(
    session_factory,
):
    occurred_at = datetime(
        2026,
        9,
        18,
        10,
        0,
        tzinfo=UTC,
    )

    received_at = datetime(
        2026,
        9,
        18,
        10,
        0,
        1,
        tzinfo=UTC,
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

    validated = EventValidation().validate(event)

    assert validated == event

    store = EventStore(
        session_factory,
        clock=lambda: received_at,
    )

    await store.append(validated)

    event_repository = SQLiteEventRepository(session_factory)

    stored_event = await event_repository.get(event.event_id)

    assert stored_event == event

    source_event = await event_repository.find_by_source_event(
        "filesystem",
        "file-123",
    )

    assert source_event == event

    deduped_event = await event_repository.find_by_dedupe_key(
        "filesystem",
        "filesystem:file-123",
    )

    assert deduped_event == event

    stored_events = await event_repository.read_after(0)

    assert len(stored_events) == 1
    assert stored_events[0].event.event_id == event.event_id
    assert stored_events[0].event_seq > 0

    outbox_repository = OutboxRepository(session_factory)

    pending = await outbox_repository.get_pending()

    assert len(pending) == 1
    assert pending[0].event_id == str(event.event_id)
    assert pending[0].status == "PENDING"
    assert pending[0].attempt_count == 0