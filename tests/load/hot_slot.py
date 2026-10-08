"""Hot-slot burst (SPEC §2.1): N simultaneous bookings for ONE dealership and slot.

Expect successes == min(free bays, free qualified technicians) for that slot (computed from
the database before the burst), the rest 409, and zero double bookings anywhere. Usage:
    uv run python tests/load/hot_slot.py --requests 50 --dealership 1001 --service-type 2
"""

import argparse
import datetime as dt
import subprocess
import sys
import threading
import uuid
from collections import Counter
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from common import DURATIONS, random_day, random_start

OVERLAP_SQL = """
SELECT count(*) FROM scheduling_appointment a JOIN scheduling_appointment b
  ON a.id < b.id AND a.status = 'CONFIRMED' AND b.status = 'CONFIRMED'
 AND a.time_range && b.time_range
 AND (a.service_bay_id = b.service_bay_id OR a.technician_id = b.technician_id
      OR a.vehicle_id = b.vehicle_id);
"""


CAPACITY_SQL = """
WITH busy AS (
  SELECT service_bay_id, technician_id FROM scheduling_appointment
   WHERE status = 'CONFIRMED' AND time_range && tstzrange('{start}', '{end}', '[)'))
SELECT least(
  (SELECT count(*) FROM scheduling_service_bay b
    WHERE b.dealership_id = {dealership}
      AND b.id NOT IN (SELECT service_bay_id FROM busy)),
  (SELECT count(*) FROM scheduling_technician t
    WHERE t.dealership_id = {dealership}
      AND t.id NOT IN (SELECT technician_id FROM busy)
      AND EXISTS (SELECT 1 FROM scheduling_technician_skill s
                   WHERE s.technician_id = t.id
                     AND s.skill = (SELECT required_skill FROM catalog_servicetype
                                     WHERE id = {service_type}))));
"""


def psql(sql: str) -> str:
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "db",
        "psql",
        "-U",
        "scheduler",
        "-d",
        "scheduler",
        "-tAc",
        sql,
    ]
    return subprocess.run(command, capture_output=True, text=True, check=True).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="http://localhost:8000")
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--dealership", type=int, default=1001)
    parser.add_argument("--service-type", type=int, default=2)
    parser.add_argument("--days-ahead", type=int, help="default: random within the load window")
    args = parser.parse_args()

    day = dt.date.today() + dt.timedelta(days=args.days_ahead) if args.days_ahead else random_day()
    start = random_start(args.service_type, day)
    end = (
        dt.datetime.fromisoformat(start.replace("Z", "+00:00"))
        + dt.timedelta(minutes=DURATIONS[args.service_type])
    ).isoformat()
    expected = int(
        psql(
            CAPACITY_SQL.format(
                start=start, end=end, dealership=args.dealership, service_type=args.service_type
            )
        )
    )
    barrier = threading.Barrier(args.requests)
    statuses: list[int] = [0] * args.requests

    def fire(index: int) -> None:
        customer = 100_000 + 1 + index  # distinct customers/vehicles: only bays/techs contend
        body = {
            "customer_id": customer,
            "vehicle_id": customer,
            "service_type_id": args.service_type,
            "dealership_id": args.dealership,
            "start_time": start,
        }
        barrier.wait()
        response = requests.post(
            f"{args.host}/api/v1/appointments/",
            json=body,
            headers={"Idempotency-Key": str(uuid.uuid4())},
            timeout=30,
        )
        statuses[index] = response.status_code

    threads = [threading.Thread(target=fire, args=(i,)) for i in range(args.requests)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    counts = Counter(statuses)
    overlaps = psql(OVERLAP_SQL)
    print(f"slot {start} at dealership {args.dealership}, {args.requests} simultaneous requests")
    print(f"capacity before the burst (free bays vs free qualified technicians): {expected}")
    print(f"status counts: {dict(sorted(counts.items()))}")
    print(f"overlapping confirmed pairs in the whole database: {overlaps}")
    ok = overlaps == "0" and counts.get(201, 0) == expected and set(counts) <= {201, 409}
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
