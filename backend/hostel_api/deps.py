from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User
from app.services.auth import serialize_user


def get_db_session() -> Generator[Session, None, None]:
    with get_session()() as session:
        yield session


def get_current_user(request: Request, session: Session = Depends(get_db_session)) -> dict:
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    user = session.get(User, int(user_id))
    if user is None or not bool(user.is_active):
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return serialize_user(user)


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not bool(user.get("is_admin")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return user
