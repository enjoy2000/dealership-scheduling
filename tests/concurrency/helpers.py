"""Thread-race helpers: one DB connection per thread, all released by one barrier."""

import threading
import uuid
from collections.abc import Callable
from typing import Any

from django.db import connections

from contexts.catalog.models import Customer, Vehicle
from contexts.scheduling.application.dto import BookAppointmentCommand
from contexts.scheduling.container import Container


def make_customers(count: int) -> list[tuple[int, int]]:
    """(customer_id, vehicle_id) pairs, one vehicle each, so only bays/technicians contend."""
    pairs = []
    for n in range(count):
        customer = Customer.objects.create(name=f"Racer {n}", email=f"racer{n}@example.com")
        vehicle = Vehicle.objects.create(
            customer=customer, vin=f"RACE{n:013d}", make="Make", model="Model", year=2020
        )
        pairs.append((customer.id, vehicle.id))
    return pairs


def run_concurrently(calls: list[Callable[[], Any]]) -> list[Any]:
    """Runs each call in its own thread, all released at once; returns results or errors."""
    barrier = threading.Barrier(len(calls))
    results: list[Any] = [None] * len(calls)

    def worker(index: int, call: Callable[[], Any]) -> None:
        try:
            barrier.wait()
            results[index] = call()
        except Exception as error:
            results[index] = error
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(i, c)) for i, c in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return results


def booking_call(
    container: Container, customer: int, vehicle: int, dealership: int, start: Any
) -> Callable[[], Any]:
    command = BookAppointmentCommand(customer, vehicle, 2, dealership, start)
    return lambda: container.book_appointment(str(uuid.uuid4()), command)


def outcome(result: Any) -> str:
    return "success" if not isinstance(result, Exception) else getattr(result, "code", repr(result))
