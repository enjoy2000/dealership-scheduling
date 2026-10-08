"""Request validation and response shapes. Serializers carry no business rules."""

from datetime import datetime
from typing import Any

from django.utils import timezone
from rest_framework import serializers


class AwareDateTimeField(serializers.DateTimeField):
    """ISO-8601 with an explicit offset or `Z`; naive datetimes are rejected (A6)."""

    def enforce_timezone(self, value: datetime) -> datetime:
        if timezone.is_naive(value):
            raise serializers.ValidationError(
                "Include a timezone offset, e.g. 2026-11-02T09:00:00Z.", code="naive"
            )
        return super().enforce_timezone(value)


class BookAppointmentRequestSerializer(serializers.Serializer[Any]):
    customer_id = serializers.IntegerField(min_value=1)
    vehicle_id = serializers.IntegerField(min_value=1)
    service_type_id = serializers.IntegerField(min_value=1)
    dealership_id = serializers.IntegerField(min_value=1)
    start_time = AwareDateTimeField(
        help_text="UTC, on the 15-minute grid, e.g. 2026-11-02T09:00:00Z"
    )


class NamedRefSerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    name = serializers.CharField()


class VehicleSummarySerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    vin = serializers.CharField()


class ServiceTypeSummarySerializer(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    name = serializers.CharField()
    duration_minutes = serializers.IntegerField()


class AppointmentSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=["CONFIRMED", "CANCELLED"])
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()
    customer = NamedRefSerializer()
    vehicle = VehicleSummarySerializer()
    service_type = ServiceTypeSummarySerializer()
    dealership = NamedRefSerializer()
    technician = NamedRefSerializer()
    service_bay = NamedRefSerializer()


class AvailabilityQuerySerializer(serializers.Serializer[Any]):
    dealership_id = serializers.IntegerField(min_value=1)
    service_type_id = serializers.IntegerField(min_value=1)
    date = serializers.DateField(input_formats=["iso-8601"], help_text="Dealership-local day.")


class AvailableSlotSerializer(serializers.Serializer[Any]):
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()


class AvailabilitySerializer(serializers.Serializer[Any]):
    dealership_id = serializers.IntegerField()
    service_type_id = serializers.IntegerField()
    date = serializers.DateField()
    slots = AvailableSlotSerializer(many=True)


class ProblemSerializer(serializers.Serializer[Any]):
    """RFC 7807 problem details (SPEC §14.2)."""

    type = serializers.CharField()
    title = serializers.CharField()
    status = serializers.IntegerField()
    detail = serializers.CharField()
    code = serializers.CharField()
    correlation_id = serializers.CharField(allow_null=True)


class ValidationProblemSerializer(ProblemSerializer):
    """Adds `errors` (field name to messages). Declared in `get_fields` because a class
    attribute named `errors` would shadow `Serializer.errors`."""

    def get_fields(self) -> dict[str, serializers.Field[Any, Any, Any, Any]]:
        fields = super().get_fields()
        fields["errors"] = serializers.DictField(help_text="Field name to list of messages.")
        return fields
