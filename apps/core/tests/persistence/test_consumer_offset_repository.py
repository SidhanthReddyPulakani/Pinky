from pathlib import Path

import pytest

from pinky_core.persistence.consumer_offset_repository import (
    ConsumerOffsetRepository,
)
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


@pytest.fixture
async def repository(session_factory):
    return ConsumerOffsetRepository(session_factory)


@pytest.mark.asyncio
async def test_get_returns_none_for_unknown_consumer(
    repository,
):
    result = await repository.get("test-consumer")

    assert result is None


@pytest.mark.asyncio
async def test_advance_creates_offset(
    repository,
):
    await repository.advance(
        consumer_id="test-consumer",
        event_seq=42,
        updated_at="2026-09-24T10:00:00+00:00",
    )

    row = await repository.get("test-consumer")

    assert row is not None
    assert row.consumer_id == "test-consumer"
    assert row.last_processed_event_seq == 42
    assert row.updated_at == "2026-09-24T10:00:00+00:00"


@pytest.mark.asyncio
async def test_advance_updates_existing_offset(
    repository,
):
    await repository.advance(
        consumer_id="test-consumer",
        event_seq=10,
        updated_at="2026-09-24T10:00:00+00:00",
    )

    await repository.advance(
        consumer_id="test-consumer",
        event_seq=11,
        updated_at="2026-09-24T10:01:00+00:00",
    )

    row = await repository.get("test-consumer")

    assert row is not None
    assert row.last_processed_event_seq == 11
    assert row.updated_at == "2026-09-24T10:01:00+00:00"


@pytest.mark.asyncio
async def test_advance_rejects_backward_offset(
    repository,
):
    await repository.advance(
        consumer_id="test-consumer",
        event_seq=10,
        updated_at="2026-09-24T10:00:00+00:00",
    )

    with pytest.raises(
        ValueError,
        match="cannot move backwards",
    ):
        await repository.advance(
            consumer_id="test-consumer",
            event_seq=9,
            updated_at="2026-09-24T10:01:00+00:00",
        )


@pytest.mark.asyncio
async def test_advance_rejects_negative_event_seq(
    repository,
):
    with pytest.raises(
        ValueError,
        match="event_seq must be >= 0",
    ):
        await repository.advance(
            consumer_id="test-consumer",
            event_seq=-1,
            updated_at="2026-09-24T10:00:00+00:00",
        )
