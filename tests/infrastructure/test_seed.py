import pytest
from django.core.management import call_command

from contexts.catalog.models import Customer, Dealership, ServiceType, Vehicle
from contexts.scheduling.infrastructure.persistence.models import ServiceBayRecord, TechnicianRecord


@pytest.mark.django_db
def test_seed_demo_creates_the_spec_reference_data():
    call_command("seed_demo", verbosity=0)

    assert list(Dealership.objects.values_list("id", "name", "timezone").order_by("id")) == [
        (1, "Downtown Motors", "Europe/London"),
        (2, "Uptown Auto", "America/New_York"),
    ]
    assert list(
        ServiceType.objects.values_list(
            "id", "name", "duration_minutes", "required_skill"
        ).order_by("id")
    ) == [
        (1, "Oil Change", 30, "oil_service"),
        (2, "Brake Service", 90, "brakes"),
        (3, "Full Service", 120, "general"),
    ]
    assert Customer.objects.count() == 3
    assert list(Vehicle.objects.values_list("id", "customer_id", "vin").order_by("id")) == [
        (1, 1, "1HGCM82633A004352"),
        (2, 1, "5YJ3E1EA7KF317000"),
        (3, 2, "WVWZZZ1JZXW000001"),
        (4, 3, "3VWFE21C04M000001"),
    ]
    assert list(
        ServiceBayRecord.objects.values_list("id", "dealership_id", "name").order_by("id")
    ) == [(1, 1, "Bay 1"), (2, 1, "Bay 2"), (3, 1, "Bay 3"), (4, 2, "Bay 1")]
    skills = {
        t.name: sorted(s.skill for s in t.skills.all())
        for t in TechnicianRecord.objects.prefetch_related("skills")
    }
    assert skills == {
        "Alice": ["general", "oil_service"],
        "Bob": ["brakes", "general"],
        "Chen": ["brakes", "oil_service"],
        "Dana": ["brakes", "general", "oil_service"],
    }


@pytest.mark.django_db
def test_seed_demo_is_idempotent_and_resets_sequences():
    call_command("seed_demo", verbosity=0)
    call_command("seed_demo", verbosity=0)

    assert Dealership.objects.count() == 2
    assert TechnicianRecord.objects.count() == 4
    new = Dealership.objects.create(
        name="New", timezone="UTC", open_time="08:00", close_time="17:00"
    )
    assert new.id == 3
