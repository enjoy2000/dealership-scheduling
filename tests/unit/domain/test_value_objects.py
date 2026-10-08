import pytest

from contexts.scheduling.domain.model.value_objects import AppointmentStatus, Skill, Vin


def test_skill_is_normalised():
    assert Skill(" Brakes ") == Skill("brakes")
    assert str(Skill("oil_service")) == "oil_service"


@pytest.mark.parametrize("raw", ["", "  ", "brakes!", "oil service"])
def test_skill_rejects_invalid_names(raw):
    with pytest.raises(ValueError, match="skill"):
        Skill(raw)


def test_vin_accepts_valid_and_normalises_case():
    vin = Vin("1hgcm82633a004352")

    assert vin.value == "1HGCM82633A004352"
    assert str(vin) == "1HGCM82633A004352"


@pytest.mark.parametrize(
    "raw",
    [
        "1HGCM82633A00435",  # 16 chars
        "1HGCM82633A0043521",  # 18 chars
        "1HGCM82633A00435I",  # I not allowed
        "1HGCM82633A00435O",  # O not allowed
        "1HGCM82633A00435Q",  # Q not allowed
        "1HGCM82633A00435-",
    ],
)
def test_vin_rejects_invalid(raw):
    with pytest.raises(ValueError, match="VIN"):
        Vin(raw)


def test_appointment_status_values_match_the_wire_format():
    assert AppointmentStatus.CONFIRMED.value == "CONFIRMED"
    assert AppointmentStatus.CANCELLED.value == "CANCELLED"
