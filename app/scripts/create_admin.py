import argparse
import getpass
import sys
from pathlib import Path

from dotenv import load_dotenv
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Tenant, User
from app.services.auth import validate_password_strength

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create the first admin user.")
    parser.add_argument("--email", required=True, help="Admin email address")
    parser.add_argument("--full-name", required=True, help="Admin full name")
    parser.add_argument("--password", help="Admin password (will prompt if omitted)")
    parser.add_argument(
        "--tenant-id",
        type=int,
        help="Optional tenant id to associate the admin user",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv(Path(".env"))
    args = parse_args()
    password = args.password or getpass.getpass("Password: ")
    if not password:
        print("Password is required.", file=sys.stderr)
        raise SystemExit(1)
    ok, password_error = validate_password_strength(password)
    if not ok:
        print(password_error, file=sys.stderr)
        raise SystemExit(1)

    engine = get_engine()
    with Session(engine) as session:
        if args.tenant_id is not None:
            tenant = session.get(Tenant, args.tenant_id)
            if tenant is None:
                print(f"Tenant id {args.tenant_id} not found.", file=sys.stderr)
                raise SystemExit(1)

        if args.tenant_id is None:
            existing = session.execute(
                select(User).where(User.email == args.email, User.tenant_id.is_(None))
            ).scalar_one_or_none()
        else:
            existing = session.execute(
                select(User).where(User.email == args.email, User.tenant_id == args.tenant_id)
            ).scalar_one_or_none()

        if existing:
            print("User with this email already exists.", file=sys.stderr)
            raise SystemExit(1)

        password_hash = pwd_context.hash(password)
        user = User(
            tenant_id=args.tenant_id,
            email=args.email,
            full_name=args.full_name,
            password_hash=password_hash,
            is_admin=True,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        tenant_info = f"tenant {args.tenant_id}" if args.tenant_id else "no tenant"
        print(f"Created admin user {user.id} ({args.email}) with {tenant_info}.")


if __name__ == "__main__":
    main()
