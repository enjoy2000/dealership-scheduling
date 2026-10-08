"""Backpressure (SPEC §2.1): per-customer booking limit, per-client availability limit."""

from rest_framework.request import Request
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView


class BookingRateThrottle(SimpleRateThrottle):
    scope = "booking"

    def get_cache_key(self, request: Request, view: APIView) -> str:
        customer_id = request.data.get("customer_id") if hasattr(request.data, "get") else None
        ident = (
            f"customer:{customer_id}" if isinstance(customer_id, int) else self.get_ident(request)
        )
        return self.cache_format % {"scope": self.scope, "ident": ident}


class AvailabilityRateThrottle(SimpleRateThrottle):
    scope = "availability"

    def get_cache_key(self, request: Request, view: APIView) -> str:
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
