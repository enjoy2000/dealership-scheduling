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

## Milestone 3 — Application layer with in-memory fakes (2026-10-08)

**Intent.** Ports, DTOs, `BookAppointmentHandler` (with retry on `ResourceConflict`) and `CancelAppointmentHandler`, all tested against in-memory fakes with no Django.

**Produced.** `application/{ports,dto,errors}.py`, `commands/{book_appointment,cancel_appointment}.py`, `domain/model/references.py`. The fakes in `tests/unit/application/fakes.py` simulate transactions (working copy, commit/rollback) and the DB's exclusion constraints. They can also inject `ResourceConflict`, optionally committing a "concurrent winner" first. The fixture world mirrors the §14.7 seed data.

**Verified.**
- Tests were written first and failed on import.
- The unit suite (domain + application) passes with the Django pytest plugin disabled. Coverage is 99% on domain + application, against targets of 90%/85%.
- Mutation checks, each change applied and then reverted:
  - Removing the ownership check: 1 test failed.
  - Disabling the retry: 3 tests failed.
  - Publishing events before commit: 2 tests failed.
- Publishing right after `commit()` but still inside the `with` block was *not* caught. On review that is still after commit, so this is correct behaviour, not a test gap.
- `ruff`, `mypy --strict` and `lint-imports` are clean.

**Corrected.**
- mypy rejected the fakes against the `UnitOfWork` port because the Protocol declared `appointments`/`resources` as mutable attributes (invariant). They became read-only properties, which is also the correct contract: callers must not swap repositories.
- Ruff flagged `NotFound` (N818). Unlike the domain errors, this name isn't fixed by the spec, so it was renamed to `NotFoundError` instead of widening the ignore.
- Removed `type: ignore` comments and in-function imports from the first test draft.

### Milestone 3 follow-up — RESTful cancel (2026-10-08)

**Intent (user).** "API design should follow RESTful, DELETE returns empty no-content 204."

**Produced.** `CancelAppointmentHandler` now returns `None` and `CancellationResult` is removed. SPEC.md is updated to v1.1 (§6 responses, §7 rule 12), adding a `Location` header on `201`. Recorded as I18.

**Verified.** The cancel tests were rewritten first to assert persisted state instead of a returned DTO. The idempotency test now also checks that the repeated cancel doesn't commit. Full gate is green: 111 tests.

**Corrected.** Milestone 3 had followed SPEC v1.0, which returned `200` on a repeated cancel. The user overrode this as non-RESTful.

## Milestone 4 — Infrastructure (2026-10-08)

**Intent.** ORM models and migrations (`BtreeGistExtension` + 3 exclusion constraints), mappers, repositories, `DjangoUnitOfWork`, `23P01` translation, `CatalogGateway` adapter, Catalog app and seed command.

**Produced.**
- Catalog app: models, admin, `seed_catalog`, `seed_demo`.
- Scheduling persistence app: `models.py`, migration `0001` starting with `BtreeGistExtension()`, `ranges.py`, `mappers.py`, `error_translation.py`, `repositories.py`, `unit_of_work.py`, read-only appointment admin, `seed_resources`.
- `infrastructure/catalog_gateway.py`.

**Verified.**
- 39 integration tests on PostgreSQL 16 (compose):
  - extension and constraint presence, `makemigrations --check`
  - raw-ORM overlap inserts rejected for bay/technician/vehicle, while back-to-back and cancelled rows are allowed
  - `23P01` → `ResourceConflict`, while a duplicate primary key is *not* translated, and the connection stays usable after a conflict
  - repository round-trips, availability, and technician load counting (cancelled and other-day appointments excluded)
  - UoW commit/rollback/exception/reuse, gateway mapping, seed idempotency and sequence reset
  - book → conflict → cancel → rebook through the real handlers
- Full suite: 150 passed, 98% coverage. `ruff`, `mypy --strict`, and `lint-imports` (5 kept; the gateway exception is now matched, and the I2 relaxation is removed) are all clean.
- In compose: `make migrate` and `make seed` (run twice) succeed, and `pg_constraint` lists the three exclusion constraints.

**Corrected.**
- Django admin generics (`ModelAdmin[Model]`) crashed at runtime without `django_stubs_ext.monkeypatch()`. Fixed by adding the dependency (I25).
- Ruff RUF012 flagged list-valued `Meta.constraints`/`inlines`. The AI's first automated fix, a regex rewrite to tuples, dropped the trailing comma on single-element lists, so `constraints = (X)` became a bare object. Ruff stayed green; the **mypy Django plugin crashed** on it (`'CheckConstraint' object is not iterable`). The five spots were fixed by hand, and `makemigrations --check` confirmed no schema drift. Lesson: blind mechanical rewrites need a semantic check, and the typed toolchain provided one.
- The first seeding design had a shared helper module in Catalog that Scheduling would have imported. It was replaced by per-context commands composed via `call_command` (I20).

## Milestone 5 — Interface (2026-10-08)

**Intent.** DRF views/serializers, problem-details mapping, composition root, OpenAPI via drf-spectacular. RESTful: `201` + `Location`, `204` on cancel.

**Produced.**
- `container.py` (composition root).
- `interface/api/{views,serializers,problem_details,throttles,urls,dependencies}.py`.
- Infrastructure `clock.py`, `event_publisher.py` (after-commit dispatch), and a correlation-id middleware.
- Swagger UI at `/api/v1/docs/` and the schema at `/api/v1/schema/`, exported to `docs/openapi.yaml` (`make schema`, validated).

**Verified.**
- 38 API tests through the DRF client on Postgres cover:
  - every booking/cancel criterion of §7 (rules 2, 3, 4, 6, 7, 9, 10, 11, 12)
  - problem+json shape and correlation-id echo
  - a `500` that does not leak internals
  - per-customer throttling with `Retry-After`
- An OpenAPI contract test validates `201`/`400`/`404`/`422` bodies against the generated component schemas, and checks that `Idempotency-Key` (required header), `Location` and `204` are documented.
- Live check against `docker compose`: curl gives `201` + `Location`, then `409 no_capacity` for the overlapping request.
- Full suite: 188 passed. `ruff`, `mypy --strict`, `lint-imports` (5 kept) are clean.

**Corrected.**
- **Layer violation caught by import-linter:** the first views imported `container.py`, which the M1 contract forbids (container sits above interface). Editing `.importlinter` would have been the quick fix, and is exactly what CLAUDE.md forbids. Dependency inversion was used instead (I27).
- **Shadowed DRF API:** a serializer field named `errors` silently shadowed `Serializer.errors`. mypy caught it, and it is now declared in `get_fields()`.
- `OpenApiResponse(response_headers=...)` does not exist in drf-spectacular. The test run caught it, and response headers are now declared as `OpenApiParameter(..., response=[201])`.
- `default_error_messages` override failed type-checking. Replaced with an explicit `ValidationError`.
- Renamed `IdempotencyConflict` to `IdempotencyConflictError` for consistency with `NotFoundError`.

## Milestone 6 — Queries and remaining endpoints (2026-10-08)

**Intent.** Availability read model + cache (A14), `GET /appointments/{id}/`, `GET /availability/`. Cancel was already done in M5.

**Produced.**
- Domain `services/availability.py`.
- Application: `queries/{get_appointment,list_availability}.py`, `event_handlers.py`, read-model and cache ports.
- Infrastructure: `persistence/read_models.py` and `cache.py` (versioned keys).
- Views, serializers and the route for availability.

**Verified.**
- Tests first at each layer:
  - 8 domain tests for the calculator (grid, past starts, back-to-back, off-grid opening, qualified-only).
  - 9 application tests with fakes (caching, targeted invalidation, 404 not cached).
  - 6 infrastructure tests (projection, fixed 3-query day schedule, cache invalidation scope, TTL 0).
  - 14 API tests. The key one is a **brute-force check of §7 rule 13**: for every grid start of the day, "offered by availability" equals "a real booking succeeds". Others: cache hit = 0 queries, stale-but-revalidated booking (A14), and real-commit invalidation on book and cancel.
- Live in compose (Redis): 31 slots → book → 25 → cancel → 31.
- 227 tests passing. `ruff`, `mypy --strict` and `lint-imports` (5 kept) are clean.

**Corrected.**
- The invalidation API test failed at first. pytest-django wraps tests in a transaction, so `transaction.on_commit` (the after-commit dispatch from I32) never fired. This was not a production bug: requests run in autocommit, so the unit of work's atomic block is outermost and commits. The test now runs with `transaction=True`, so it proves the real commit path instead of faking it.
- `assert` used for a runtime invariant in the query handler (assertions vanish under `-O`) was replaced with an explicit `LookupError`.
