"""Shared FastAPI dependencies: DB session, current-user resolution, and the request-context
pieces (session id, device info) that event-emission call sites attach to every event."""

from __future__ import annotations

from typing import Iterator

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.security import InvalidTokenError, decode_access_token
from app.user_agent import parse_device_info
from db.models import User
from events.envelope import DeviceInfo

bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        user_id = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    user = db.get(User, user_id)
    if user is None or user.account_status != "ACTIVE":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return user


def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """Like get_current_user, but returns None instead of 401 — for endpoints anonymous
    users must be able to call too (the /events ingestion endpoint)."""
    if credentials is None:
        return None
    try:
        user_id = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        return None
    user = db.get(User, user_id)
    if user is None or user.account_status != "ACTIVE":
        return None
    return user


def get_session_id(x_session_id: str | None = Header(default=None, alias="X-Session-Id")) -> str | None:
    return x_session_id


def get_device_info(request: Request) -> DeviceInfo:
    return parse_device_info(request.headers.get("user-agent"))
