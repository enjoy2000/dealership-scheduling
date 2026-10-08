# AI Collaboration Log

Per milestone: intent → what the AI produced → how it was verified → what was corrected (SPEC.md §13).

## Milestone 1 — Scaffold (2026-10-08)

**Intent.** Django project skeleton, settings split, Docker/compose stack, `/healthz` + `/readyz`, ruff/mypy/pytest, `.importlinter` contracts, CI.

**Produced.** `Dockerfile`, `docker-compose.yml` (db, redis, web, otel-collector, prometheus), `ops/` collector and Prometheus configs, `.env.example`, `Makefile`, `.importlinter` (5 contracts), `.github/workflows/ci.yml`, health endpoints and tests, architecture test that runs `lint-imports`.

**Verified.** `ruff check`, `mypy`, `lint-imports`, `pytest` against PostgreSQL 16 in compose. Contracts were probed by temporarily adding `import django` to the domain and an infrastructure import to the interface: both contracts reported BROKEN, then the probes were removed.

**Corrected.** The AI found a host-installed PostgreSQL and started wiring tests to it. The user rejected this: dependencies must be managed only with docker compose. The host PostgreSQL was purged, Docker Engine installed, and tests now target the compose `db` service (decision I1).
