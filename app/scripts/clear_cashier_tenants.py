from __future__ import annotations

import argparse
import sys

from sqlalchemy import update, select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import User


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clear tenant associations for cashier (non-admin) users."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply updates (omit for dry run).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    engine = get_engine()
    with Session(engine) as session:
        affected = session.execute(
            select(User).where(User.is_admin.is_(False), User.tenant_id.is_not(None))
        ).scalars().all()
        count = len(affected)
        if count == 0:
            print("No cashier users are linked to tenants.")
            return

        if not args.apply:
            print(f"{count} cashier user(s) have tenant links. Re-run with --apply to clear.")
            return

        session.execute(
            update(User)
            .where(User.is_admin.is_(False), User.tenant_id.is_not(None))
            .values(tenant_id=None)
        )
        session.commit()
        print(f"Cleared tenant links for {count} cashier user(s).")


if __name__ == "__main__":
    sys.exit(main())
