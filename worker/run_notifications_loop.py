from __future__ import annotations

import os
import time

from worker.send_notifications import process_notifications


def _poll_interval_seconds() -> int:
    raw_value = (os.getenv("NOTIFICATION_POLL_INTERVAL_SECONDS") or "").strip()
    if not raw_value:
        return 15
    try:
        parsed = int(raw_value)
    except ValueError:
        return 15
    return max(parsed, 5)


def _batch_limit() -> int:
    raw_value = (os.getenv("NOTIFICATION_BATCH_LIMIT") or "").strip()
    if not raw_value:
        return 50
    try:
        parsed = int(raw_value)
    except ValueError:
        return 50
    return max(parsed, 1)


def main() -> None:
    interval_seconds = _poll_interval_seconds()
    limit = _batch_limit()
    while True:
        processed = process_notifications(limit)
        print(f"Processed {processed} notifications.")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
