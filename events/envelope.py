"""Shared envelope pieces (MASTER_BUILD_PROMPT.md §28) reused by every event type.

`context.session_id` and `device.*` are nullable and left unset by every event emitted in
Phase 3a (server-side wiring) — they're populated once Phase 3b adds the `X-Session-Id`
header convention and request-context extraction shared by every event-emitting endpoint,
server- and client-triggered alike. `context.user_id` is populated whenever the emitting
endpoint has an authenticated user.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

PRODUCER_NAME = "ekadai-backend"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class EventContext:
    user_id: str | None = None
    session_id: str | None = None

    def to_dict(self) -> dict:
        return {"user_id": self.user_id, "session_id": self.session_id}


@dataclass(frozen=True)
class DeviceInfo:
    device_type: str | None = None
    operating_system: str | None = None
    browser: str | None = None

    def to_dict(self) -> dict:
        return {
            "device_type": self.device_type,
            "operating_system": self.operating_system,
            "browser": self.browser,
        }


def new_event_id() -> str:
    return str(uuid.uuid4())


def now_ms() -> int:
    """event_timestamp as epoch milliseconds (Avro timestamp-millis)."""
    return int(datetime.now(timezone.utc).timestamp() * 1000)
