"""AvailabilityCache on the Django cache (Redis in compose, local memory in tests).

Invalidation is by version: each (dealership, day) has a version number embedded in the
keys of every service type's listing; bumping it orphans them all in one O(1) write.
"""

from datetime import date

from django.core.cache import cache

from contexts.scheduling.application.dto import Availability

_VERSION_TTL_SECONDS = 2 * 24 * 3600


class DjangoAvailabilityCache:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds

    @staticmethod
    def _version_key(dealership_id: int, day: date) -> str:
        return f"availability:version:{dealership_id}:{day.isoformat()}"

    def _key(self, dealership_id: int, service_type_id: int, day: date) -> str:
        version = cache.get(self._version_key(dealership_id, day), 0)
        return f"availability:{dealership_id}:{service_type_id}:{day.isoformat()}:v{version}"

    def get(self, dealership_id: int, service_type_id: int, day: date) -> Availability | None:
        if self._ttl <= 0:
            return None
        value = cache.get(self._key(dealership_id, service_type_id, day))
        return value if isinstance(value, Availability) else None

    def set(self, value: Availability) -> None:
        if self._ttl > 0:
            key = self._key(value.dealership_id, value.service_type_id, value.date)
            cache.set(key, value, timeout=self._ttl)

    def invalidate(self, dealership_id: int, day: date) -> None:
        key = self._version_key(dealership_id, day)
        cache.add(key, 0, timeout=_VERSION_TTL_SECONDS)
        try:
            cache.incr(key)
        except ValueError:  # expired between add and incr
            cache.set(key, 1, timeout=_VERSION_TTL_SECONDS)
