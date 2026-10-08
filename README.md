# Unified Service Scheduler

Backend for Keyloop's Scenario A: a REST API that books a **service bay** and a **qualified
technician** for a dealership appointment, and confirms **only if both are free for the entire
service duration**, safely under concurrency.

Django 5 · DRF · PostgreSQL 16 (exclusion constraints) · Redis · Domain-Driven Design ·
Docker Compose · OpenTelemetry · Prometheus

| Document | |
|---|---|
| [`docs/SYSTEM_DESIGN.md`](docs/SYSTEM_DESIGN.md) | System design: architecture diagrams, data flow, decisions D1–D5, technology choices, observability, capacity, GenAI in design |
| [`docs/openapi.yaml`](docs/openapi.yaml) · [`docs/curl-examples.md`](docs/curl-examples.md) | Stubbed client: OpenAPI 3 contract (Swagger UI at `/api/v1/docs/`) and curl walkthrough |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Every implementation decision not in the spec, with rationale (I1–I47) |
| [`docs/AI_LOG.md`](docs/AI_LOG.md) | Per-milestone AI collaboration log: intent, output, verification, corrections |
| [`docs/demo/LOOM_SCRIPT.md`](docs/demo/LOOM_SCRIPT.md) · [`scripts/demo.sh`](scripts/demo.sh) | Demo talk track and the guided terminal demo |
| [`SPEC.md`](SPEC.md) | The specification the build followed (v1.1) |

---

## Quick start

Requirements: Docker with Compose v2, [uv](https://docs.astral.sh/uv/), GNU Make. All backing
services run in containers; nothing else is installed on the host.

```bash
cp .env.example .env        # optional: compose has safe local defaults
make up                     # build + start web, postgres, redis, otel-collector, prometheus
make migrate
make seed                   # demo dealerships, bays, technicians, customers (SPEC §14.7)
curl localhost:8000/readyz  # {"status": "ok", "database": "up"}
```

| URL | |
|---|---|
| <http://localhost:8000/api/v1/docs/> | Swagger UI (try the API in the browser) |
| <http://localhost:8000/admin/> | Reference-data admin (`make superuser` first) |
| <http://localhost:8000/metrics> | Prometheus metrics |
| <http://localhost:9090> | Prometheus (with SLO alert rules) |

Guided demo of every behaviour: `./scripts/demo.sh` (press Enter between steps).

### API at a glance

```bash
curl -s "localhost:8000/api/v1/availability/?dealership_id=2&service_type_id=2&date=2026-11-02"

curl -si -X POST localhost:8000/api/v1/appointments/ \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: 3b6f…' \
  -d '{"customer_id":1,"vehicle_id":1,"service_type_id":2,"dealership_id":2,
       "start_time":"2026-11-02T14:00:00Z"}'          # 201 + Location

curl -s  localhost:8000/api/v1/appointments/<id>/      # 200
curl -si -X DELETE localhost:8000/api/v1/appointments/<id>/   # 204 (idempotent)
```

Errors are RFC 7807 `application/problem+json` with a stable `code`
(`no_capacity`, `vehicle_already_booked`, `idempotency_conflict`, `invalid_slot`,
`outside_opening_hours`, `vehicle_not_owned`, `cancellation_not_allowed`, `not_found`,
`validation_error`, `throttled`) and a `correlation_id`. Full walkthrough:
[`docs/curl-examples.md`](docs/curl-examples.md).

---

## Development

```bash
uv sync                # Python 3.12 toolchain from the lockfile
make test              # starts postgres + redis via compose, runs pytest with coverage
make lint              # ruff + mypy --strict
make arch              # import-linter layer contracts
make schema            # regenerate docs/openapi.yaml
```

| Make target | |
|---|---|
| `up` / `down` / `logs` | Stack lifecycle; `logs` tails the JSON logs |
| `migrate` / `seed` / `superuser` | Database setup and admin login |
| `purge-keys` | Delete expired idempotency keys (cron in production) |
| `load-up` / `load` / `load-stress` / `hot-slot` | Load-test stack, k6 scenarios, hot-slot burst |
| `locust` | Interactive Locust UI |

### Project layout

```
config/                          Django project (settings base/dev/test/prod, urls, wsgi)
shared_kernel/                   DomainEvent base, Clock port
contexts/
  catalog/                       SUPPORTING: dealerships, service types, customers, vehicles
  scheduling/                    CORE domain
    domain/                      pure Python: Appointment, TimeSlot, policies, allocator, …
    application/                 use cases, ports, DTOs, decorators (idempotent, instrumented)
    infrastructure/              ORM + constraints, repositories, UoW, Redis, telemetry, gateway
    interface/api/               DRF views, serializers, problem details, throttles
    container.py                 composition root
tests/
  unit/domain  unit/application  (no database, no Django)
  infrastructure  api  concurrency  architecture  load
```

### Configuration

All configuration is via environment variables (`.env.example`): `SECRET_KEY`,
`ALLOWED_HOSTS`, `DATABASE_URL`, `REDIS_URL`, `OTEL_EXPORTER_OTLP_ENDPOINT`,
`BOOKING_MAX_RETRIES` (3), `AVAILABILITY_CACHE_TTL_SECONDS` (5), `IDEMPOTENCY_TTL_HOURS` (24),
`DB_STATEMENT_TIMEOUT_MS` (2000), `WEB_CONCURRENCY` (4), `THROTTLE_BOOKING_RATE` (60/min per
customer), `THROTTLE_AVAILABILITY_RATE` (120/min per client), `LOG_LEVEL`, `LOG_FORMAT`.

---

## Testing

**258 tests, all on real PostgreSQL 16** (in compose) except the unit suites, which need neither
Django nor a database. Coverage: **domain 100 %, application 99 %** (targets 90 / 85), 93 % overall.

```
make test     # or: uv run pytest
139 unit (domain + application, run with -p no:django) · 49 infrastructure · 63 api
  · 6 concurrency · 1 architecture
```

| Suite | What it proves |
|---|---|
| `unit/domain` | `TimeSlot` half-open overlap, 15-minute grid, opening hours across London and New York DST transitions, allocation rule A9, aggregate state transitions and events, availability calculation. **Runs with the Django plugin disabled.** |
| `unit/application` | Use cases against in-memory fakes that mimic transactions and exclusion constraints: retry on `ResourceConflict` (including re-allocation around a concurrent winner), idempotency, caching and invalidation, instrumentation. |
| `infrastructure` | Real PostgreSQL: migrations and `btree_gist`, raw-ORM overlapping inserts rejected by each constraint, `23P01` → `ResourceConflict` (and *only* `23P01`), repositories, read models (fixed query count), unit of work, cache, idempotency store, seeds. |
| `api` | Every §7 acceptance criterion over HTTP, problem+json shape, throttling, a brute-force proof that availability equals "bookable", and OpenAPI contract validation of responses. |
| `concurrency` | 20 threads with their own connections racing for one slot: exactly one winner; hot slot = capacity; concurrent duplicate idempotency keys; concurrent cancels; and a test that **drops the constraints and shows the app alone double-books**. |
| `architecture` | import-linter contracts (also run in CI). |

Mutation checks during development (removing the ownership check, disabling retry, publishing
events before commit) each made tests fail. See `docs/AI_LOG.md`.

---

## Load-test results

k6 (open model: requests arrive at a fixed rate) against the compose stack with
`make load-up` (50 dealerships × 8 bays × 8 technicians, 5,000 customers; throttles lifted
because all traffic comes from one IP). **Host:** one WSL2 VM, 20 vCPU / 15 GB, running
the stack *and* the load generator. Raw output and resource samples: [`docs/load/`](docs/load/).

| Scenario | Workers | Throughput | Booking p50 / p95 / p99 | Availability p50 / p95 / p99 | Errors | DB conns |
|---|---|---|---|---|---|---|
| **Sustained design target**: 10 booking + 100 availability TPS (+15 % cancels), **10 min** | 4 | 113.5 req/s (66,925 requests) | 18.7 / **25.4** / 34.0 ms | 7.3 / **9.8** / 19.1 ms | 0 unexpected (100 % checks) | 5 |
| **Stress burst**: 50 booking + 500 availability TPS, 60 s | 4 | ~331 req/s (saturated) | p95 11.9 s | p95 11.1 s | 1.8 % client timeouts, 0 5xx | 5 |
| **Stress burst** after tuning | 16 | **571 req/s** (33,486 requests) | 24.9 / **39.4** / 100.8 ms | 11.4 / **16.2** / 93.5 ms | 0 unexpected (100 % checks) | 17 |
| **Hot slot**: 50 simultaneous requests for one slot (`make hot-slot`) | 16 | | 6 × 201, 44 × 409 (capacity 6) | | 0 overlaps in DB | |

**Against the §2.1 SLOs:** booking p95 < 300 ms / p99 < 800 ms ✅, availability p95 < 150 ms ✅,
5xx < 0.1 % ✅ (no 5xx in any run), hot slot = capacity with zero double bookings ✅. After the
sustained run the database held 5,058 confirmed and 924 cancelled appointments with no overlaps.

**Bottleneck and tuning.** With 4 sync workers the stress burst saturated web CPU (~3.2 cores),
so requests queued for seconds; Postgres sat at ~0.6 core with 5 connections. Raising
`WEB_CONCURRENCY` to 16 (no code change) served 571 req/s at ~6 cores web / ~1.2 cores DB.
The service itself is cheap: ~7 ms per availability request and ~18 ms per booking end to end.
Production sizing: about 4 workers per 100–150 req/s of uncached traffic, spread over pods,
with PgBouncer capping server connections.

**Why k6 and not Locust.** On this host every Locust configuration reported ~130 ms medians at
the design target. Meanwhile the server's own histograms said 6.7 ms, all processes were mostly
idle, and a plain-Python client with the same user shape measured p95 12 ms. Neither keep-alive
changes, `127.0.0.1`, 8 Locust processes, nor running Locust inside the Docker network changed
it. The latency was in the load generator, so recorded results use k6 (`make load`), cross-checked
against server metrics. The Locust file remains for interactive use (`make locust`).

---

## AI Collaboration Narrative

I built this with **Claude Code** as the implementing agent and myself as architect and
reviewer. The full per-milestone record is in [`docs/AI_LOG.md`](docs/AI_LOG.md); this is the
summary.

**1. Spec first, then a working agreement.** Before any code, I wrote `SPEC.md`: assumptions,
traffic model and SLOs, the layering rules, the database constraints, ten milestones and the
acceptance criteria. `CLAUDE.md` turned it into non-negotiables for the agent: one milestone at
a time, tests first for domain/application code, run ruff/mypy/pytest/import-linter before
declaring anything done, **never weaken a test or edit `.importlinter` to make a check pass**,
and record every new decision. The result is 47 logged decisions, each with a rationale I could
accept or reject.

**2. Guardrails that catch AI mistakes mechanically.** I don't trust plausible code, so the
build checks itself:
* *Layer leak.* The agent's first DRF views imported the composition root, which the
  import-linter contract forbids. The quick fix, editing the contract, was off the table, so
  the agent inverted the dependency instead: the interface declares a `SchedulingUseCases`
  protocol and `config/urls.py` installs the container.
* *Silent breakage.* A regex refactor (to satisfy a ruff rule) turned single-element
  `constraints = (X,)` tuples into bare objects. Ruff was green; **mypy's Django plugin
  crashed** on it, which is how it was caught before a migration ever ran.
* *Shadowed framework API.* A serializer field named `errors` silently shadowed DRF's
  `Serializer.errors`; mypy flagged it.
* *Bad generated data.* Load-test seed VINs contained the letter O (invalid). `bulk_create`
  skipped model validation, but the domain's `Vin` value object rejected them at runtime,
  which showed up as 500s in the first load run and was traced via correlation id in a minute.

**3. Where I overrode the AI.**
* It found a PostgreSQL already installed on the host and started wiring tests to it. I had
  it remove that and manage **every dependency through Docker Compose** (recorded as I1).
* The spec said a repeated `DELETE` returns `200`. I asked for RESTful semantics instead,
  **`204 No Content`**, and the agent updated the spec (v1.1), tests and handler together (I18).

**4. Evidence over assertions.** I asked for proof, not claims: mutation checks on the tests;
a test that **drops the exclusion constraints** and shows 19 of 20 concurrent requests
double-booking one bay (with constraints: exactly one); a brute-force check that availability
equals bookability. When the first load test said availability missed its SLO, the agent did
not tune anything. It showed that server-side latency was ~7 ms, reproduced ~10 ms with two
independent clients, and attributed the gap to the load generator on this host before
recording k6 results.

**5. What I'd keep doing.** Small milestones with a hard quality gate, an architecture
contract the AI cannot edit, a decision log, and asking "show me the failing test" or "what's
the bottleneck?" *before* accepting a change.
