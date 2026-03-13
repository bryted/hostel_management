import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


load_dotenv(Path(".env"))


def get_database_url() -> str:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set. Create a .env file or set the env var.")
    return db_url


def get_engine():
    return create_engine(
        get_database_url(),
        future=True,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
    )


def get_session():
    engine = get_engine()
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
