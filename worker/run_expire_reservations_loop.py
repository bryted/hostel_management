from __future__ import annotations

import os
import time

from worker.expire_reservations import expire_reservations


def _interval_seconds() -> int:
    raw_value = (os.getenv("RESERVATION_EXPIRY_INTERVAL_MINUTES") or "").strip()
    if not raw_value:
        return 300
    try:
        minutes = max(int(raw_value), 1)
    except ValueError:
        minutes = 5
    return minutes * 60


def main() -> None:
    interval_seconds = _interval_seconds()
    while True:
        processed = expire_reservations(limit=200)
        print(f"Expired {processed} reservations.")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
