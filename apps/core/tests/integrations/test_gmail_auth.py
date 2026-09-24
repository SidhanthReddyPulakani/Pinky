from pathlib import Path
from unittest.mock import Mock

from pinky_core.integrations.gmail.auth import GmailAuthenticator


def test_existing_valid_token_is_reused(tmp_path: Path, monkeypatch) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text("{}", encoding="utf-8")

    credentials = Mock(valid=True, expired=False, refresh_token=None)

    monkeypatch.setattr(
        "pinky_core.integrations.gmail.auth.Credentials.from_authorized_user_file",
        lambda path, scopes: credentials,
    )

    flow = Mock()
    monkeypatch.setattr(
        "pinky_core.integrations.gmail.auth.InstalledAppFlow.from_client_secrets_file",
        flow,
    )

    authenticator = GmailAuthenticator(
        credentials_path=tmp_path / "credentials.json",
        token_path=token_path,
    )

    assert authenticator.load_or_authorize() is credentials
    flow.assert_not_called()


def test_expired_token_is_refreshed(tmp_path: Path, monkeypatch) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text("{}", encoding="utf-8")

    credentials = Mock(valid=False, expired=True, refresh_token="refresh-token")
    credentials.to_json.return_value = '{"refresh_token":"refresh-token"}'

    monkeypatch.setattr(
        "pinky_core.integrations.gmail.auth.Credentials.from_authorized_user_file",
        lambda path, scopes: credentials,
    )

    authenticator = GmailAuthenticator(
        credentials_path=tmp_path / "credentials.json",
        token_path=token_path,
    )

    result = authenticator.load_or_authorize()

    assert result is credentials
    credentials.refresh.assert_called_once()
    assert token_path.read_text(encoding="utf-8") == '{"refresh_token":"refresh-token"}'


def test_missing_token_starts_local_oauth_flow(tmp_path: Path, monkeypatch) -> None:
    token_path = tmp_path / "token.json"

    credentials = Mock()
    credentials.to_json.return_value = '{"access_token":"access"}'

    flow = Mock()
    flow.run_local_server.return_value = credentials

    monkeypatch.setattr(
        "pinky_core.integrations.gmail.auth.InstalledAppFlow.from_client_secrets_file",
        lambda path, scopes: flow,
    )

    authenticator = GmailAuthenticator(
        credentials_path=tmp_path / "credentials.json",
        token_path=token_path,
    )

    result = authenticator.load_or_authorize()

    assert result is credentials
    flow.run_local_server.assert_called_once_with(port=0)
    assert token_path.read_text(encoding="utf-8") == '{"access_token":"access"}'
