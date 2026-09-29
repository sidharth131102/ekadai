from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class UserUpdateRequest(BaseModel):
    city: str | None = None
    state: str | None = None


class AddressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    address_id: uuid.UUID
    address_line1: str
    address_line2: str | None
    city: str
    state: str
    postal_code: str
    country: str
    is_default: bool


class AddressCreateRequest(BaseModel):
    address_line1: str = Field(min_length=1, max_length=255)
    address_line2: str | None = None
    city: str = Field(min_length=1, max_length=120)
    state: str = Field(min_length=1, max_length=120)
    postal_code: str = Field(min_length=1, max_length=20)
    country: str = Field(min_length=2, max_length=2)
    is_default: bool = False


class AddressUpdateRequest(BaseModel):
    address_line1: str | None = Field(default=None, min_length=1, max_length=255)
    address_line2: str | None = None
    city: str | None = Field(default=None, min_length=1, max_length=120)
    state: str | None = Field(default=None, min_length=1, max_length=120)
    postal_code: str | None = Field(default=None, min_length=1, max_length=20)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    is_default: bool | None = None
