from __future__ import annotations

import asyncio
from pathlib import Path

from pinky_core.integrations.gmail.runtime import build_gmail_reader
from pinky_core.persistence.database import (
    create_engine,
    create_session_factory,
)
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

async def main() -> None:
    project_root = Path(__file__).resolve().parents[1]

    database_path = project_root / "pinky.db"
    credentials_path = project_root.parent.parent / "credentials.json"
    token_path = project_root / ".pinky" / "gmail" / "token.json"
    checkpoint_path = (
        project_root / ".pinky" / "gmail" / "checkpoint"
    )

    engine = create_engine(database_path)
    session_factory = create_session_factory(engine)

    reader = build_gmail_reader(
        credentials_path=credentials_path,
        token_path=token_path,
        checkpoint_path=checkpoint_path,
        account_id="account-a",
        session_factory=session_factory,
        poll_interval_seconds=30.0,
    )

    try:
        await reader.run()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())