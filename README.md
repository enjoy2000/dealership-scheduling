# Unified Service Scheduler

Books a service bay and a qualified technician for a dealership appointment. Django 5 + DRF + PostgreSQL 16, DDD layering. See `SPEC.md`.

## Quick start

Requires Docker (with Compose) and [uv](https://docs.astral.sh/uv/). All backing services run in docker compose.

```bash
cp .env.example .env
make up        # build and start web, db, redis, otel-collector, prometheus
make migrate
curl localhost:8000/healthz
```

## Development

```bash
uv sync
make test      # starts db + redis via compose, then runs pytest on the host
make lint      # ruff + mypy
make arch      # import-linter layer contracts
```
