# Loom recording kit: Unified Service Scheduler

Target length **~12 minutes**. Four segments: *why/what → live demo → proof → AI collaboration*.
Everything shown is real and reproducible from this repo.

---

## Before you hit record (5 minutes)

```bash
make up && make migrate && make seed          # stack + demo data
docker compose exec web python manage.py seed_load --dealerships 1 --customers 60   # hot-slot data
AUTO=1 ./scripts/demo.sh > /dev/null          # rehearsal run (also warms caches/connections)
```

Open these, in this order, as browser tabs / windows:

1. **Slides** (the deck published with this kit), on the title slide.
2. **Terminal**, font ≥ 16 pt, ~110 columns wide, repo root, `clear`.
3. **Swagger UI**: <http://localhost:8000/api/v1/docs/>
4. **Prometheus**: <http://localhost:9090/graph?g0.expr=sum%20by%20(outcome)%20(increase(booking_requests_total%5B15m%5D))&g0.tab=1>
5. **Editor** with `docs/SYSTEM_DESIGN.md` (diagrams render in GitHub/VS Code preview),
   `contexts/scheduling/infrastructure/persistence/models.py` (exclusion constraints) and
   `.importlinter`.

Turn off notifications. Close unrelated tabs.

---

## 0:00–1:00 · Hook and problem (slides 1–2)

> "Dealerships book service appointments by hand, which double-books bays and sends jobs to
> technicians without the right skill. I built the backend for Scenario A: an API that confirms
> an appointment **only if** a service bay **and** a qualified technician are free for the
> **whole** service duration, and persists it, safely under concurrency."

> "Stack: Django and DRF on PostgreSQL, Domain-Driven Design, everything in Docker Compose.
> I'll show it running, then *prove* it's correct, then talk about how I worked with AI."

## 1:00–3:00 · Architecture (slides 3–5)

* **Contexts.** Scheduling is the core domain with full DDD; Catalog (dealerships, service
  types, customers, vehicles) is deliberately plain Django. Scheduling only sees Catalog
  through a gateway that returns its own value objects.
* **Layers.** Domain is pure Python: no Django import, enforced by import-linter in CI.
  Application holds use cases and ports; infrastructure implements them.
* **The key decision (D1/D2).**
  > "'No overlapping bookings' spans many appointments. If I modelled a per-dealership
  > schedule aggregate, every booking at a dealership would queue behind one lock. Instead
  > `Appointment` is the only aggregate, the domain pre-checks for good error messages, and
  > **PostgreSQL exclusion constraints are the final guard**: the database itself refuses two
  > confirmed rows for the same bay, technician or vehicle with overlapping time ranges."
* Show `models.py` constraint block for five seconds.

## 3:00–8:00 · Live demo (terminal: `./scripts/demo.sh`)

Press Enter through the steps; suggested narration:

| Step | Say |
|---|---|
| 0 | "Uptown Auto has exactly **one** bay and **one** technician: the easiest place to see conflicts." |
| 1 | "Liveness vs readiness. The OpenAPI contract is the stubbed client; here's Swagger." *(flash Swagger tab)* |
| 2 | "Availability lists only starts where a bay **and** a qualified technician are free for the full 90 minutes. Dates are the dealership's local day; the wire is UTC." |
| 3 | "Booking returns **201 with a Location header**; bay and technician are allocated automatically (least-loaded qualified technician)." |
| 4 | "Clients retry. Same Idempotency-Key, same payload: the original response is **replayed**, nothing is booked twice." |
| 5 | "A different customer overlapping that slot gets **409 no_capacity**, as RFC 7807 problem JSON with a correlation id, and nothing is persisted." |
| 6 | "Back-to-back at 10:30 works: intervals are half-open." |
| 7 | "Every business rule has a precise status: someone else's vehicle is 422, before opening hours is 422, a missing Idempotency-Key is 400." |
| 8 | "Availability reflects the bookings immediately: booking events invalidate the cache for that dealership and day." |
| 9 | "Cancel is **204 No Content**, idempotent, and the slot comes back." |
| 10 | "Now the important one: **50 simultaneous requests for one slot**. This dealership has 8 bays but only 6 brakes-qualified technicians. Exactly 6 succeed, 44 get 409, zero overlaps in the database." |
| 11 | "Metrics by outcome, conflicts and retries; one JSON log line per use case with correlation and trace ids." *(flash Prometheus tab)* |
| 12 | "And the architecture is enforced: five import contracts, all kept." |

## 8:00–10:00 · Proof (slides 6–7, terminal)

```bash
uv run pytest -q                                            # 260+ tests, real PostgreSQL
uv run pytest tests/concurrency -v                          # the race tests
```

> "The test I like most is this one: it **drops the exclusion constraints** and runs the same
> 20-request race. The application's own checks are fine one at a time, but under concurrency
> they race: **19 bookings for one bay**. Put the constraints back and exactly one wins. That's
> the whole design argument in one test."

Load results (slide 7): read the k6 table. Then the honest bit:

> "My first load test said availability missed its SLO at ~220 ms p95. Before tuning anything
> I compared server-side histograms (7 ms), a plain Python client and k6 (both ~10 ms). The
> latency was in the load generator on my WSL2 box, not the service, so the recorded numbers
> are from k6, cross-checked against server metrics."

## 10:00–11:30 · Working with AI (slide 8)

* **Spec first.** Assumptions, layering rules, DB constraints, milestones and acceptance
  criteria written *before* code; Claude Code implemented one milestone at a time, tests first.
* **Guardrails catch AI mistakes mechanically.**
  * import-linter blocked a view importing the composition root. The fix was dependency
    inversion, *not* loosening the contract (that's a rule in CLAUDE.md).
  * mypy's Django plugin caught a regex refactor that silently turned
    `constraints = (X,)` into a bare object; ruff was green.
  * The domain's VIN value object rejected bad seed data the AI generated for load tests.
* **I stayed in the loop.** I redirected it twice: dependencies only via Docker Compose
  (it had started using a host Postgres), and RESTful `204` for DELETE instead of the spec's
  `200`. Every decision it made is logged in `docs/DECISIONS.md` (47 of them) and every
  milestone in `docs/AI_LOG.md`.

## 11:30–12:00 · Wrap-up (slide 9)

> "Trade-offs I'd revisit at scale: PgBouncer and a read replica, monthly partitions, a
> transactional outbox for notifications, then sharding by dealership, which is natural
> because no booking spans dealerships. Thanks for watching."

---

## If something goes wrong on camera

| Symptom | Fix |
|---|---|
| Step 3 says 409 | Re-run `./scripts/demo.sh`; step 0 resets the demo dealership. |
| Hot slot prints FAIL with fewer successes | Another run used that day; the script picks a fresh day each run, just rerun step 10. |
| `connection refused` | `make up` (wait for "Healthy"), then `make migrate seed`. |
| Prometheus shows no data | `docker compose restart prometheus`, wait 10 s. |
| Collector shows no spans | `docker compose restart otel-collector`. |
