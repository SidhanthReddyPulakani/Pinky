from datetime import UTC, datetime

import pytest

from pinky_core.event.intake import EventIntake
from pinky_core.event.intake_result import Accepted
from pinky_core.event.models import IncomingEvent
from pinky_core.event.readers.synthetic import SyntheticEventReader
from pinky_core.event.validation import EventValidation


class StubRepository:
    def __init__(self):
        self.events = []

    async def find_by_source_event(self, source, source_event_id):
        return None

    async def find_by_dedupe_key(self, source, dedupe_key):
        return None


class StubEventStore:
    def __init__(self):
        self.appended = []

    async def append(self, event):
        self.appended.append(event)

def make_event() -> IncomingEvent:
    return IncomingEvent(
        event_type="TEST_EVENT",
        source="synthetic",
        source_event_id="test-001",
        dedupe_key="synthetic:test-001",
        occurred_at=datetime.now(UTC),
        payload={"message": "hello"},
    )

@pytest.mark.asyncio
async def test_reader_emits_event_through_intake():
    repository = StubRepository()
    event_store = StubEventStore()

    intake = EventIntake(
        validator=EventValidation(),
        repository=repository,
        event_store=event_store,
    )

    reader = SyntheticEventReader(
        emit=intake.accept,
    )

    await reader.run()

    incoming = IncomingEvent(
        event_type="FILE_CHANGED",
        source="synthetic",
        source_event_id="test-001",
        dedupe_key="synthetic:test-001",
        occurred_at=datetime.now(UTC),
        payload={"message": "hello"},
    )

    result = await reader.emit(incoming)

    assert isinstance(result, Accepted)
    assert len(event_store.appended) == 1
    assert event_store.appended[0] == result.event

    await reader.stop()

@pytest.mark.asyncio
async def test_reader_rejects_emit_before_run():
    async def emit(event):
        return None

    reader = SyntheticEventReader(emit=emit)

    with pytest.raises(RuntimeError, match="Reader is not running"):
        await reader.emit(make_event())

@pytest.mark.asyncio
async def test_reader_rejects_emit_before_run():
    async def emit(event):
        return None

    reader = SyntheticEventReader(emit=emit)

    with pytest.raises(RuntimeError, match="Reader is not running"):
        await reader.emit(make_event())