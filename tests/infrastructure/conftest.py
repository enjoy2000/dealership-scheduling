import uuid
from datetime import datetime, timedelta

import pytest
from django.core.management import call_command

from contexts.scheduling.domain.model.value_objects import TimeSlot
from contexts.scheduling.infrastructure.persistence.models import AppointmentRecord
from contexts.scheduling.infrastructure.persistence.ranges import to_range


@pytest.fixture
def seeded(db: None) -> None:
    call_command("seed_demo", verbosity=0)


def insert_appointment(
    *,
    start: datetime,
    minutes: int = 90,
    bay: int = 1,
    technician: int = 2,
    vehicle: int = 1,
    customer: int = 1,
    dealership: int = 1,
    service_type: int = 2,
    status: str = "CONFIRMED",
    cancelled_at: datetime | None = None,
) -> AppointmentRecord:
    """Raw ORM insert that bypasses all application code."""
    return AppointmentRecord.objects.create(
        id=uuid.uuid4(),
        customer_id=customer,
        vehicle_id=vehicle,
        dealership_id=dealership,
        service_type_id=service_type,
        service_bay_id=bay,
        technician_id=technician,
        time_range=to_range(TimeSlot.starting_at(start, timedelta(minutes=minutes))),
        status=status,
        created_at=start - timedelta(days=1),
        cancelled_at=cancelled_at,
    )
