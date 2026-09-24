from __future__ import annotations

import argparse
from pathlib import Path

from .auth import GmailAuthenticator


def main() -> None:
    parser = argparse.ArgumentParser(description="Authorize Pinky for Gmail.")
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--token", type=Path, required=True)
    args = parser.parse_args()

    GmailAuthenticator(
        credentials_path=args.credentials,
        token_path=args.token,
    ).load_or_authorize()

    print(f"Gmail authorization succeeded; token saved to {args.token}")


if __name__ == "__main__":
    main()
