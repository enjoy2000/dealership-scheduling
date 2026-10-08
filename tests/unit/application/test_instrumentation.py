import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field

import pytest

from contexts.scheduling.application.decorators import Instrumented
from contexts.scheduling.application.dto import BookAppointmentCommand
from contexts.scheduling.domain.errors import NoCapacityAvailable
from tests.unit.application.conftest import World
from tests.unit.domain.time_helpers import utc


@dataclass
class RecordingTelemetry:
    records: list[tuple[str, str, float]] = field(default_factory=list)
    spans: list[tuple[str, dict[str, object]]] = field(default_factory=list)
    conflicts: int = 0
    retries: list[int] = field(default_factory=list)

    @contextmanager
    def span(self, use_case: str, attributes: Mapping[str, object]) -> Iterator[None]:
        self.spans.append((use_case, dict(attributes)))
        yield

    def record(self, use_case: str, outcome: str, duration_seconds: float) -> None:
        self.records.append((use_case, outcome, duration_seconds))

    def booking_conflict(self) -> None:
        self.conflicts += 1

    def booking_retry(self, attempt: int) -> None:
        self.retries.append(attempt)


COMMAND = BookAppointmentCommand(1, 1, 2, 1, utc(2026, 11, 2, 9))


def test_success_is_recorded_spanned_and_logged(caplog):
    telemetry = RecordingTelemetry()
    instrumented = Instrumented("book_appointment", lambda command: "ok", telemetry=telemetry)

    with caplog.at_level(logging.INFO):
        assert instrumented(COMMAND) == "ok"

    [(use_case, outcome, duration)] = telemetry.records
    assert (use_case, outcome) == ("book_appointment", "success")
    assert duration >= 0
    assert telemetry.spans == [("book_appointment", {"dealership_id": 1})]
    [log] = [r for r in caplog.records if r.getMessage() == "use_case.completed"]
    assert (log.use_case, log.outcome, log.dealership_id) == ("book_appointment", "success", 1)


def test_domain_error_outcome_is_its_code_and_is_reraised():
    telemetry = RecordingTelemetry()

    def fail(command):
        raise NoCapacityAvailable()

    with pytest.raises(NoCapacityAvailable):
        Instrumented("book_appointment", fail, telemetry=telemetry)(COMMAND)

    assert telemetry.records[0][1] == "no_capacity"


def test_unexpected_error_outcome_is_internal_error():
    telemetry = RecordingTelemetry()

    def fail(command):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        Instrumented("cancel_appointment", fail, telemetry=telemetry)(COMMAND)

    assert telemetry.records[0][1] == "internal_error"


def test_finds_the_command_among_positional_arguments():
    telemetry = RecordingTelemetry()
    instrumented = Instrumented("book_appointment", lambda key, command: key, telemetry=telemetry)

    assert instrumented("idem-key", COMMAND) == "idem-key"
    assert telemetry.spans[0][1] == {"dealership_id": 1}


def test_booking_handler_reports_conflicts_and_retries(world: World):
    telemetry = RecordingTelemetry()
    world.book._observer = telemetry
    world.uow.injected_conflicts = [None, None]

    world.book(COMMAND)

    assert telemetry.conflicts == 2
    assert telemetry.retries == [1, 2]
