# One-shot local Phase 1 setup: start Postgres, apply migrations, seed catalog data.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example"
}

docker compose -f db/docker-compose.yml --env-file .env up -d
if (-not $?) { throw "docker compose up failed" }

Write-Host "Waiting for Postgres to be healthy..."
$healthy = $false
for ($i = 0; $i -lt 30; $i++) {
    $status = docker inspect --format='{{.State.Health.Status}}' ekadai-postgres 2>$null
    if ($status -eq "healthy") { $healthy = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $healthy) { throw "Postgres did not become healthy in time" }

alembic -c db/alembic.ini upgrade head
if (-not $?) { throw "alembic upgrade failed" }

python db/seed/run_seed.py
if (-not $?) { throw "seed script failed" }

Write-Host "Done. Run 'pytest tests/db -v' to verify constraints."
