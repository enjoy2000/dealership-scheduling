"""Decision D2, demonstrated: without the exclusion constraints, the application's own
pre-checks race and the same bay/technician is booked many times over. With them (the
other tests in this package), exactly one request wins."""

import pytest
from django.db import connection

from contexts.scheduling.infrastructure.persistence.models import AppointmentRecord
from tests.concurrency.helpers import booking_call, make_customers, run_concurrently
from tests.unit.domain.time_helpers import utc

pytestmark = pytest.mark.django_db(transaction=True)

EXCLUSION_CONSTRAINTS = ("no_bay_overlap", "no_technician_overlap", "no_vehicle_overlap")


def test_without_exclusion_constraints_the_application_alone_double_books(container):
    constraints = [
        c for c in AppointmentRecord._meta.constraints if c.name in EXCLUSION_CONSTRAINTS
    ]
    with connection.schema_editor() as editor:
        for constraint in constraints:
            editor.remove_constraint(AppointmentRecord, constraint)
    try:
        racers = make_customers(20)
        start = utc(2026, 11, 2, 14)  # Uptown Auto: one bay, one technician
        run_concurrently([booking_call(container, c, v, 2, start) for c, v in racers])

        double_booked = AppointmentRecord.objects.filter(status="CONFIRMED").count()
        assert double_booked > 1, "expected the unguarded race to double-book"
    finally:
        AppointmentRecord.objects.all().delete()
        with connection.schema_editor() as editor:
            for constraint in constraints:
                editor.add_constraint(AppointmentRecord, constraint)
