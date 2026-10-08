# AI Collaboration Log

Per milestone: intent → what the AI produced → how it was verified → what was corrected (SPEC.md §13).

## Milestone 1 — Scaffold (2026-10-08)

**Intent.** Django project skeleton, settings split, Docker/compose stack, `/healthz` + `/readyz`, ruff/mypy/pytest, `.importlinter` contracts, CI.

**Produced.** `Dockerfile`, `docker-compose.yml` (db, redis, web, otel-collector, prometheus), `ops/` collector and Prometheus configs, `.env.example`, `Makefile`, `.importlinter` (5 contracts), `.github/workflows/ci.yml`, health endpoints and tests, architecture test that runs `lint-imports`.

**Verified.** `ruff check`, `mypy`, `lint-imports`, `pytest` against PostgreSQL 16 in compose. Contracts were probed by temporarily adding `import django` to the domain and an infrastructure import to the interface: both contracts reported BROKEN, then the probes were removed.

**Corrected.** The AI found a host-installed PostgreSQL and started wiring tests to it. The user rejected this: dependencies must be managed only with docker compose. The host PostgreSQL was purged, Docker Engine installed, and tests now target the compose `db` service (decision I1).

## Milestone 2 — Domain layer (2026-10-08)

**Intent.** Pure-Python Scheduling domain, tests first: value objects, `TimeSlot`, policies, `Appointment` aggregate with events, `ResourceAllocator`, errors, repository ports.

**Produced.** `domain/model/{value_objects,resources,appointment}.py`, `domain/services/resource_allocator.py`, `domain/policies/{slot_alignment,opening_hours}.py`, `domain/{events,errors,repositories}.py`, `shared_kernel/{events,clock}.py`. 78 tests in `tests/unit/domain` cover half-open overlap (back-to-back vs 1-minute overlap), 15-minute grid and past starts, opening hours in London/New York across both 2026 DST transitions, A9 tie-breaking, and aggregate events and state transitions.

**Verified.** The tests were written first and failed on import before any domain code existed. The domain suite passes with the Django pytest plugin disabled (`-p no:django`), proving it needs neither Django nor a DB. Domain coverage is 95% (the only uncovered lines are Protocol port bodies). `ruff`, `mypy --strict` and `lint-imports` (5 kept) are clean.

**Corrected.**
- Ruff `N818` wanted every exception renamed `...Error`, which would break the spec's ubiquitous language. Rather than rename, the rule is ignored for `domain/errors.py` only (I10).
- The first draft of the tests imported a helper from `conftest.py`. It was moved to `time_helpers.py`, since importing from conftest is fragile.
- An untyped test helper failed `mypy --strict` and was annotated.
- `CancellationNotAllowed` is missing from the spec's domain-error list. It was added deliberately (I5) rather than putting the rule in a view.
