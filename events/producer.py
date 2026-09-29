"""The producer library. `emit()` never raises — event emission is a side effect and must
never break the request it's attached to (called from FastAPI BackgroundTasks, after the
response is already being sent). `emit_strict()` is the opposite, for the one call site where
raising is exactly what's wanted (POST /events, translating a bad client payload into a 4xx).
`build_envelope`/`validate` are exposed separately so tests can assert real failures instead
of having them silently swallowed.
"""

from __future__ import annotations

import logging
from typing import Any

from fastavro.validation import ValidationError as AvroValidationError
from fastavro.validation import validate as avro_validate

from events.envelope import DeviceInfo, EventContext, PRODUCER_NAME, SCHEMA_VERSION, new_event_id, now_ms
from events.registry import EVENT_TYPES, resolve_key
from events.transports.base import EventTransport
from events.transports.logging_transport import LoggingTransport

logger = logging.getLogger("events")


def build_envelope(
    event_type: str,
    payload: dict[str, Any],
    context: EventContext | None = None,
    device: DeviceInfo | None = None,
    event_timestamp_ms: int | None = None,
) -> dict[str, Any]:
    return {
        "event_id": new_event_id(),
        "event_type": event_type,
        "schema_version": SCHEMA_VERSION,
        "event_timestamp": event_timestamp_ms if event_timestamp_ms is not None else now_ms(),
        "producer": PRODUCER_NAME,
        "context": (context or EventContext()).to_dict(),
        "device": (device or DeviceInfo()).to_dict(),
        "payload": payload,
    }


def validate(event_type: str, envelope: dict[str, Any]) -> None:
    """Raises ValueError (not fastavro's own exception type) on schema mismatch, so callers
    never need a fastavro import just to catch a validation failure."""
    info = EVENT_TYPES[event_type]
    try:
        avro_validate(envelope, info.schema, strict=True, raise_errors=True)
    except AvroValidationError as exc:
        raise ValueError(f"{event_type} failed schema validation: {exc}") from exc


class EventProducer:
    def __init__(self, transport: EventTransport):
        self._transport = transport

    def emit_strict(
        self,
        event_type: str,
        payload: dict[str, Any],
        context: EventContext | None = None,
        device: DeviceInfo | None = None,
        event_timestamp_ms: int | None = None,
    ) -> dict[str, Any]:
        """Builds, validates, and sends — raises ValueError/KeyError on failure instead of
        swallowing it. For the one call site (POST /events) where the caller IS the untrusted
        client submitting the event, and a malformed submission should surface as a clear 4xx
        rather than silently vanish — the opposite of every internal call site's `emit()`."""
        envelope = build_envelope(event_type, payload, context, device, event_timestamp_ms)
        validate(event_type, envelope)
        key = resolve_key(event_type, envelope)
        info = EVENT_TYPES[event_type]
        self._transport.send(info.topic, key, envelope)
        return envelope

    def emit(
        self,
        event_type: str,
        payload: dict[str, Any],
        context: EventContext | None = None,
        device: DeviceInfo | None = None,
        event_timestamp_ms: int | None = None,
    ) -> None:
        try:
            self.emit_strict(event_type, payload, context, device, event_timestamp_ms)
        except Exception:
            logger.exception("failed to emit event %s", event_type)


_producer = EventProducer(LoggingTransport())


def get_producer() -> EventProducer:
    return _producer


def set_transport(transport: EventTransport) -> None:
    """Test hook: swap the module-level producer's transport (e.g. an in-memory capturing
    transport), since routers call `get_producer()` rather than receiving it via FastAPI DI —
    BackgroundTasks callables aren't part of the dependency-override graph."""
    global _producer
    _producer = EventProducer(transport)
