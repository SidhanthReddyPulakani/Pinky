from __future__ import annotations

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class GmailAuthenticator:
    """Owns local Gmail OAuth authorization and refresh-token persistence."""

    def __init__(
        self,
        *,
        credentials_path: Path,
        token_path: Path,
        scopes: tuple[str, ...] = (GMAIL_READONLY_SCOPE,),
    ) -> None:
        self._credentials_path = credentials_path
        self._token_path = token_path
        self._scopes = scopes

    def load_or_authorize(self) -> Credentials:
        credentials = self._load_token()

        if credentials is not None and credentials.valid:
            return credentials

        if credentials is not None and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            self._save_token(credentials)
            return credentials

        flow = InstalledAppFlow.from_client_secrets_file(
            self._credentials_path,
            self._scopes,
        )
        credentials = flow.run_local_server(port=0)
        self._save_token(credentials)
        return credentials

    def _load_token(self) -> Credentials | None:
        if not self._token_path.exists():
            return None

        return Credentials.from_authorized_user_file(
            self._token_path,
            self._scopes,
        )

    def _save_token(self, credentials: Credentials) -> None:
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_path.write_text(credentials.to_json(), encoding="utf-8")
        try:
            os.chmod(self._token_path, 0o600)
        except OSError:
            pass
