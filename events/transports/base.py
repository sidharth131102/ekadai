"""EventTransport protocol — Phase 4 adds a KafkaAvroTransport implementing the same
interface; no caller (producer.py or any router) changes when that swap happens."""

from __future__ import annotations

from typing import Any, Protocol


class EventTransport(Protocol):
    def send(self, topic: str, key: str, event: dict[str, Any]) -> None: ...
