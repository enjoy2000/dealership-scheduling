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

## Milestone 7 — Idempotency (2026-10-08)

**Intent.** `Idempotency-Key` storage and replay (§14.5): same key and payload → original `201`; different payload → `409`; written in the booking's transaction; failures not stored; 24 h expiry.

**Produced.**
- Application: `decorators.py` (`Idempotent`, `Replayable`, `fingerprint`), `serialization.py`, ports `Transaction`/`IdempotencyStore`/`StoredResponse`.
- Infrastructure: `idempotency.py` (insert-first reservation, `23505` → conflict), `IdempotencyRecord` and migration 0002, `purge_idempotency_keys`, and the unit of work rebuilt as a nestable stack.
- The view sets `Idempotent-Replayed: true`.

**Verified.**
- 9 application tests with fakes: replay, offset-equivalent payload, different payload, failure not stored then retried, key taken concurrently, codec round-trip.
- 4 store tests on Postgres.
- 4 API tests (rule 8, conflict, retry after failure, key row stored with the appointment).
- Live in compose: `201` → replay `201` with the header (same id) → `409 idempotency_conflict`.
- 243 tests passing. All checks green.
- The genuine *concurrent* duplicate case (two threads, real connections) is covered in M9.

**Corrected.**
- The first purge-command test reused the frozen test clock, but the command uses wall-clock time. It was rewritten to use real timestamps rather than injecting a clock into an ops command.
- mypy flagged `encode=dict` in the test as not matching `Callable[[R], dict]`. It now uses an explicit, typed identity.

## Milestone 8 — Observability (2026-10-08)

**Intent.** Logging/metrics/tracing decorators and middleware, compose collector config (§9).

**Produced.**
- Application: `Instrumented` decorator, `UseCaseTelemetry`/`BookingObserver` ports, retry/conflict hooks in the booking handler.
- Infrastructure: `telemetry/{metrics,logging,tracing,middleware}.py`.
- Runtime: `gunicorn.conf.py`, WhiteNoise, prod settings in compose, `ops/prometheus-alerts.yml`, a detailed OTel collector config, and new Makefile targets (`superuser`, `purge-keys`, `logs`).

**Verified.**
- 5 application tests (outcome codes, span attributes, log fields, conflict/retry counting).
- 4 API tests: `/metrics` deltas per outcome, cache hit/miss counts, JSON log line with the correlation id, use-case span with an `outcome` attribute via an in-memory exporter.
- Live with 4 gunicorn workers:
  - `/metrics` aggregates all workers (5 hits / 3 misses over 8 availability calls).
  - A JSON log line carries `correlation_id`, `route`, `trace_id` and `span_id`.
  - A client `traceparent` (`4bf92f35…`) is propagated to every SQL span in the collector.
  - Prometheus loaded the 4 alert rules.
  - Admin static files and Swagger UI return 200 under `DEBUG=False`.
- 252 tests passing. All checks green.

**Corrected.**
- The collector at first showed no span names, because compose had not recreated it after its mounted config changed. `docker compose restart` fixed it. Worth knowing for the demo.
- WhiteNoise warned in every test about the missing `STATIC_ROOT`. It is now container-only, not silenced.
- The gunicorn hook's `type: ignore` used the wrong error code. mypy pointed to the exact one needed.

## Milestone 9 — Concurrency, constraints and load (2026-10-08)

**Intent.** Concurrency and constraint tests, then load tests against the §2.1 targets. Find the bottleneck *before* tuning anything.

**Produced.**
- `tests/concurrency/` (helpers, 6 tests): 20-thread races for the last bay/technician and a hot slot, a concurrent duplicate idempotency key, concurrent cancels, a cancel/rebook race, and a test that **drops the exclusion constraints** to show the app alone double-books.
- Load seed commands (`seed_load*`) and the `docker-compose.load.yml` overlay.
- `tests/load/k6.js` (open-model scenarios), `locustfile.py`, and `hot_slot.py` (computes the expected capacity from the DB, then fires 50 simultaneous requests).
- `make load / load-stress / hot-slot / locust`.

**Verified.**
- Concurrency suite green. Without constraints, **19 of 20** requests confirmed the same single bay/technician; with them, exactly 1.
- Load results are in the README (`docs/load/` holds raw k6 output and resource samples).

**Corrected (two good stories).**
1. *500s on the first load run.* The correlation id in the problem response led straight to the JSON log line: `ValueError: Invalid VIN 'LOAD…'`. The AI had generated seed VINs containing **O** (forbidden). `bulk_create` skips model validators, but the domain `Vin` value object rejected the data at runtime. The fix was in the seed, not the domain.
2. *"Availability misses its SLO" turned out to be a measurement artifact.* Locust reported p95 ≈ 220 ms (target 150 ms). Instead of adding workers, the AI investigated:
   - django-prometheus said the full request took **6.7 ms** server-side, and the use case 4.8 ms.
   - CPU was mostly idle everywhere.
   - A plain-Python client reproducing Locust's exact shape (110 closed-loop users) measured **p95 12 ms**.
   - The following changed nothing: `HttpUser` vs `FastHttpUser`, `Connection: close`, `127.0.0.1`, 8 Locust processes, running Locust *inside* the compose network, and moving gunicorn's heartbeat off overlayfs.
   - k6 on the compose network measured p95 ≈ 9 ms.

   Conclusion: Locust on this WSL2 host adds ~120 ms client-side. Recorded numbers use k6, cross-checked with server metrics (I48). Several plausible "fixes" (more workers, caching tweaks) would have been tuned against a phantom.

## Milestone 10 — Docs and demo materials (2026-10-08)

**Intent.** System design document, curl examples, README with AI Collaboration Narrative and load results, plus materials for a Loom walkthrough.

**Produced.**
- `docs/SYSTEM_DESIGN.md`: deployment, layer, domain-model and booking-sequence diagrams (Mermaid); assumptions; D1–D5; technology choices; reliability; observability; capacity with measured results; GenAI in design.
- `docs/curl-examples.md`.
- README: quick start, testing, load results, narrative.
- `scripts/demo.sh`: a guided, self-resetting 12-step terminal demo. Its date is computed so it never goes stale, and it handles New York DST.
- `docs/demo/LOOM_SCRIPT.md`: a timed talk track with a pre-recording checklist and troubleshooting.
- A 9-slide deck published as a claude.ai artifact.
- CI gained a migration-drift check and a Docker image build.

**Verified.** The demo was rehearsed end to end (`AUTO=1 ./scripts/demo.sh`) against the normal stack. The final gate is green: ruff, `mypy --strict` (139 files), `lint-imports` (5 kept), 258 tests, `makemigrations --check`, and `make schema --validate`.

**Corrected.** The rehearsal caught two demo-script bugs that would have broken the recording:
- An escaped quote inside a Python f-string (a `SyntaxError`).
- A `step()` helper ending in `[[ … ]] && echo`, which returned 1 when no subtitle was given and silently stopped the script under `set -e`.

The JSON output was also compacted to fit a video frame.
