from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from contexts.scheduling.application.errors import IdempotencyConflictError
from contexts.scheduling.infrastructure.idempotency import DjangoIdempotencyStore
from contexts.scheduling.infrastructure.persistence.models import IdempotencyRecord
from tests.unit.application.fakes import FixedClock
from tests.unit.domain.time_helpers import utc

pytestmark = pytest.mark.django_db
NOW = utc(2026, 11, 1, 12)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


@pytest.fixture
def store(clock: FixedClock) -> DjangoIdempotencyStore:
    return DjangoIdempotencyStore(clock=clock, ttl=timedelta(hours=24))


def test_reserve_complete_find(store):
    store.reserve("k1", "a" * 64)
    assert store.find("k1") is None  # reserved but not completed

    store.complete("k1", 201, {"id": "x"})

    found = store.find("k1")
    assert found is not None
    assert (found.request_hash, found.status, found.body) == ("a" * 64, 201, {"id": "x"})


def test_second_reservation_of_a_key_is_a_conflict(store):
    store.reserve("k1", "a" * 64)

    with pytest.raises(IdempotencyConflictError):
        store.reserve("k1", "a" * 64)


def test_expired_keys_are_ignored_and_can_be_reused(store, clock):
    store.reserve("k1", "a" * 64)
    store.complete("k1", 201, {"id": "old"})
    clock.current = NOW + timedelta(hours=24, seconds=1)

    assert store.find("k1") is None
    store.reserve("k1", "b" * 64)
    store.complete("k1", 201, {"id": "new"})
    found = store.find("k1")
    assert found is not None
    assert found.body == {"id": "new"}
    assert IdempotencyRecord.objects.count() == 1


def test_purge_command_deletes_only_expired_keys():
    now = timezone.now()
    for key, age in (("old-1", 25), ("old-2", 48), ("fresh", 1)):
        IdempotencyRecord.objects.create(
            key=key, request_hash="a" * 64, created_at=now - timedelta(hours=age)
        )

    out = StringIO()
    call_command("purge_idempotency_keys", stdout=out)

    assert list(IdempotencyRecord.objects.values_list("key", flat=True)) == ["fresh"]
    assert "2" in out.getvalue()
