"""Shared request generation for the load tests (mirrors the seed_load id formulas)."""

import os
import random
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DEALERSHIPS = int(os.environ.get("LOAD_DEALERSHIPS", "50"))
CUSTOMERS = int(os.environ.get("LOAD_CUSTOMERS", "5000"))
DAYS_AHEAD = (int(os.environ.get("LOAD_DAY_MIN", "21")), int(os.environ.get("LOAD_DAY_MAX", "80")))
LONDON = ZoneInfo("Europe/London")
DURATIONS = {1: 30, 2: 90, 3: 120}  # service_type_id -> minutes (seed_demo)


def random_dealership() -> int:
    return 1000 + random.randint(1, DEALERSHIPS)


def random_day() -> date:
    return date.today() + timedelta(days=random.randint(*DAYS_AHEAD))


def random_start(service_type: int, day: date) -> str:
    """A 15-minute-grid start that fits 08:00-18:00 London time on `day`."""
    last_start = 18 * 60 - DURATIONS[service_type]
    minutes = random.randrange(8 * 60, last_start + 1, 15)
    local = datetime.combine(day, time(minutes // 60, minutes % 60), tzinfo=LONDON)
    return local.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def booking_payload() -> dict[str, object]:
    customer = 100_000 + random.randint(1, CUSTOMERS)
    service_type = random.choice((1, 2, 3))
    return {
        "customer_id": customer,
        "vehicle_id": customer,  # seed_load: vehicle id == customer id
        "service_type_id": service_type,
        "dealership_id": random_dealership(),
        "start_time": random_start(service_type, random_day()),
    }
