from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ClientEventRequest(BaseModel):
    event_type: str
    event_timestamp: int = Field(description="Epoch milliseconds, captured client-side at the moment of the action")
    payload: dict[str, Any]


class ClientEventAccepted(BaseModel):
    event_id: str
    event_type: str
