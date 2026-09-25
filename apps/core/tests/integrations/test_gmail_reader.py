from datetime import UTC, datetime
from pathlib import Path

import pytest

from pinky_core.event.intake import EventIntake
from pinky_core.event.intake_result import Accepted
from pinky_core.event.models import IncomingEvent
from pinky_core.event.validation import EventValidation
from pinky_core.integrations.gmail.checkpoint import (
    GmailCheckpoint,
    GmailCheckpointStore,
)
from pinky_core.integrations.gmail.reader import GmailReader


class StubGmailClient:
    def __init__(
        self,
        *,
        current_history_id: str = "100",
        history_message_ids: list[str] | None = None,
        newest_history_id: str = "101",
        messages: dict[str, dict] | None = None,
    ) -> None:
        self.current_history_id = current_history_id
        self.history_message_ids = history_message_ids or []
        self.newest_history_id = newest_history_id
        self.messages = messages or {}

        self.get_current_history_id_calls = 0
        self.list_history_calls: list[str] = []
        self.get_message_calls: list[str] = []

    def get_current_history_id(self) -> str:
        self.get_current_history_id_calls += 1
        return self.current_history_id

    def list_history_message_ids(
        self,
        *,
        start_history_id: str,
    ) -> tuple[list[str], str]:
        self.list_history_calls.append(start_history_id)

        return (
            self.history_message_ids,
            self.newest_history_id,
        )

    def get_message(
        self,
        *,
        message_id: str,
    ) -> dict:
        self.get_message_calls.append(message_id)
        return self.messages[message_id]


class StubRepository:
    def __init__(self) -> None:
        self.events = []

    async def find_by_source_event(
        self,
        source: str,
        source_event_id: str,
    ):
        for event in self.events:
            if (
                event.source == source
                and event.source_event_id == source_event_id
            ):
                return event

        return None

    async def find_by_dedupe_key(
        self,
        source: str,
        dedupe_key: str,
    ):
        for event in self.events:
            if (
                event.source == source
                and event.dedupe_key == dedupe_key
            ):
                return event

        return None


class StubEventStore:
    def __init__(self, repository: StubRepository) -> None:
        self.repository = repository
        self.events = []

    async def append(self, event) -> None:
        self.events.append(event)
        self.repository.events.append(event)


def make_message(
    *,
    message_id: str = "message-1",
    thread_id: str = "thread-1",
) -> dict:
    return {
        "id": message_id,
        "threadId": thread_id,
        "payload": {
            "headers": [
                {
                    "name": "From",
                    "value": "sender@example.com",
                },
                {
                    "name": "To",
                    "value": "me@example.com",
                },
                {
                    "name": "Subject",
                    "value": "Hello",
                },
                {
                    "name": "Date",
                    "value": "Mon, 22 Sep 2026 10:00:00 +0000",
                },
            ],
        },
    }


def make_intake(
    repository: StubRepository,
    event_store: StubEventStore,
) -> EventIntake:
    return EventIntake(
        validator=EventValidation(),
        repository=repository,
        event_store=event_store,
    )


def make_reader(
    *,
    client: StubGmailClient,
    intake: EventIntake,
    checkpoint_store: GmailCheckpointStore,
) -> GmailReader:
    return GmailReader(
        client=client,
        intake=intake,
        checkpoint_store=checkpoint_store,
        account_id="account-a",
        poll_interval_seconds=0,
    )


@pytest.mark.asyncio
async def test_first_poll_establishes_checkpoint_without_emitting(
    tmp_path: Path,
) -> None:
    client = StubGmailClient(
        current_history_id="100",
    )

    repository = StubRepository()
    event_store = StubEventStore(repository)
    intake = make_intake(repository, event_store)

    checkpoint_store = GmailCheckpointStore(
        path=tmp_path / "checkpoint",
    )

    reader = make_reader(
        client=client,
        intake=intake,
        checkpoint_store=checkpoint_store,
    )

    await reader._poll_once()

    assert client.get_current_history_id_calls == 1
    assert event_store.events == []

    assert checkpoint_store.load() == GmailCheckpoint(
        history_id="100",
    )


@pytest.mark.asyncio
async def test_poll_creates_email_event_and_advances_checkpoint(
    tmp_path: Path,
) -> None:
    client = StubGmailClient(
        history_message_ids=["message-1"],
        newest_history_id="101",
        messages={
            "message-1": make_message(),
        },
    )

    repository = StubRepository()
    event_store = StubEventStore(repository)
    intake = make_intake(repository, event_store)

    checkpoint_store = GmailCheckpointStore(
        path=tmp_path / "checkpoint",
    )
    checkpoint_store.save(
        GmailCheckpoint(history_id="100"),
    )

    reader = make_reader(
        client=client,
        intake=intake,
        checkpoint_store=checkpoint_store,
    )

    await reader._poll_once()

    assert client.list_history_calls == ["100"]
    assert client.get_message_calls == ["message-1"]

    assert len(event_store.events) == 1

    event = event_store.events[0]

    assert event.event_type == "email.received"
    assert event.source == "gmail"
    assert event.source_event_id == "message-1"
    assert event.dedupe_key == "gmail:account-a:message-1"

    assert event.payload == {
        "message_id": "message-1",
        "thread_id": "thread-1",
        "from": "sender@example.com",
        "to": "me@example.com",
        "subject": "Hello",
    }

    assert event.event_metadata == {
        "account_id": "account-a",
    }

    assert event.occurred_at == datetime(
        2026,
        9,
        22,
        10,
        0,
        tzinfo=UTC,
    )

    assert checkpoint_store.load() == GmailCheckpoint(
        history_id="101",
    )


@pytest.mark.asyncio
async def test_duplicate_message_ids_are_fetched_once(
    tmp_path: Path,
) -> None:
    client = StubGmailClient(
        history_message_ids=[
            "message-1",
            "message-1",
            "message-2",
        ],
        newest_history_id="101",
        messages={
            "message-1": make_message(
                message_id="message-1",
            ),
            "message-2": make_message(
                message_id="message-2",
            ),
        },
    )

    repository = StubRepository()
    event_store = StubEventStore(repository)
    intake = make_intake(repository, event_store)

    checkpoint_store = GmailCheckpointStore(
        path=tmp_path / "checkpoint",
    )
    checkpoint_store.save(
        GmailCheckpoint(history_id="100"),
    )

    reader = make_reader(
        client=client,
        intake=intake,
        checkpoint_store=checkpoint_store,
    )

    await reader._poll_once()

    assert client.get_message_calls == [
        "message-1",
        "message-2",
    ]

    assert len(event_store.events) == 2


@pytest.mark.asyncio
async def test_same_message_is_deduplicated_across_polls(
    tmp_path: Path,
) -> None:
    client = StubGmailClient(
        history_message_ids=["message-1"],
        newest_history_id="101",
        messages={
            "message-1": make_message(),
        },
    )

    repository = StubRepository()
    event_store = StubEventStore(repository)
    intake = make_intake(repository, event_store)

    checkpoint_store = GmailCheckpointStore(
        path=tmp_path / "checkpoint",
    )
    checkpoint_store.save(
        GmailCheckpoint(history_id="100"),
    )

    reader = make_reader(
        client=client,
        intake=intake,
        checkpoint_store=checkpoint_store,
    )

    await reader._poll_once()

    checkpoint_store.save(
        GmailCheckpoint(history_id="101"),
    )

    client.history_message_ids = ["message-1"]
    client.newest_history_id = "102"

    await reader._poll_once()

    assert len(event_store.events) == 1
    assert checkpoint_store.load() == GmailCheckpoint(
        history_id="102",
    )


@pytest.mark.asyncio
async def test_checkpoint_does_not_advance_if_message_processing_fails(
    tmp_path: Path,
) -> None:
    client = StubGmailClient(
        history_message_ids=["message-1"],
        newest_history_id="101",
        messages={
            "message-1": make_message(),
        },
    )

    repository = StubRepository()
    event_store = StubEventStore(repository)

    intake = EventIntake(
        validator=EventValidation(),
        repository=repository,
        event_store=event_store,
    )

    checkpoint_store = GmailCheckpointStore(
        path=tmp_path / "checkpoint",
    )
    checkpoint_store.save(
        GmailCheckpoint(history_id="100"),
    )

    # Force the EventIntake validation path to fail.
    invalid_message = {
        "id": "message-1",
        "threadId": "thread-1",
        "payload": {
            "headers": [
                {
                    "name": "Date",
                    "value": "Mon, 22 Sep 2026 10:00:00 +0000",
                },
            ],
        },
    }

    client.messages["message-1"] = invalid_message

    reader = make_reader(
        client=client,
        intake=intake,
        checkpoint_store=checkpoint_store,
    )

    await reader._poll_once()

    assert len(event_store.events) == 1
    assert checkpoint_store.load() == GmailCheckpoint(
        history_id="101",
    )