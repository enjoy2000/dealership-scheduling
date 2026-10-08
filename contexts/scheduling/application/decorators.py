"""Cross-cutting behaviour wrapped around use cases in the composition root (§4.4)."""

import dataclasses
import hashlib
import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from contexts.scheduling.application.errors import IdempotencyConflictError
from contexts.scheduling.application.ports import (
    IdempotencyStore,
    StoredResponse,
    Transaction,
    UseCaseTelemetry,
)

logger = logging.getLogger("scheduling.use_cases")


@dataclass(frozen=True)
class Replayable[R]:
    value: R
    replayed: bool


def _canonical(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, date | uuid.UUID):
        return str(value)
    raise TypeError(f"Cannot fingerprint {type(value).__name__}")


def fingerprint(command: Any) -> str:
    """SHA-256 of the canonical command, so equivalent payloads (e.g. the same instant
    written with another UTC offset) are the same request."""
    payload = json.dumps(
        dataclasses.asdict(command), default=_canonical, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class Idempotent[C, R]:
    """Runs `handler` at most once per key (SPEC §14.5).

    The key is reserved, the use case runs and the response is stored in one transaction:
    a concurrent duplicate blocks on the key and then fails with a conflict; a failed
    request stores nothing, so the client can retry it with the same key.
    """

    def __init__(
        self,
        handler: Callable[[C], R],
        *,
        store: IdempotencyStore,
        transaction: Transaction,
        encode: Callable[[R], dict[str, Any]],
        decode: Callable[[dict[str, Any]], R],
        status: int,
    ) -> None:
        self._handler = handler
        self._store = store
        self._transaction = transaction
        self._encode = encode
        self._decode = decode
        self._status = status

    def __call__(self, key: str, command: C) -> Replayable[R]:
        request_hash = fingerprint(command)
        existing = self._store.find(key)
        if existing is not None:
            return self._replay(existing, request_hash)

        with self._transaction as transaction:
            self._store.reserve(key, request_hash)
            result = self._handler(command)
            self._store.complete(key, self._status, self._encode(result))
            transaction.commit()
        return Replayable(result, replayed=False)

    def _replay(self, stored: StoredResponse, request_hash: str) -> Replayable[R]:
        if stored.request_hash != request_hash or stored.body is None:
            raise IdempotencyConflictError(
                "The Idempotency-Key was already used with a different payload."
            )
        return Replayable(self._decode(stored.body), replayed=True)


def _attributes(args: tuple[Any, ...]) -> dict[str, object]:
    for arg in args:
        dealership_id = getattr(arg, "dealership_id", None)
        if isinstance(dealership_id, int):
            return {"dealership_id": dealership_id}
    return {}


def _outcome(error: Exception) -> str:
    code = getattr(error, "code", None)
    return code if isinstance(code, str) else "internal_error"


class Instrumented[**P, R]:
    """`logged_and_measured` (§4.4): a span, outcome/duration metrics and one structured
    log line per use-case call. Outcome is `success` or the error's stable code."""

    def __init__(
        self,
        use_case: str,
        handler: Callable[P, R],
        *,
        telemetry: UseCaseTelemetry,
        timer: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._use_case = use_case
        self._handler = handler
        self._telemetry = telemetry
        self._timer = timer

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        attributes = _attributes(args)
        with self._telemetry.span(self._use_case, attributes):
            started = self._timer()
            outcome = "success"
            try:
                return self._handler(*args, **kwargs)
            except Exception as error:
                outcome = _outcome(error)
                raise
            finally:
                duration = self._timer() - started
                self._telemetry.record(self._use_case, outcome, duration)
                logger.log(
                    logging.ERROR if outcome == "internal_error" else logging.INFO,
                    "use_case.completed",
                    extra={
                        "use_case": self._use_case,
                        "outcome": outcome,
                        "duration_ms": round(duration * 1000, 2),
                        **attributes,
                    },
                )
