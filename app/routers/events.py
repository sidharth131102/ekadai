from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.deps import get_device_info, get_optional_current_user, get_session_id
from app.errors import NotFoundError, UnprocessableError
from app.schemas.events import ClientEventAccepted, ClientEventRequest
from events.envelope import DeviceInfo, EventContext
from events.producer import get_producer
from events.registry import CLIENT_EMITTABLE_EVENT_TYPES, EVENT_TYPES
from db.models import User

router = APIRouter(prefix="/events", tags=["events"])


@router.post("", response_model=ClientEventAccepted, status_code=status.HTTP_202_ACCEPTED)
def ingest_client_event(
    payload: ClientEventRequest,
    current_user: User | None = Depends(get_optional_current_user),
    session_id: str | None = Depends(get_session_id),
    device_info: DeviceInfo = Depends(get_device_info),
) -> ClientEventAccepted:
    """Anonymous users may call this (browsing before login still emits events) — the
    frontend never needs its own Avro/session logic, it just sends event_type +
    event_timestamp + payload and everything else (event_id, context, device) is filled in
    here. Only the client-originated event types are accepted (§30-§32/§35); the 10
    server-emitted types can never be forged through this endpoint.
    """
    if payload.event_type not in EVENT_TYPES:
        raise NotFoundError(f"Unknown event_type: {payload.event_type}")
    if payload.event_type not in CLIENT_EMITTABLE_EVENT_TYPES:
        raise UnprocessableError(f"{payload.event_type} is not a client-emittable event type")

    context = EventContext(
        user_id=str(current_user.user_id) if current_user else None,
        session_id=session_id,
    )

    try:
        envelope = get_producer().emit_strict(
            payload.event_type,
            payload.payload,
            context=context,
            device=device_info,
            event_timestamp_ms=payload.event_timestamp,
        )
    except (ValueError, KeyError) as exc:
        raise UnprocessableError(str(exc)) from exc

    return ClientEventAccepted(event_id=envelope["event_id"], event_type=payload.event_type)
