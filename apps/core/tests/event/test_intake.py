from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from pinky_core.event.intake import EventIntake
from pinky_core.event.intake_result import Accepted, Duplicate, Rejected
from pinky_core.event.models import Event, IncomingEvent
from pinky_core.event.validation import EventValidation


class FailingEventStore:
    async def append(self, event):
        raise IntegrityError(
            "INSERT INTO events ...",
            {},
            Exception("duplicate"),
        )


class StubRepository:
    def __init__(self, existing_event=None):
        self.existing_event = existing_event

    async def find_by_source_event(self, source, source_event_id):
        return self.existing_event

    async def find_by_dedupe_key(self, source, dedupe_key):
        return self.existing_event


class StubEventStore:
    def __init__(self):
        self.appended = []

    async def append(self, event):
        self.appended.append(event)


def make_incoming(**overrides):
    values = {
        "event_type": "FILE_CHANGED",
        "source": "filesystem",
        "source_event_id": "event-1",
        "dedupe_key": "filesystem:event-1",
        "occurred_at": datetime.now(UTC),
        "payload": {"path": "/tmp/test.txt"},
    }
    values.update(overrides)
    return IncomingEvent(**values)


@pytest.mark.asyncio
async def test_accept_returns_accepted_and_persists_event():
    repository = StubRepository()
    event_store = StubEventStore()
    intake = EventIntake(
        validator=EventValidation(),
        repository=repository,
        event_store=event_store,
    )

    result = await intake.accept(make_incoming())

    assert isinstance(result, Accepted)
    assert len(event_store.appended) == 1
    assert event_store.appended[0] == result.event


@pytest.mark.asyncio
async def test_existing_source_event_returns_duplicate():
    existing_event = Event.from_incoming(
        make_incoming(),
        received_at=datetime.now(UTC),
    )
    repository = StubRepository(existing_event)
    event_store = StubEventStore()
    intake = EventIntake(
        validator=EventValidation(),
        repository=repository,
        event_store=event_store,
    )

    result = await intake.accept(make_incoming())

    assert isinstance(result, Duplicate)
    assert result.existing_event == existing_event
    assert event_store.appended == []


@pytest.mark.asyncio
async def test_validation_failure_returns_rejected():
    repository = StubRepository()
    event_store = StubEventStore()
    intake = EventIntake(
        validator=EventValidation(),
        repository=repository,
        event_store=event_store,
    )

    result = await intake.accept(make_incoming(event_type=""))

    assert isinstance(result, Rejected)
    assert result.reason
    assert event_store.appended == []


@pytest.mark.asyncio
async def test_integrity_error_returns_duplicate_when_existing_event_is_found():
    existing_event = Event.from_incoming(
        make_incoming(),
        received_at=datetime.now(UTC),
    )
    repository = StubRepository(existing_event)
    intake = EventIntake(
        validator=EventValidation(),
        repository=repository,
        event_store=FailingEventStore(),
    )

    result = await intake.accept(make_incoming())

    assert isinstance(result, Duplicate)
    assert result.existing_event == existing_event


@pytest.mark.asyncio
async def test_unrelated_integrity_error_is_reraised():
    repository = StubRepository(existing_event=None)
    intake = EventIntake(
        validator=EventValidation(),
        repository=repository,
        event_store=FailingEventStore(),
    )

    with pytest.raises(IntegrityError):
        await intake.accept(make_incoming())
