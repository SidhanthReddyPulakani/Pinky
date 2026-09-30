from unittest.mock import Mock

from google.oauth2.credentials import Credentials

from pinky_core.integrations.gmail.client import GmailClient


def make_client(service: Mock) -> GmailClient:
    client = GmailClient.__new__(GmailClient)
    client._service = service
    return client


def test_list_message_ids() -> None:
    service = Mock()

    (
        service.users.return_value
        .messages.return_value
        .list.return_value
        .execute.return_value
    ) = {
        "messages": [
            {"id": "message-1"},
            {"id": "message-2"},
        ]
    }

    client = make_client(service)

    result = client.list_message_ids(
        query="is:unread",
        max_results=10,
    )

    assert result == ["message-1", "message-2"]

    service.users.return_value.messages.return_value.list.assert_called_once_with(
        userId="me",
        maxResults=10,
        q="is:unread",
    )


def test_list_message_ids_without_query() -> None:
    service = Mock()

    (
        service.users.return_value
        .messages.return_value
        .list.return_value
        .execute.return_value
    ) = {
        "messages": [{"id": "message-1"}],
    }

    client = make_client(service)

    result = client.list_message_ids()

    assert result == ["message-1"]

    service.users.return_value.messages.return_value.list.assert_called_once_with(
        userId="me",
        maxResults=100,
    )


def test_get_message() -> None:
    service = Mock()

    message = {
        "id": "message-1",
        "threadId": "thread-1",
        "payload": {},
    }

    (
        service.users.return_value
        .messages.return_value
        .get.return_value
        .execute.return_value
    ) = message

    client = make_client(service)

    result = client.get_message(message_id="message-1")

    assert result == message

    service.users.return_value.messages.return_value.get.assert_called_once_with(
        userId="me",
        id="message-1",
        format="full",
    )


def test_get_message_summary() -> None:
    service = Mock()

    (
        service.users.return_value
        .messages.return_value
        .get.return_value
        .execute.return_value
    ) = {
        "id": "message-1",
        "threadId": "thread-1",
        "internalDate": "1750000000000",
    }

    client = make_client(service)

    result = client.get_message_summary(
        message_id="message-1",
    )

    assert result.message_id == "message-1"
    assert result.thread_id == "thread-1"
    assert result.internal_date == 1750000000000

def test_list_history_message_ids_paginates() -> None:
    service = Mock()

    list_method = (
        service.users.return_value
        .history.return_value
        .list
    )

    list_method.return_value.execute.side_effect = [
        {
            "history": [
                {
                    "messagesAdded": [
                        {"message": {"id": "message-1"}},
                    ],
                },
            ],
            "nextPageToken": "page-2",
            "historyId": "101",
        },
        {
            "history": [
                {
                    "messagesAdded": [
                        {"message": {"id": "message-2"}},
                        {"message": {"id": "message-1"}},
                    ],
                },
            ],
            "historyId": "102",
        },
    ]

    client = make_client(service)

    message_ids, history_id = client.list_history_message_ids(
        start_history_id="100",
    )

    assert message_ids == [
        "message-1",
        "message-2",
        "message-1",
    ]
    assert history_id == "102"
    assert list_method.call_count == 2

    assert list_method.call_args_list[0].kwargs == {
        "userId": "me",
        "startHistoryId": "100",
        "historyTypes": ["messageAdded"],
    }

    assert list_method.call_args_list[1].kwargs == {
        "userId": "me",
        "startHistoryId": "100",
        "historyTypes": ["messageAdded"],
        "pageToken": "page-2",
    }