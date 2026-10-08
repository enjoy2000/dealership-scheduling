from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest
from django.core.cache import cache
from django.core.management import call_command
from rest_framework.test import APIClient

from contexts.scheduling.container import Container, set_container
from tests.unit.application.fakes import FixedClock
from tests.unit.domain.time_helpers import utc

NOW = utc(2026, 11, 1, 12)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


@pytest.fixture(autouse=True)
def container(clock: FixedClock) -> Iterator[Container]:
    instance = Container(clock=clock, sleep=lambda _: None)
    set_container(instance)
    cache.clear()
    yield instance
    set_container(None)
    cache.clear()


@pytest.fixture
def seeded(db: None) -> None:
    call_command("seed_demo", verbosity=0)


@pytest.fixture
def api() -> APIClient:
    return APIClient()


_keys = iter(range(1, 1_000_000))


def booking(
    *,
    customer: int = 1,
    vehicle: int = 1,
    service_type: int = 2,
    dealership: int = 1,
    start: str = "2026-11-02T09:00:00Z",
) -> dict[str, Any]:
    return {
        "customer_id": customer,
        "vehicle_id": vehicle,
        "service_type_id": service_type,
        "dealership_id": dealership,
        "start_time": start,
    }


def post_booking(api: APIClient, body: dict[str, Any], key: str | None = None) -> Any:
    headers = {"Idempotency-Key": key or f"test-key-{next(_keys)}"}
    return api.post("/api/v1/appointments/", body, format="json", headers=headers)


def iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")
