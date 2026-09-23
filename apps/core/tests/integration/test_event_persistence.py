from datetime import UTC, datetime
from pathlib import Path

import pytest
import asyncio

from pinky_core.event.intake import EventIntake
from pinky_core.event.intake_result import Accepted, Duplicate, Rejected
from pinky_core.event.models import IncomingEvent
from pinky_core.event.validation import EventValidation
from pinky_core.persistence.database import (
    create_engine,
    create_session_factory,
)
from pinky_core.persistence.event_repository import SQLiteEventRepository
from pinky_core.persistence.event_store import EventStore
from pinky_core.persistence.models import Base
from pinky_core.persistence.models.outbox import OutboxORM

class CoordinatedRepository(SQLiteEventRepository):
    def __init__(self, session_factory, ready, release):
        super().__init__(session_factory)
        self._ready = ready
        self._release = release
        self._calls = 0

    async def find_by_dedupe_key(self, source, dedupe_key):
        result = await super().find_by_dedupe_key(
            source,
            dedupe_key,
        )

        self._calls += 1

        if self._calls == 2:
            self._ready.set()

        await self._release.wait()

        return result

@pytest.mark.asyncio
async def test_concurrent_duplicate_intake(
    session_factory,
):
    ready = asyncio.Event()
    release = asyncio.Event()

    repository = CoordinatedRepository(
        session_factory,
        ready,
        release,
    )

    validator = EventValidation()
    event_store = EventStore(session_factory)

    intake = EventIntake(
        validator=validator,
        repository=repository,
        event_store=event_store,
    )

    incoming = IncomingEvent(
        event_type="FILE_CHANGED",
        source="filesystem",
        source_event_id=None,
        dedupe_key="filesystem:concurrent-test",
        occurred_at=datetime.now(UTC),
        payload={"path": "/tmp/concurrent.txt"},
    )

    task1 = asyncio.create_task(
        intake.accept(incoming)
    )
    task2 = asyncio.create_task(
        intake.accept(incoming)
    )

    await asyncio.wait_for(
        ready.wait(),
        timeout=5,
    )

    release.set()

    results = await asyncio.wait_for(
        asyncio.gather(task1, task2),
        timeout=5,
    )

    accepted = [
        result
        for result in results
        if isinstance(result, Accepted)
    ]

    duplicates = [
        result
        for result in results
        if isinstance(result, Duplicate)
    ]

    assert len(accepted) == 1
    assert len(duplicates) == 1

    assert (
        accepted[0].event.event_id
        == duplicates[0].existing_event.event_id
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


def make_incoming_event() -> IncomingEvent:
    return IncomingEvent(
        event_type="FILE_CHANGED",
        source="filesystem",
        source_event_id="file-123",
        dedupe_key="filesystem:file-123",
        occurred_at=datetime(
            2026,
            9,
            18,
            10,
            0,
            tzinfo=UTC,
        ),
        payload={
            "path": "/tmp/example.txt",
        },
        event_metadata={
            "reader": "filesystem",
        },
    )


@pytest.fixture
def intake(session_factory):
    received_at = datetime(
        2026,
        9,
        18,
        10,
        0,
        1,
        tzinfo=UTC,
    )

    validator = EventValidation()
    repository = SQLiteEventRepository(session_factory)

    event_store = EventStore(
        session_factory,
        clock=lambda: received_at,
    )

    return EventIntake(
        validator=validator,
        repository=repository,
        event_store=event_store,
        clock=lambda: received_at,
    )


@pytest.mark.asyncio
async def test_event_flows_from_intake_to_persistence(
    session_factory,
    intake,
):
    incoming = make_incoming_event()

    result = await intake.accept(incoming)

    assert isinstance(result, Accepted)

    event = result.event

    repository = SQLiteEventRepository(session_factory)

    stored = await repository.get(event.event_id)

    assert stored is not None
    assert stored.event_id == event.event_id
    assert stored.event_type == "FILE_CHANGED"
    assert stored.source == "filesystem"
    assert stored.occurred_at == incoming.occurred_at
    assert stored.received_at == datetime(
        2026,
        9,
        18,
        10,
        0,
        1,
        tzinfo=UTC,
    )
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

    duplicate_result = await intake.accept(incoming)

    assert isinstance(duplicate_result, Duplicate)
    assert duplicate_result.existing_event.event_id == event.event_id

    replay = await repository.read_after(0)

    assert len(replay) == 1
    assert replay[0].event_seq > 0
    assert replay[0].event.event_id == event.event_id

    async with session_factory() as session:
        from sqlalchemy import func, select

        from pinky_core.persistence.models.event import EventORM

        event_count = await session.scalar(
            select(func.count()).select_from(EventORM)
        )

        outbox_count = await session.scalar(
            select(func.count()).select_from(OutboxORM)
        )

    assert event_count == 1
    assert outbox_count == 1


@pytest.mark.asyncio
async def test_duplicate_intake_returns_duplicate_without_second_persistence(
    session_factory,
    intake,
):
    incoming = make_incoming_event()

    result1 = await intake.accept(incoming)
    result2 = await intake.accept(incoming)

    assert isinstance(result1, Accepted)
    assert isinstance(result2, Duplicate)

    assert result1.event.event_id == result2.existing_event.event_id

    repository = SQLiteEventRepository(session_factory)

    replay = await repository.read_after(0)

    assert len(replay) == 1
    assert replay[0].event.event_id == result1.event.event_id

    stored = await repository.get(result1.event.event_id)

    assert stored is not None
    assert stored.event_id == result2.existing_event.event_id

    async with session_factory() as session:
        from sqlalchemy import func, select

        from pinky_core.persistence.models.event import EventORM

        event_count = await session.scalar(
            select(func.count()).select_from(EventORM)
        )

        outbox_count = await session.scalar(
            select(func.count()).select_from(OutboxORM)
        )

    assert event_count == 1
    assert outbox_count == 1

@pytest.mark.asyncio
async def test_rejected_intake_does_not_persist_event(session_factory):
    validator = EventValidation()
    repository = SQLiteEventRepository(session_factory)
    event_store = EventStore(session_factory)
    intake = EventIntake(
        validator=validator,
        repository=repository,
        event_store=event_store,
    )

    incoming = IncomingEvent(
        event_type="",
        source="filesystem",
        source_event_id="invalid-event",
        dedupe_key="filesystem:invalid-test",
        occurred_at=datetime.now(UTC),
        payload={"path": "/tmp/invalid.txt"},
    )

    result = await intake.accept(incoming)

    assert isinstance(result, Rejected)
    assert result.reason

    stored_event = await repository.find_by_source_event(
        "filesystem",
        "invalid-event",
    )
    assert stored_event is None

    replayed = await repository.read_after(0)
    assert replayed == []