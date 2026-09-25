from __future__ import annotations

from pathlib import Path

from pinky_core.event.intake import EventIntake
from pinky_core.event.validation import EventValidation
from pinky_core.integrations.gmail.auth import GmailAuthenticator
from pinky_core.integrations.gmail.checkpoint import GmailCheckpointStore
from pinky_core.integrations.gmail.client import GmailClient
from pinky_core.integrations.gmail.reader import GmailReader
from pinky_core.persistence.event_repository import SQLiteEventRepository
from pinky_core.persistence.event_store import EventStore
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def build_gmail_reader(
    *,
    credentials_path: Path,
    token_path: Path,
    checkpoint_path: Path,
    account_id: str,
    session_factory: async_sessionmaker[AsyncSession],
    poll_interval_seconds: float = 30.0,
) -> GmailReader:
    """Construct a Gmail reader using the Core event pipeline."""

    credentials = GmailAuthenticator(
        credentials_path=credentials_path,
        token_path=token_path,
    ).load_or_authorize()

    client = GmailClient(
        credentials=credentials,
    )

    repository = SQLiteEventRepository(
        session_factory,
    )

    event_store = EventStore(
        session_factory,
    )

    intake = EventIntake(
        validator=EventValidation(),
        repository=repository,
        event_store=event_store,
    )

    checkpoint_store = GmailCheckpointStore(
        path=checkpoint_path,
    )

    return GmailReader(
        client=client,
        intake=intake,
        checkpoint_store=checkpoint_store,
        account_id=account_id,
        poll_interval_seconds=poll_interval_seconds,
    )