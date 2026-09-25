from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from venv import logger

from pinky_core.event.intake import EventIntake
from pinky_core.event.intake_result import Accepted, Rejected
from pinky_core.event.models import IncomingEvent

from .checkpoint import GmailCheckpoint, GmailCheckpointStore
from .client import GmailClient


class GmailReader:
    """Polls Gmail and translates newly received messages into Events."""

    def __init__(
        self,
        *,
        client: GmailClient,
        intake: EventIntake,
        checkpoint_store: GmailCheckpointStore,
        account_id: str,
        poll_interval_seconds: float = 30.0,
    ) -> None:
        self._client = client
        self._intake = intake
        self._checkpoint_store = checkpoint_store
        self._account_id = account_id
        self._poll_interval_seconds = poll_interval_seconds

        self._running = False
        self._stop_event = asyncio.Event()

        self._logger = logging.getLogger(__name__)

    async def run(self) -> None:
        if self._running:
            raise RuntimeError("Reader is already running")

        self._running = True
        self._stop_event.clear()

        try:
            self._logger.info(
                "Gmail reader started for account=%s",
                self._account_id,
            )
            await self._poll_once()

            while not self._stop_event.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self._poll_interval_seconds,
                    )
                except asyncio.TimeoutError:
                    await self._poll_once()
        finally:
            self._running = False

    async def stop(self) -> None:
        self._stop_event.set()

        self._logger.info(
            "Gmail reader stop requested for account=%s",
            self._account_id,
        )

    async def _poll_once(self) -> None:
        checkpoint = self._checkpoint_store.load()

        if checkpoint is None:
            history_id = self._client.get_current_history_id()
            self._logger.info(
                "Gmail reader established initial checkpoint "
                "account=%s history_id=%s",
                self._account_id,
                history_id,
            )

            self._checkpoint_store.save(
                GmailCheckpoint(history_id=history_id)
            )
            return

        message_ids, newest_history_id = (
            self._client.list_history_message_ids(
                start_history_id=checkpoint.history_id,
            )
        )

        unique_message_ids = list(dict.fromkeys(message_ids))

        self._logger.info(
            "Gmail reader poll account=%s checkpoint=%s messages=%d",
            self._account_id,
            checkpoint.history_id,
            len(unique_message_ids),
        )

        for message_id in unique_message_ids:
            message = self._client.get_message(
                message_id=message_id,
            )

            event = self._to_event(message)
            result = await self._intake.accept(event)

            if isinstance(result, Rejected):
                self._logger.warning(
                    "Gmail event rejected account=%s message_id=%s "
                    "reason=%s; checkpoint not advanced",
                    self._account_id,
                    message_id,
                    result.reason,
                )
                return

            if isinstance(result, Accepted):
                self._logger.info(
                    "Gmail event accepted account=%s message_id=%s "
                    "event_id=%s",
                    self._account_id,
                    message_id,
                    result.event.event_id,
                )
            else:
                self._logger.info(
                    "Gmail event duplicate account=%s message_id=%s "
                    "event_id=%s",
                    self._account_id,
                    message_id,
                    result.existing_event.event_id,
                )

        self._checkpoint_store.save(
            GmailCheckpoint(
                history_id=newest_history_id,
            )
        )

        self._logger.info(
            "Gmail reader advanced checkpoint account=%s history_id=%s",
            self._account_id,
            newest_history_id,
        )

    def _to_event(
        self,
        message: dict[str, Any],
    ) -> IncomingEvent:
        message_id = str(message["id"])
        thread_id = str(message.get("threadId", ""))

        headers = self._headers(message)

        occurred_at = self._message_timestamp(headers)

        payload = {
            "message_id": message_id,
            "thread_id": thread_id,
            "from": headers.get("From"),
            "to": headers.get("To"),
            "subject": headers.get("Subject"),
        }

        return IncomingEvent(
            event_type="email.received",
            source="gmail",
            source_event_id=message_id,
            dedupe_key=f"gmail:{self._account_id}:{message_id}",
            occurred_at=occurred_at,
            payload=payload,
            event_metadata={
                "account_id": self._account_id,
            },
        )

    @staticmethod
    def _headers(
        message: dict[str, Any],
    ) -> dict[str, str]:
        payload = message.get("payload", {})

        result: dict[str, str] = {}

        for header in payload.get("headers", []):
            name = header.get("name")
            value = header.get("value")

            if name is not None and value is not None:
                result[name] = value

        return result

    @staticmethod
    def _message_timestamp(
        headers: dict[str, str],
    ) -> datetime:
        date_header = headers.get("Date")

        if date_header is None:
            return datetime.now(timezone.utc)

        parsed = parsedate_to_datetime(date_header)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)