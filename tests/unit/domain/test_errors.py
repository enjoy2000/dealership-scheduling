import pytest

from contexts.scheduling.domain import errors


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (errors.NoCapacityAvailable, "no_capacity"),
        (errors.VehicleAlreadyBooked, "vehicle_already_booked"),
        (errors.InvalidSlot, "invalid_slot"),
        (errors.OutsideOpeningHours, "outside_opening_hours"),
        (errors.VehicleNotOwnedByCustomer, "vehicle_not_owned"),
        (errors.CancellationNotAllowed, "cancellation_not_allowed"),
        (errors.AppointmentAlreadyCancelled, "appointment_already_cancelled"),
        (errors.ResourceConflict, "resource_conflict"),
    ],
)
def test_domain_errors_carry_stable_codes(error, code):
    instance = error()

    assert isinstance(instance, errors.DomainError)
    assert instance.code == code
    assert str(instance)  # every error has a default human-readable message


def test_domain_error_accepts_custom_message():
    assert str(errors.InvalidSlot("start must be in the future")) == "start must be in the future"
