"""Phase 3a default transport: appends validated events as JSON lines to a local file.
Inspectable proof the contract + wiring work before real Kafka infrastructure (Phase 4)
exists. `Decimal` fields are rendered as strings here purely for human-readable JSON — the
actual Avro validation upstream (producer.py) already used real Decimal objects.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

logger = logging.getLogger("events")


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


class LoggingTransport:
    def __init__(self, path: str | Path = "var/events.log"):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def send(self, topic: str, key: str, event: dict[str, Any]) -> None:
        line = json.dumps({"topic": topic, "key": key, "event": event}, default=_json_default)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        logger.info("emitted %s topic=%s key=%s", event.get("event_type"), topic, key)
