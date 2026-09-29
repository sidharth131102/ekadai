"""App-level settings. Reads the same .env as db/config.py, adding API-specific values."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://ekadai:ekadai@localhost:5432/ekadai"
    test_database_url: str = "postgresql+psycopg://ekadai:ekadai@localhost:5432/ekadai_test"

    jwt_secret_key: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    cors_origins: str = "http://localhost:5173"

    # No table anywhere upstream supplies a currency (no per-user/per-product currency
    # column) — a single app-level constant, applied uniformly to orders.currency and
    # order_items.currency. INR: the seeded catalog prices are ordinary INR retail price
    # points (₹599, ₹17999 for a monitor, etc.), consistent with the master spec's own
    # cost framing (§6, "₹0 mandatory recurring cost") — they were always INR, just
    # mislabeled/rendered as USD (Phase 2c fix).
    default_currency: str = "INR"

    # Phase 4 — Kafka + Schema Registry. "logging" (default) keeps the Phase 3a
    # LoggingTransport, so a fresh clone / the test suite never require a running Kafka
    # broker. Set to "kafka" (in .env) to produce real Avro-encoded events instead.
    event_transport: str = "logging"
    kafka_bootstrap_servers: str = "localhost:29092"
    schema_registry_url: str = "http://localhost:8081"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
