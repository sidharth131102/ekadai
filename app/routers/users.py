from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.errors import NotFoundError
from app.schemas.auth import UserOut
from app.schemas.users import AddressCreateRequest, AddressOut, AddressUpdateRequest, UserUpdateRequest
from db.models import Address, User

router = APIRouter(prefix="/users/me", tags=["users"])


@router.get("", response_model=UserOut)
def get_profile(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)


@router.patch("", response_model=UserOut)
def update_profile(
    payload: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    if payload.city is not None:
        current_user.city = payload.city
    if payload.state is not None:
        current_user.state = payload.state
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return UserOut.model_validate(current_user)


def _unset_existing_default(db: Session, user_id: uuid.UUID) -> None:
    db.execute(
        update(Address)
        .where(Address.user_id == user_id, Address.is_default.is_(True))
        .values(is_default=False)
    )


@router.get("/addresses", response_model=list[AddressOut])
def list_addresses(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[AddressOut]:
    addresses = db.execute(
        select(Address).where(Address.user_id == current_user.user_id).order_by(Address.created_at)
    ).scalars().all()
    return [AddressOut.model_validate(a) for a in addresses]


@router.post("/addresses", response_model=AddressOut, status_code=status.HTTP_201_CREATED)
def create_address(
    payload: AddressCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AddressOut:
    if payload.is_default:
        _unset_existing_default(db, current_user.user_id)
    address = Address(user_id=current_user.user_id, **payload.model_dump())
    db.add(address)
    db.commit()
    db.refresh(address)
    return AddressOut.model_validate(address)


@router.patch("/addresses/{address_id}", response_model=AddressOut)
def update_address(
    address_id: uuid.UUID,
    payload: AddressUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AddressOut:
    address = db.execute(
        select(Address).where(Address.address_id == address_id, Address.user_id == current_user.user_id)
    ).scalar_one_or_none()
    if address is None:
        raise NotFoundError("Address not found")

    updates = payload.model_dump(exclude_unset=True)
    if updates.get("is_default") is True:
        _unset_existing_default(db, current_user.user_id)
    for field, value in updates.items():
        setattr(address, field, value)

    db.add(address)
    db.commit()
    db.refresh(address)
    return AddressOut.model_validate(address)


@router.delete("/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_address(
    address_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    address = db.execute(
        select(Address).where(Address.address_id == address_id, Address.user_id == current_user.user_id)
    ).scalar_one_or_none()
    if address is None:
        raise NotFoundError("Address not found")
    db.delete(address)
    db.commit()
    return None
