from __future__ import annotations

from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, get_device_info, get_session_id
from app.errors import ConflictError, UnauthorizedError
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.security import create_access_token, hash_password, verify_password
from db.models import User, Wishlist
from events.envelope import DeviceInfo, EventContext
from events.producer import get_producer

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    session_id: str | None = Depends(get_session_id),
    device_info: DeviceInfo = Depends(get_device_info),
) -> TokenResponse:
    existing = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("Email already registered")

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        registration_date=date.today(),
        account_status="ACTIVE",
        city=payload.city,
        state=payload.state,
    )
    db.add(user)
    db.flush()  # obtain user.user_id for the wishlist FK

    # Wishlist is created eagerly at registration (simple 1:1 invariant) — cart is
    # created lazily on first add-to-cart instead (see Phase 2a plan).
    db.add(Wishlist(user_id=user.user_id))
    db.commit()
    db.refresh(user)

    token = create_access_token(user.user_id)

    background_tasks.add_task(
        get_producer().emit,
        "user_registered",
        {"registration": {"registration_method": "email"}},
        context=EventContext(user_id=str(user.user_id), session_id=session_id),
        device=device_info,
    )
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    session_id: str | None = Depends(get_session_id),
    device_info: DeviceInfo = Depends(get_device_info),
) -> TokenResponse:
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise UnauthorizedError("Invalid email or password")
    if user.account_status != "ACTIVE":
        raise UnauthorizedError("Account is not active")

    token = create_access_token(user.user_id)

    background_tasks.add_task(
        get_producer().emit,
        "user_login",
        {"authentication": {"login_method": "email"}},
        context=EventContext(user_id=str(user.user_id), session_id=session_id),
        device=device_info,
    )
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session_id: str | None = Depends(get_session_id),
    device_info: DeviceInfo = Depends(get_device_info),
) -> None:
    # Stateless JWT: nothing to invalidate server-side without a denylist store, which
    # doesn't exist in v1 — the client is responsible for discarding its token. Requiring
    # auth here (added in Phase 3a) both matches "you can only log out a session you're
    # authenticated for" and gives the user_logout event a real user_id.
    background_tasks.add_task(
        get_producer().emit,
        "user_logout",
        {},
        context=EventContext(user_id=str(current_user.user_id), session_id=session_id),
        device=device_info,
    )
    return None
