from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pinky_core.event.models import Event
from pinky_core.event.outbox_publisher import OutboxPublisher
from pinky_core.persistence.event_repository import SQLiteEventRepository
from pinky_core.persistence.event_store import EventStore
from pinky_core.persistence.models import Base
from pinky_core.persistence.outbox_repository import OutboxRepository


@pytest.fixture
async def repositories():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    outbox_repository = OutboxRepository(session_factory)
    event_repository = SQLiteEventRepository(session_factory)
    event_store = EventStore(session_factory)

    try:
        yield outbox_repository, event_repository, event_store
    finally:
        await engine.dispose()


def make_event() -> Event:
    now = datetime.now(UTC)

    return Event(
        event_id=uuid4(),
        event_type="test.event",
        source="test",
        occurred_at=now,
        received_at=now,
        payload={"value": 1},
        event_metadata={},
        schema_version=1,
    )


@pytest.mark.asyncio
async def test_publish_pending_marks_successful_delivery_published(
    repositories,
):
    outbox_repository, event_repository, event_store = repositories

    event = make_event()
    await event_store.append(event)

    delivered: list[Event] = []

    async def deliver(delivered_event: Event) -> None:
        delivered.append(delivered_event)

    publisher = OutboxPublisher(
        outbox_repository=outbox_repository,
        event_repository=event_repository,
        delivery_target=deliver,
    )

    await publisher.publish_pending()

    assert delivered == [event]
    assert await outbox_repository.get_pending() == []


@pytest.mark.asyncio
async def test_publish_pending_keeps_failed_delivery_pending(
    repositories,
):
    outbox_repository, event_repository, event_store = repositories

    event = make_event()
    await event_store.append(event)

    rows = await outbox_repository.get_pending()
    assert len(rows) == 1

    async def deliver(_event: Event) -> None:
        raise RuntimeError("delivery failed")

    publisher = OutboxPublisher(
        outbox_repository=outbox_repository,
        event_repository=event_repository,
        delivery_target=deliver,
    )

    await publisher.publish_pending()

    pending = await outbox_repository.get_pending()

    assert len(pending) == 1
    assert pending[0].outbox_id == rows[0].outbox_id
    assert pending[0].status == "PENDING"
    assert pending[0].attempt_count == 1
    assert pending[0].last_attempt_at is not None
    assert pending[0].next_attempt_at is None
    assert pending[0].last_error == "delivery failed"


@pytest.mark.asyncio
async def test_pending_outbox_is_republished_by_new_publisher(
    repositories,
):
    outbox_repository, event_repository, event_store = repositories

    event = make_event()
    await event_store.append(event)

    first_delivery_attempts = 0

    async def failing_delivery(_event: Event) -> None:
        nonlocal first_delivery_attempts
        first_delivery_attempts += 1
        raise RuntimeError("temporary failure")

    first_publisher = OutboxPublisher(
        outbox_repository=outbox_repository,
        event_repository=event_repository,
        delivery_target=failing_delivery,
    )

    await first_publisher.publish_pending()

    pending = await outbox_repository.get_pending()

    assert len(pending) == 1
    assert pending[0].attempt_count == 1
    assert first_delivery_attempts == 1

    delivered: list[Event] = []

    async def successful_delivery(delivered_event: Event) -> None:
        delivered.append(delivered_event)

    second_publisher = OutboxPublisher(
        outbox_repository=outbox_repository,
        event_repository=event_repository,
        delivery_target=successful_delivery,
    )

    await second_publisher.publish_pending()

    assert delivered == [event]
    assert await outbox_repository.get_pending() == []
