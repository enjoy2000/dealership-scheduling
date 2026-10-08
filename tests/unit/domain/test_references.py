from datetime import timedelta

import pytest

from contexts.scheduling.domain.errors import VehicleNotOwnedByCustomer
from contexts.scheduling.domain.model.references import ServiceOffering, VehicleRef
from contexts.scheduling.domain.model.value_objects import (
    CustomerId,
    ServiceTypeId,
    Skill,
    VehicleId,
    Vin,
)

VEHICLE = VehicleRef(VehicleId(1), CustomerId(1), Vin("1HGCM82633A004352"))


def test_vehicle_owned_by_customer_passes():
    VEHICLE.ensure_owned_by(CustomerId(1))


def test_vehicle_of_another_customer_is_rejected():
    with pytest.raises(VehicleNotOwnedByCustomer):
        VEHICLE.ensure_owned_by(CustomerId(2))


def test_service_offering_requires_positive_duration():
    with pytest.raises(ValueError, match="duration"):
        ServiceOffering(ServiceTypeId(1), "Oil Change", timedelta(0), Skill("oil_service"))


def test_service_offering_duration_in_minutes():
    offering = ServiceOffering(
        ServiceTypeId(2), "Brake Service", timedelta(minutes=90), Skill("brakes")
    )

    assert offering.duration_minutes == 90
