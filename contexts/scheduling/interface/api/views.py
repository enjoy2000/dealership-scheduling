"""Thin DRF views: validate input, call a use case from the container, shape the output."""

import uuid

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.views import APIView

from contexts.scheduling.application.dto import (
    BookAppointmentCommand,
    CancelAppointmentCommand,
    GetAppointmentQuery,
    ListAvailabilityQuery,
)
from contexts.scheduling.interface.api.dependencies import use_cases
from contexts.scheduling.interface.api.serializers import (
    AppointmentSerializer,
    AvailabilityQuerySerializer,
    AvailabilitySerializer,
    BookAppointmentRequestSerializer,
    ProblemSerializer,
    ValidationProblemSerializer,
)
from contexts.scheduling.interface.api.throttles import (
    AvailabilityRateThrottle,
    BookingRateThrottle,
)

IDEMPOTENCY_HEADER = "Idempotency-Key"
MAX_IDEMPOTENCY_KEY_LENGTH = 255


def _problem(description: str) -> OpenApiResponse:
    return OpenApiResponse(ProblemSerializer, description=description)


def idempotency_key(request: Request) -> str:
    key = request.headers.get(IDEMPOTENCY_HEADER, "").strip()
    if not key or len(key) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise ValidationError(
            {IDEMPOTENCY_HEADER: [f"Required header, 1-{MAX_IDEMPOTENCY_KEY_LENGTH} characters."]}
        )
    return key


class AppointmentCollectionView(APIView):
    throttle_classes = (BookingRateThrottle,)

    @extend_schema(
        operation_id="book_appointment",
        summary="Book an appointment",
        description=(
            "Confirms the appointment only if a service bay and a qualified technician are "
            "both free for the whole service duration. Idempotent via `Idempotency-Key`."
        ),
        request=BookAppointmentRequestSerializer,
        parameters=[
            OpenApiParameter(
                IDEMPOTENCY_HEADER,
                OpenApiTypes.STR,
                OpenApiParameter.HEADER,
                required=True,
                description="Client-generated key (e.g. a UUID). Retained for 24 hours.",
            ),
            OpenApiParameter(
                "Location",
                OpenApiTypes.URI,
                OpenApiParameter.HEADER,
                response=[201],
                description="URL of the new appointment.",
            ),
            OpenApiParameter(
                "Idempotent-Replayed",
                OpenApiTypes.STR,
                OpenApiParameter.HEADER,
                response=[201],
                description="`true` when this is a replay of an earlier identical request.",
            ),
        ],
        responses={
            201: OpenApiResponse(AppointmentSerializer, description="Appointment confirmed."),
            400: OpenApiResponse(ValidationProblemSerializer, description="Malformed request."),
            404: _problem("Unknown customer, vehicle, service type or dealership."),
            409: _problem("No capacity, vehicle already booked, or idempotency conflict."),
            422: _problem("Invalid slot, outside opening hours, or vehicle not owned."),
            429: _problem("Too many requests."),
        },
        tags=["appointments"],
    )
    def post(self, request: Request) -> Response:
        key = idempotency_key(request)
        serializer = BookAppointmentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        command = BookAppointmentCommand(**serializer.validated_data)
        result = use_cases().book_appointment(key, command)
        details = result.value
        headers = {"Location": reverse("appointment-detail", args=[details.id], request=request)}
        if result.replayed:
            headers["Idempotent-Replayed"] = "true"
        return Response(
            AppointmentSerializer(details).data, status=status.HTTP_201_CREATED, headers=headers
        )


class AppointmentDetailView(APIView):
    @extend_schema(
        operation_id="get_appointment",
        summary="Fetch an appointment",
        responses={200: AppointmentSerializer, 404: _problem("Unknown appointment.")},
        tags=["appointments"],
    )
    def get(self, request: Request, id: uuid.UUID) -> Response:
        details = use_cases().get_appointment(GetAppointmentQuery(id))
        return Response(AppointmentSerializer(details).data)

    @extend_schema(
        operation_id="cancel_appointment",
        summary="Cancel an appointment",
        description=(
            "Frees the bay and technician. Allowed only before the start time. Idempotent: "
            "cancelling an already cancelled appointment also returns 204."
        ),
        responses={
            204: OpenApiResponse(description="Cancelled (or already cancelled)."),
            404: _problem("Unknown appointment."),
            422: _problem("The appointment has already started."),
        },
        tags=["appointments"],
    )
    def delete(self, request: Request, id: uuid.UUID) -> Response:
        use_cases().cancel_appointment(CancelAppointmentCommand(id))
        return Response(status=status.HTTP_204_NO_CONTENT)


class AvailabilityView(APIView):
    throttle_classes = (AvailabilityRateThrottle,)

    @extend_schema(
        operation_id="list_availability",
        summary="List bookable start times",
        description=(
            "Start times on the dealership-local `date` for which a bay and a qualified "
            "technician are free for the whole service. May be up to "
            "AVAILABILITY_CACHE_TTL_SECONDS stale; booking always re-validates."
        ),
        parameters=[AvailabilityQuerySerializer],
        responses={
            200: AvailabilitySerializer,
            400: OpenApiResponse(ValidationProblemSerializer, description="Malformed query."),
            404: _problem("Unknown dealership or service type."),
            429: _problem("Too many requests."),
        },
        tags=["availability"],
    )
    def get(self, request: Request) -> Response:
        params = AvailabilityQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        result = use_cases().list_availability(ListAvailabilityQuery(**params.validated_data))
        return Response(AvailabilitySerializer(result).data)
