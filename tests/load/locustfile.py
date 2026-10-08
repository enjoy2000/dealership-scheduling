"""Locust scenarios for SPEC §2.1, for interactive exploration (`make locust`, web UI).

Recorded results use k6 (`make load`): on the WSL2 test host every Locust configuration
added ~120 ms of client-side latency that neither the server histograms nor two other
clients showed (investigation in docs/AI_LOG.md, milestone 9).

User counts are fixed per class so each user is one request per second:
  sustained: BOOKING_USERS=10  AVAILABILITY_USERS=100  (10 + 100 TPS, 10 min)
  stress:    BOOKING_USERS=50  AVAILABILITY_USERS=500  (50 + 500 TPS, 60 s)
409 is a valid outcome (no capacity / vehicle already booked), not an error.
"""

import os
import random
import sys
import uuid
from pathlib import Path

from locust import FastHttpUser, constant_throughput, task

sys.path.insert(0, str(Path(__file__).parent))
from common import booking_payload, random_day, random_dealership

CANCEL_RATIO = 0.15


class BookingUser(FastHttpUser):
    fixed_count = int(os.environ.get("BOOKING_USERS", "10"))
    wait_time = constant_throughput(1)

    @task
    def book(self) -> None:
        with self.client.post(
            "/api/v1/appointments/",
            json=booking_payload(),
            headers={"Idempotency-Key": str(uuid.uuid4())},
            name="POST /appointments",
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                response.success()
                if random.random() < CANCEL_RATIO:
                    appointment_id = response.json()["id"]
                    self.client.delete(
                        f"/api/v1/appointments/{appointment_id}/", name="DELETE /appointments/{id}"
                    )
            elif response.status_code == 409:
                response.success()  # valid business outcome
            else:
                response.failure(f"{response.status_code}: {response.text[:200]}")


class AvailabilityUser(FastHttpUser):
    fixed_count = int(os.environ.get("AVAILABILITY_USERS", "100"))
    wait_time = constant_throughput(1)

    @task
    def availability(self) -> None:
        self.client.get(
            "/api/v1/availability/",
            params={
                "dealership_id": random_dealership(),
                "service_type_id": random.choice((1, 2, 3)),
                "date": random_day().isoformat(),
            },
            name="GET /availability",
        )
