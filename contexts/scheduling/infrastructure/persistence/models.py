"""Scheduling persistence model (D3: separate from the domain, joined by mappers).

Catalog tables are referenced by "app_label.Model" strings, so no Catalog code is imported.
"""

from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.contrib.postgres.indexes import GistIndex
from django.db import models

CONFIRMED = "CONFIRMED"
CANCELLED = "CANCELLED"


class ServiceBayRecord(models.Model):
    dealership = models.ForeignKey("catalog.Dealership", on_delete=models.PROTECT, related_name="+")
    name = models.CharField(max_length=100)

    class Meta:
        db_table = "scheduling_service_bay"
        verbose_name = "service bay"
        constraints = (
            models.UniqueConstraint(fields=["dealership", "name"], name="unique_bay_name"),
        )

    def __str__(self) -> str:
        return self.name


class TechnicianRecord(models.Model):
    dealership = models.ForeignKey("catalog.Dealership", on_delete=models.PROTECT, related_name="+")
    name = models.CharField(max_length=200)

    class Meta:
        db_table = "scheduling_technician"
        verbose_name = "technician"

    def __str__(self) -> str:
        return self.name


class TechnicianSkillRecord(models.Model):
    technician = models.ForeignKey(
        TechnicianRecord, on_delete=models.CASCADE, related_name="skills"
    )
    skill = models.CharField(max_length=64)

    class Meta:
        db_table = "scheduling_technician_skill"
        verbose_name = "technician skill"
        constraints = (
            models.UniqueConstraint(fields=["technician", "skill"], name="unique_technician_skill"),
        )

    def __str__(self) -> str:
        return self.skill


class AppointmentRecord(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = CONFIRMED
        CANCELLED = CANCELLED

    id = models.UUIDField(primary_key=True)
    customer = models.ForeignKey("catalog.Customer", on_delete=models.PROTECT, related_name="+")
    vehicle = models.ForeignKey("catalog.Vehicle", on_delete=models.PROTECT, related_name="+")
    dealership = models.ForeignKey("catalog.Dealership", on_delete=models.PROTECT, related_name="+")
    service_type = models.ForeignKey(
        "catalog.ServiceType", on_delete=models.PROTECT, related_name="+"
    )
    service_bay = models.ForeignKey(
        ServiceBayRecord, on_delete=models.PROTECT, related_name="appointments"
    )
    technician = models.ForeignKey(
        TechnicianRecord, on_delete=models.PROTECT, related_name="appointments"
    )
    time_range = DateTimeRangeField(default_bounds="[)")
    status = models.CharField(max_length=10, choices=Status.choices)
    created_at = models.DateTimeField()
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "scheduling_appointment"
        verbose_name = "appointment"
        constraints = (
            ExclusionConstraint(
                name="no_bay_overlap",
                expressions=[
                    ("service_bay", RangeOperators.EQUAL),
                    ("time_range", RangeOperators.OVERLAPS),
                ],
                condition=models.Q(status=CONFIRMED),
            ),
            ExclusionConstraint(
                name="no_technician_overlap",
                expressions=[
                    ("technician", RangeOperators.EQUAL),
                    ("time_range", RangeOperators.OVERLAPS),
                ],
                condition=models.Q(status=CONFIRMED),
            ),
            ExclusionConstraint(
                name="no_vehicle_overlap",
                expressions=[
                    ("vehicle", RangeOperators.EQUAL),
                    ("time_range", RangeOperators.OVERLAPS),
                ],
                condition=models.Q(status=CONFIRMED),
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status=CONFIRMED, cancelled_at__isnull=True)
                    | models.Q(status=CANCELLED, cancelled_at__isnull=False)
                ),
                name="cancelled_at_matches_status",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    time_range__isempty=False,
                    time_range__lower_inc=True,
                    time_range__upper_inc=False,
                ),
                name="time_range_half_open_non_empty",
            ),
        )
        indexes = (
            GistIndex(fields=["dealership", "time_range"], name="appt_dealership_range_gist"),
        )

    def __str__(self) -> str:
        return f"{self.id} ({self.status})"
