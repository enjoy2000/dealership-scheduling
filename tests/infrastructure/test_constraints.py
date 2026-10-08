"""The DB is the final guard for resource exclusivity (D2), independent of app code."""

import pytest
from django.db import IntegrityError, transaction

from tests.infrastructure.conftest import insert_appointment
from tests.unit.domain.time_helpers import utc

pytestmark = pytest.mark.usefixtures("seeded")

NINE = utc(2026, 11, 2, 9)


@pytest.mark.parametrize(
    ("second", "constraint"),
    [
        ({"bay": 1, "technician": 3, "vehicle": 2}, "no_bay_overlap"),
        ({"bay": 2, "technician": 2, "vehicle": 2}, "no_technician_overlap"),
        ({"bay": 2, "technician": 3, "vehicle": 1}, "no_vehicle_overlap"),
    ],
)
def test_overlapping_confirmed_rows_are_rejected(second, constraint):
    insert_appointment(start=NINE, bay=1, technician=2, vehicle=1)

    with pytest.raises(IntegrityError, match=constraint), transaction.atomic():
        insert_appointment(start=utc(2026, 11, 2, 10, 29), **second)


def test_back_to_back_rows_are_allowed():
    insert_appointment(start=NINE)
    insert_appointment(start=utc(2026, 11, 2, 10, 30))


def test_cancelled_rows_do_not_block_resources():
    insert_appointment(start=NINE, status="CANCELLED", cancelled_at=utc(2026, 11, 1, 9))
    insert_appointment(start=NINE)


def test_cancelled_at_must_match_status():
    with pytest.raises(IntegrityError, match="cancelled_at_matches_status"), transaction.atomic():
        insert_appointment(start=NINE, status="CANCELLED", cancelled_at=None)
