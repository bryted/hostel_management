"""Expire stale bed reservations."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

from dotenv import load_dotenv
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from app.db import get_engine
from app.services.reservations import expire_reservations_batch

load_dotenv()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Expire stale bed reservations.")
    parser.add_argument("--limit", type=int, default=200, help="Max reservations to process")
    return parser.parse_args()


def expire_reservations(limit: int) -> int:
    engine = get_engine()
    now = datetime.now(timezone.utc)

    with Session(engine) as session:
        processed = expire_reservations_batch(session, now=now, limit=limit)
        session.commit()
    return processed


def main() -> None:
    args = parse_args()
    processed = expire_reservations(args.limit)
    print(f"Expired {processed} reservations.")


if __name__ == "__main__":
    main()
