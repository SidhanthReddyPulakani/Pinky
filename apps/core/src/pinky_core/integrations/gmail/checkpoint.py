from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GmailCheckpoint:
    """Durable Gmail reader cursor."""

    history_id: str


class GmailCheckpointStore:
    """Persists the Gmail history cursor for one authorized account."""

    def __init__(self, *, path: Path) -> None:
        self._path = path

    def load(self) -> GmailCheckpoint | None:
        if not self._path.exists():
            return None

        history_id = self._path.read_text(encoding="utf-8").strip()

        if not history_id:
            return None

        return GmailCheckpoint(history_id=history_id)

    def save(self, checkpoint: GmailCheckpoint) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

        temporary_path = self._path.with_suffix(
            self._path.suffix + ".tmp"
        )

        temporary_path.write_text(
            checkpoint.history_id,
            encoding="utf-8",
        )

        temporary_path.replace(self._path)