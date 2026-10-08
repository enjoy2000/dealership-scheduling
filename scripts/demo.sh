#!/usr/bin/env bash
# Guided demo of the Unified Service Scheduler (for the Loom recording).
#
#   ./scripts/demo.sh            interactive: press Enter between steps
#   AUTO=1 ./scripts/demo.sh     no pauses (rehearsal)
#
# Needs the compose stack running with the demo seed (`make up migrate seed`).
# Resets ONLY the demo dealership's appointments (Uptown Auto, id 2) and idempotency keys
# created by this script, so the story is the same every time.
set -euo pipefail
cd "$(dirname "$0")/.."

API=${API:-http://localhost:8000/api/v1}
BOLD=$'\e[1m'; DIM=$'\e[2m'; CYAN=$'\e[36m'; GREEN=$'\e[32m'; RED=$'\e[31m'; YELLOW=$'\e[33m'; RESET=$'\e[0m'
RUN_ID=$(date +%s)

# Next Monday at least a week out, so the date is always in the future.
read -r DAY NY_0900 NY_1000 NY_1030 NY_1100 NY_0800 < <(python3 - <<'PY'
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
d = date.today() + timedelta(days=7)
d += timedelta(days=(7 - d.weekday()) % 7)
ny = ZoneInfo("America/New_York")
z = lambda h, m=0: datetime.combine(d, time(h, m), ny).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
print(d.isoformat(), z(9), z(10), z(10, 30), z(11), z(8))
PY
)

step() {
  echo; echo "${BOLD}${CYAN}━━ $1${RESET}"
  if [[ -n "${2:-}" ]]; then echo "${DIM}$2${RESET}"; fi
}
pause() { [[ "${AUTO:-}" == "1" ]] || read -rp "${DIM}↵ next${RESET} " _; }
show() { echo "${YELLOW}\$ $*${RESET}"; }
# One line per top-level key, nested objects inline: fits a video frame.
pretty() { python3 -c '
import json, sys
d = json.load(sys.stdin)
print("{")
for i, (k, v) in enumerate(d.items()):
    print(f"  \"{k}\": {json.dumps(v)}" + ("," if i < len(d) - 1 else ""))
print("}")'; }

# POST helper: prints status line + interesting headers + pretty body; sets LAST_ID.
book() {
  local key=$1 body=$2 out headers status
  show "curl -X POST $API/appointments/ -H 'Idempotency-Key: $key' -d '$body'"
  headers=$(mktemp); out=$(mktemp)
  curl -s -D "$headers" -o "$out" -X POST "$API/appointments/" \
    -H "Content-Type: application/json" -H "Idempotency-Key: $key" -d "$body"
  status=$(head -1 "$headers" | tr -d '\r')
  [[ $status == *" 2"* ]] && echo "${GREEN}${status}${RESET}" || echo "${RED}${status}${RESET}"
  grep -iE '^(location|idempotent-replayed|x-correlation-id):' "$headers" | tr -d '\r' || true
  pretty < "$out"
  LAST_ID=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("id",""))' "$out")
  rm -f "$headers" "$out"
}

slots() {
  curl -s "$API/availability/?dealership_id=2&service_type_id=2&date=$DAY" | python3 -c '
import json, sys
d = json.load(sys.stdin)
starts = [s["start_time"][11:16] for s in d["slots"]]
day = d["date"]
print(f"{len(starts)} bookable starts (UTC) on {day}: " + " ".join(starts))'
}

body() { # customer vehicle start
  printf '{"customer_id": %s, "vehicle_id": %s, "service_type_id": 2, "dealership_id": 2, "start_time": "%s"}' "$1" "$2" "$3"
}

# ---------------------------------------------------------------------------------------
step "0. Reset the demo dealership" "Uptown Auto (id 2, New York): ONE service bay, ONE technician (Dana)."
docker compose exec -T db psql -U scheduler -d scheduler -qc \
  "delete from scheduling_appointment where dealership_id = 2; delete from scheduling_idempotency_record where key like 'demo-%';" >/dev/null
docker compose ps --format '  {{.Service}}: {{.Status}}'
echo "Demo day: ${BOLD}$DAY${RESET} (09:00 New York = $NY_0900)"
pause

step "1. Health and API contract" "Liveness vs readiness; OpenAPI + Swagger UI at http://localhost:8000/api/v1/docs/"
show "curl localhost:8000/healthz ; curl localhost:8000/readyz"
curl -s localhost:8000/healthz; echo; curl -s localhost:8000/readyz; echo
pause

step "2. Availability" "Brake Service (90 min) at Uptown Auto. Only starts where a bay AND a qualified technician are free."
show "curl '$API/availability/?dealership_id=2&service_type_id=2&date=$DAY'"
slots
pause

step "3. Book: 201 Created + Location" "Customer 1, vehicle 1, 09:00 New York. Bay and technician are allocated automatically."
book "demo-$RUN_ID-a" "$(body 1 1 "$NY_0900")"
FIRST_ID=$LAST_ID
pause

step "4. Client retry with the same Idempotency-Key" "Same payload: the original 201 is replayed, nothing is booked twice."
book "demo-$RUN_ID-a" "$(body 1 1 "$NY_0900")"
pause

step "5. A competing request that overlaps (10:00, while Dana is busy until 10:30)" "Different customer and vehicle: the only bay/technician is taken, so 409 and nothing is persisted."
book "demo-$RUN_ID-b" "$(body 2 3 "$NY_1000")"
pause

step "6. Back-to-back is fine (10:30)" "Intervals are half-open [start, end)."
book "demo-$RUN_ID-c" "$(body 2 3 "$NY_1030")"
SECOND_ID=$LAST_ID
pause

step "7. Business rules return precise problem+json errors"
echo "${BOLD}Someone else's vehicle →${RESET}"; book "demo-$RUN_ID-d" "$(body 2 1 "$NY_1100")" | tail -n +2
echo "${BOLD}Before opening (08:00 New York) →${RESET}"; book "demo-$RUN_ID-e" "$(body 3 4 "$NY_0800")" | tail -n +2
echo "${BOLD}No Idempotency-Key →${RESET}"
show "curl -X POST $API/appointments/ (no Idempotency-Key header)"
curl -s -X POST "$API/appointments/" -H "Content-Type: application/json" -d "$(body 3 4 "$NY_1100")" | pretty
pause

step "8. Availability reflects the bookings immediately" "Booking events invalidate the 5-second availability cache for that dealership and day."
slots
pause

step "9. Cancel: 204 No Content (and again: still 204)" "Cancelling frees the bay and technician."
show "curl -X DELETE $API/appointments/$FIRST_ID/"
curl -s -o /dev/null -w "HTTP %{http_code}\n" -X DELETE "$API/appointments/$FIRST_ID/"
curl -s -o /dev/null -w "HTTP %{http_code} (repeat)\n" -X DELETE "$API/appointments/$FIRST_ID/"
show "curl $API/appointments/$FIRST_ID/"
curl -s "$API/appointments/$FIRST_ID/" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("status:", d["status"])'
slots
pause

step "10. Hot slot: 50 simultaneous requests for ONE slot" "Dealership 1001: 8 bays, 6 brakes-qualified technicians -> successes must equal free capacity, rest 409, zero overlaps."
docker compose exec -T web python manage.py seed_load --dealerships 1 --customers 60 >/dev/null
HOT_DAYS=$(( 90 + RUN_ID % 200 ))  # a fresh day beyond the load-test window
show "python tests/load/hot_slot.py --requests 50 --dealership 1001 --service-type 2 --days-ahead $HOT_DAYS"
uv run --quiet python tests/load/hot_slot.py --requests 50 --dealership 1001 --service-type 2 --days-ahead "$HOT_DAYS" || true
pause

step "11. Observability" "Metrics by outcome, JSON logs with correlation and trace ids, Prometheus on :9090"
show "curl -s localhost:8000/metrics | grep booking_"
curl -s localhost:8000/metrics | grep -E '^booking_(requests|conflicts|retries)_total' || true
CORR="demo-corr-$RUN_ID"
curl -s -o /dev/null -H "X-Correlation-ID: $CORR" "$API/appointments/$SECOND_ID/"
sleep 1
show "docker compose logs web | grep $CORR"
docker compose logs web --no-log-prefix 2>/dev/null | grep "$CORR" | tail -1 | python3 -m json.tool || true
pause

step "12. Architecture is enforced, not just documented" "import-linter contracts: the domain cannot import Django; interface cannot reach infrastructure."
show "uv run lint-imports"
uv run --quiet lint-imports | tail -8
echo
echo "${BOLD}${GREEN}Done.${RESET} Swagger UI: http://localhost:8000/api/v1/docs/   Prometheus: http://localhost:9090   Admin: http://localhost:8000/admin/"
