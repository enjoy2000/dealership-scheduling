"""Catalog (supporting subdomain, A16): plain Django models managed via the admin."""

import zoneinfo

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models

skill_validator = RegexValidator(r"^[a-z][a-z0-9_]*$", "Use lowercase letters, digits and _.")
vin_validator = RegexValidator(r"^[A-HJ-NPR-Z0-9]{17}$", "17 characters; I, O and Q not allowed.")


def validate_timezone(value: str) -> None:
    if value not in zoneinfo.available_timezones():
        raise ValidationError(f"{value!r} is not an IANA timezone.")


class Dealership(models.Model):
    name = models.CharField(max_length=200)
    timezone = models.CharField(max_length=64, validators=[validate_timezone])
    open_time = models.TimeField()
    close_time = models.TimeField()

    class Meta:
        constraints = (
            models.CheckConstraint(
                condition=models.Q(close_time__gt=models.F("open_time")),
                name="dealership_closes_after_opening",
            ),
        )

    def __str__(self) -> str:
        return self.name


class ServiceType(models.Model):
    name = models.CharField(max_length=200)
    duration_minutes = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    required_skill = models.CharField(max_length=64, validators=[skill_validator])

    class Meta:
        constraints = (
            models.CheckConstraint(
                condition=models.Q(duration_minutes__gt=0), name="service_type_positive_duration"
            ),
        )

    def __str__(self) -> str:
        return self.name


class Customer(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)

    def __str__(self) -> str:
        return self.name


class Vehicle(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="vehicles")
    vin = models.CharField(max_length=17, unique=True, validators=[vin_validator])
    make = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    year = models.PositiveSmallIntegerField()

    def __str__(self) -> str:
        return self.vin
