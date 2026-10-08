from datetime import time, timedelta
from zoneinfo import ZoneInfo

import pytest

from contexts.scheduling.domain.model.references import (
    CustomerRef,
    DealershipCalendar,
    ServiceOffering,
    VehicleRef,
)
from contexts.scheduling.domain.model.value_objects import (
    CustomerId,
    DealershipId,
    OpeningHours,
    ServiceTypeId,
    Skill,
    VehicleId,
    Vin,
)
from contexts.scheduling.infrastructure.catalog_gateway import DjangoCatalogGateway

pytestmark = pytest.mark.usefixtures("seeded")
gateway = DjangoCatalogGateway()


def test_service_offering():
    assert gateway.get_service_offering(ServiceTypeId(2)) == ServiceOffering(
        ServiceTypeId(2), "Brake Service", timedelta(minutes=90), Skill("brakes")
    )


def test_dealership_calendar():
    assert gateway.get_dealership_calendar(DealershipId(2)) == DealershipCalendar(
        DealershipId(2),
        "Uptown Auto",
        OpeningHours(ZoneInfo("America/New_York"), time(9), time(18)),
    )


def test_customer_and_vehicle():
    assert gateway.get_customer(CustomerId(1)) == CustomerRef(CustomerId(1), "Customer One")
    assert gateway.get_vehicle(VehicleId(3)) == VehicleRef(
        VehicleId(3), CustomerId(2), Vin("WVWZZZ1JZXW000001")
    )


def test_unknown_ids_return_none():
    assert gateway.get_service_offering(ServiceTypeId(99)) is None
    assert gateway.get_dealership_calendar(DealershipId(99)) is None
    assert gateway.get_customer(CustomerId(99)) is None
    assert gateway.get_vehicle(VehicleId(99)) is None
