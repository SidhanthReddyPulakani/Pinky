from sqlalchemy import inspect

from pinky_core.persistence.models.event import EventORM
from pinky_core.persistence.models.outbox import OutboxORM


def test_event_indexes():
    indexes = inspect(EventORM).local_table.indexes

    assert {
        index.name
        for index in indexes
    } == {
        "uq_events_source_event",
        "uq_events_source_dedupe",
    }


def test_outbox_constraints():
    constraints = OutboxORM.__table__.constraints

    check_sql = {
        str(constraint.sqltext)
        for constraint in constraints
        if constraint.__class__.__name__ == "CheckConstraint"
    }

    assert "status IN ('PENDING', 'PUBLISHED')" in check_sql
    assert "attempt_count >= 0" in check_sql