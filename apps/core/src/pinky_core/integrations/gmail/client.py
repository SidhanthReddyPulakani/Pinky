from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build


@dataclass(frozen=True)
class GmailMessageSummary:
    """Minimal Gmail message representation needed by the integration layer."""

    message_id: str
    thread_id: str
    internal_date: int | None


class GmailClient:
    """Thin adapter around the Gmail API."""

    def __init__(
        self,
        *,
        credentials: Credentials,
    ) -> None:
        self._service: Resource = build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False,
        )

    def list_message_ids(
        self,
        *,
        query: str | None = None,
        max_results: int = 100,
    ) -> list[str]:
        """Return Gmail message IDs matching the optional query."""

        request: dict[str, Any] = {
            "userId": "me",
            "maxResults": max_results,
        }

        if query is not None:
            request["q"] = query

        response = (
            self._service.users()
            .messages()
            .list(**request)
            .execute()
        )

        messages = response.get("messages", [])

        return [
            message["id"]
            for message in messages
            if "id" in message
        ]

    def get_message(
        self,
        *,
        message_id: str,
    ) -> dict[str, Any]:
        """Return the raw Gmail message resource.

        Raw Google API structures remain inside the integration boundary.
        The EventReader will translate them into IncomingEvent.
        """

        return (
            self._service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="full",
            )
            .execute()
        )

    def get_message_summary(
        self,
        *,
        message_id: str,
    ) -> GmailMessageSummary:
        """Return the small subset needed for event identity/timing."""

        message = self.get_message(message_id=message_id)

        internal_date = message.get("internalDate")

        return GmailMessageSummary(
            message_id=message["id"],
            thread_id=message.get("threadId", ""),
            internal_date=(
                int(internal_date)
                if internal_date is not None
                else None
            ),
        )
    
    def get_current_history_id(self) -> str:
        """Return the mailbox history ID currently exposed by Gmail."""

        response = (
            self._service.users()
            .getProfile(userId="me")
            .execute()
        )

        return str(response["historyId"])

    def list_history_message_ids(
        self,
        *,
        start_history_id: str,
    ) -> tuple[list[str], str]:
        """Return newly added message IDs and the newest history ID."""

        response = (
            self._service.users()
            .history()
            .list(
                userId="me",
                startHistoryId=start_history_id,
                historyTypes=["messageAdded"],
            )
            .execute()
        )

        message_ids: list[str] = []

        for history_record in response.get("history", []):
            for message in history_record.get("messagesAdded", []):
                message_id = message.get("message", {}).get("id")

                if message_id is not None:
                    message_ids.append(message_id)

        newest_history_id = str(
            response.get("historyId", start_history_id)
        )

        return message_ids, newest_history_id