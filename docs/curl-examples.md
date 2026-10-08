# curl examples (stubbed client)

Run against the compose stack with the demo seed (`make up migrate seed`). Times are UTC.
Dealership 2 ("Uptown Auto", New York, 09:00–18:00 local) has **one bay and one technician**,
so it is the easiest place to see conflicts. Interactive version: Swagger UI at
<http://localhost:8000/api/v1/docs/>. A scripted walk-through of everything below:
`./scripts/demo.sh`.

```bash
API=http://localhost:8000/api/v1
```

## 1. What can I book?

```bash
curl -s "$API/availability/?dealership_id=2&service_type_id=2&date=2026-11-02"
```

```json
{"dealership_id": 2, "service_type_id": 2, "date": "2026-11-02",
 "slots": [{"start_time": "2026-11-02T14:00:00Z", "end_time": "2026-11-02T15:30:00Z"},
           {"start_time": "2026-11-02T14:15:00Z", "end_time": "2026-11-02T15:45:00Z"}, "…"]}
```

`date` is the dealership's local day; 09:00 EST is 14:00Z.

## 2. Book (201 + Location)

```bash
curl -si -X POST "$API/appointments/" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: 7f3c2a9e-demo-0001" \
  -d '{"customer_id": 1, "vehicle_id": 1, "service_type_id": 2,
       "dealership_id": 2, "start_time": "2026-11-02T14:00:00Z"}'
```

```http
HTTP/1.1 201 Created
Location: http://localhost:8000/api/v1/appointments/5b1e8c1a-…/
X-Correlation-ID: 3f2d…
```

```json
{"id": "5b1e8c1a-…", "status": "CONFIRMED",
 "start_time": "2026-11-02T14:00:00Z", "end_time": "2026-11-02T15:30:00Z",
 "customer": {"id": 1, "name": "Customer One"},
 "vehicle": {"id": 1, "vin": "1HGCM82633A004352"},
 "service_type": {"id": 2, "name": "Brake Service", "duration_minutes": 90},
 "dealership": {"id": 2, "name": "Uptown Auto"},
 "technician": {"id": 4, "name": "Dana"},
 "service_bay": {"id": 4, "name": "Bay 1"}}
```

## 3. Retry safely (idempotent replay)

Repeat the same request with the same key: same `201` body, no second row.

```http
HTTP/1.1 201 Created
Idempotent-Replayed: true
```

Same key, different payload:

```json
{"type": "about:blank", "title": "Idempotency conflict", "status": 409,
 "detail": "The Idempotency-Key was already used with a different payload.",
 "code": "idempotency_conflict", "correlation_id": "…"}
```

## 4. Overlap → 409 no_capacity

Another customer wants 15:00Z at the same dealership (overlaps 14:00–15:30):

```bash
curl -s -X POST "$API/appointments/" -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-0002" \
  -d '{"customer_id": 2, "vehicle_id": 3, "service_type_id": 2,
       "dealership_id": 2, "start_time": "2026-11-02T15:00:00Z"}'
```

```json
{"type": "about:blank", "title": "No capacity", "status": 409,
 "detail": "No service bay and qualified technician are free for the requested time.",
 "code": "no_capacity", "correlation_id": "…"}
```

Back-to-back (`15:30Z`) succeeds: intervals are half-open.

## 5. Validation and business-rule errors

| Request | Status | `code` |
|---|---|---|
| No `Idempotency-Key` header | 400 | `validation_error` |
| `"start_time": "2026-11-02T09:00:00"` (no offset) | 400 | `validation_error` (`errors.start_time`) |
| `"customer_id": 99` | 404 | `not_found` |
| `"customer_id": 2, "vehicle_id": 1` (someone else's car) | 422 | `vehicle_not_owned` |
| `"start_time": "2026-11-02T14:10:00Z"` (off the 15-minute grid) | 422 | `invalid_slot` |
| A start in the past | 422 | `invalid_slot` |
| `"start_time": "2026-11-02T13:00:00Z"` (08:00 New York, before opening) | 422 | `outside_opening_hours` |
| Same vehicle, overlapping time, any dealership | 409 | `vehicle_already_booked` |
| More than 60 bookings/min for one customer | 429 | `throttled` (+ `Retry-After`) |

## 6. Fetch and cancel

```bash
curl -s "$API/appointments/5b1e8c1a-…/"                                 # 200, same body
curl -si -X DELETE "$API/appointments/5b1e8c1a-…/" | head -1           # HTTP/1.1 204 No Content
curl -si -X DELETE "$API/appointments/5b1e8c1a-…/" | head -1           # 204 again (idempotent)
curl -s "$API/appointments/5b1e8c1a-…/" | jq .status                   # "CANCELLED"
```

Cancelling at or after the start time → `422 cancellation_not_allowed`. After a cancel the
14:00Z slot is offered again by `/availability/` and can be booked by someone else.

## 7. Operations

```bash
curl -s localhost:8000/healthz      # {"status": "ok"}           (process up)
curl -s localhost:8000/readyz       # {"status": "ok", "database": "up"}
curl -s localhost:8000/metrics | grep -E '^booking_(requests|conflicts|retries)_total'
curl -s localhost:8000/api/v1/schema/ > openapi.yaml
```

Pass `X-Correlation-ID: my-id` on any request to find its log lines (`make logs | grep my-id`)
and send a W3C `traceparent` to join an existing trace.
