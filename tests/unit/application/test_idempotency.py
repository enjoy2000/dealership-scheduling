import uuid
from dataclasses import dataclass, field
from datetime import timedelta, timezone
from types import TracebackType
from typing import Any, Self

import pytest

from contexts.scheduling.application.decorators import Idempotent, Replayable, fingerprint
from contexts.scheduling.application.dto import (
    AppointmentDetails,
    BookAppointmentCommand,
    NamedRef,
    ServiceTypeSummary,
    VehicleSummary,
)
from contexts.scheduling.application.errors import IdempotencyConflictError
from contexts.scheduling.application.ports import StoredResponse
from contexts.scheduling.application.serialization import (
    appointment_details_from_json,
    appointment_details_to_json,
)
from contexts.scheduling.domain.errors import NoCapacityAvailable
from tests.unit.domain.time_helpers import utc


@dataclass
class FakeTransaction:
    commits: int = 0
    rollbacks: int = 0
    active: bool = False
    _committed: bool = False

    def __enter__(self) -> Self:
        self.active, self._committed = True, False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._committed and exc_type is None:
            self.commits += 1
        else:
            self.rollbacks += 1
        self.active = False

    def commit(self) -> None:
        self._committed = True

    def rollback(self) -> None:
        self._committed = False


@dataclass
class FakeIdempotencyStore:
    transaction: FakeTransaction
    committed: dict[str, StoredResponse] = field(default_factory=dict)
    pending: dict[str, StoredResponse] = field(default_factory=dict)

    def find(self, key: str) -> StoredResponse | None:
        return self.committed.get(key)

    def reserve(self, key: str, request_hash: str) -> None:
        assert self.transaction.active, "reserve must run inside the transaction"
        if key in self.committed:
            raise IdempotencyConflictError()
        self.pending[key] = StoredResponse(request_hash, None, None)

    def complete(self, key: str, status: int, body: dict[str, Any]) -> None:
        assert self.transaction.active
        self.pending[key] = StoredResponse(self.pending[key].request_hash, status, body)


COMMAND = BookAppointmentCommand(1, 1, 2, 1, utc(2026, 11, 2, 9))


class Handler:
    def __init__(self) -> None:
        self.calls = 0
        self.fail_with: Exception | None = None

    def __call__(self, command: BookAppointmentCommand) -> dict[str, Any]:
        self.calls += 1
        if self.fail_with:
            raise self.fail_with
        return {"booked": command.start_time.isoformat(), "n": self.calls}


@pytest.fixture
def parts():
    transaction = FakeTransaction()
    store = FakeIdempotencyStore(transaction)
    handler = Handler()

    def commit_pending() -> None:
        # Mirrors the DB: rows become visible to `find` once the transaction commits.
        store.committed.update(store.pending)
        store.pending.clear()

    def run(key: str, command: BookAppointmentCommand) -> Replayable[dict[str, Any]]:
        before = transaction.commits
        try:
            return idempotent(key, command)
        finally:
            if transaction.commits > before:
                commit_pending()
            else:
                store.pending.clear()

    def identity(value: dict[str, Any]) -> dict[str, Any]:
        return value

    idempotent: Idempotent[BookAppointmentCommand, dict[str, Any]] = Idempotent(
        handler, store=store, transaction=transaction, encode=identity, decode=identity, status=201
    )
    return run, handler, store, transaction


def test_first_call_runs_the_handler_and_stores_the_response(parts):
    run, _, store, transaction = parts

    result = run("key-1", COMMAND)

    assert result == Replayable({"booked": "2026-11-02T09:00:00+00:00", "n": 1}, replayed=False)
    assert transaction.commits == 1
    stored = store.committed["key-1"]
    assert stored.status == 201
    assert stored.body == result.value
    assert stored.request_hash == fingerprint(COMMAND)


def test_same_key_and_payload_replays_without_running_the_handler(parts):
    run, handler, _, _ = parts
    first = run("key-1", COMMAND)

    second = run("key-1", COMMAND)

    assert second == Replayable(first.value, replayed=True)
    assert handler.calls == 1


def test_equivalent_payload_with_another_utc_offset_is_the_same_request(parts):
    run, handler, _, _ = parts
    run("key-1", COMMAND)
    same_instant = BookAppointmentCommand(
        1, 1, 2, 1, utc(2026, 11, 2, 9).astimezone(timezone(timedelta(hours=-5)))
    )

    assert run("key-1", same_instant).replayed
    assert handler.calls == 1


def test_same_key_with_different_payload_is_a_conflict(parts):
    run, handler, _, _ = parts
    run("key-1", COMMAND)

    with pytest.raises(IdempotencyConflictError, match="different"):
        run("key-1", BookAppointmentCommand(1, 1, 2, 1, utc(2026, 11, 2, 10)))
    assert handler.calls == 1


def test_failed_requests_are_not_stored_and_can_be_retried(parts):
    run, handler, store, transaction = parts
    handler.fail_with = NoCapacityAvailable()

    with pytest.raises(NoCapacityAvailable):
        run("key-1", COMMAND)
    assert store.committed == {}
    assert transaction.rollbacks == 1

    handler.fail_with = None
    assert not run("key-1", COMMAND).replayed
    assert handler.calls == 2


def test_key_taken_concurrently_is_a_conflict(parts):
    run, handler, store, _ = parts
    original_find = store.find
    store.find = lambda key: None  # the other request committed after our lookup
    store.committed["key-1"] = StoredResponse(fingerprint(COMMAND), 201, {})

    with pytest.raises(IdempotencyConflictError):
        run("key-1", COMMAND)
    assert handler.calls == 0
    store.find = original_find


def test_fingerprint_is_stable_and_payload_sensitive():
    assert fingerprint(COMMAND) == fingerprint(
        BookAppointmentCommand(1, 1, 2, 1, utc(2026, 11, 2, 9))
    )
    assert fingerprint(COMMAND) != fingerprint(
        BookAppointmentCommand(2, 1, 2, 1, utc(2026, 11, 2, 9))
    )
    assert len(fingerprint(COMMAND)) == 64


def test_appointment_details_codec_round_trips():

    details = AppointmentDetails(
        uuid.uuid4(),
        "CONFIRMED",
        utc(2026, 11, 2, 9),
        utc(2026, 11, 2, 10, 30),
        NamedRef(1, "Customer One"),
        VehicleSummary(1, "1HGCM82633A004352"),
        ServiceTypeSummary(2, "Brake Service", 90),
        NamedRef(1, "Downtown Motors"),
        NamedRef(2, "Bob"),
        NamedRef(1, "Bay 1"),
    )

    assert appointment_details_from_json(appointment_details_to_json(details)) == details
