from sqlalchemy import inspect, text
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from pathlib import Path

import pytest

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
async def test_outbox_rejects_invalid_status(session_factory):
    async with session_factory() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    """
                    INSERT INTO outbox (
                        outbox_id,
                        event_id,
                        created_at,
                        status,
                        attempt_count
                    )
                    VALUES (
                        'invalid-status-id',
                        'missing-event',
                        '2026-01-01T00:00:00+00:00',
                        'INVALID',
                        0
                    )
                    """
                )
            )
            await session.commit()

async def test_sqlite_event_indexes_and_outbox_constraints(
    session_factory,
):
    async with session_factory() as session:
        indexes = await session.execute(
            text("PRAGMA index_list('events')")
        )
        index_names = {
            row[1]
            for row in indexes.fetchall()
        }

        assert "uq_events_source_event" in index_names
        assert "uq_events_source_dedupe" in index_names

        outbox_sql = await session.execute(
            text(
                """
                SELECT sql
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = 'outbox'
                """
            )
        )

        create_sql = outbox_sql.scalar_one()

        assert "status IN ('PENDING', 'PUBLISHED')" in create_sql
        assert "attempt_count >= 0" in create_sql