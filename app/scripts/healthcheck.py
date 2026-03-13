from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_engine


def main() -> None:
    load_dotenv(Path(".env"))
    engine = get_engine()
    with Session(engine) as session:
        session.execute(text("select 1"))
    print("ok")


if __name__ == "__main__":
    main()
