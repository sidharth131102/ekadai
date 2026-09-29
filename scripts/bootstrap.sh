#!/usr/bin/env bash
# One-shot local Phase 1 setup: start Postgres, apply migrations, seed catalog data.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

docker compose -f db/docker-compose.yml --env-file .env up -d

echo "Waiting for Postgres to be healthy..."
for _ in $(seq 1 30); do
  status=$(docker inspect --format='{{.State.Health.Status}}' ekadai-postgres 2>/dev/null || echo "starting")
  if [ "$status" = "healthy" ]; then
    break
  fi
  sleep 2
done

alembic -c db/alembic.ini upgrade head
python db/seed/run_seed.py

echo "Done. Run 'pytest tests/db -v' to verify constraints."
