"""In-process domain event dispatch, deferred until the surrounding transaction commits.

A transactional outbox is the documented next step (SPEC §4.3) for durable delivery.
"""

import logging
from collections import defaultdict
from collections.abc import Callable, Sequence

from django.db import transaction

from shared_kernel.events import DomainEvent

logger = logging.getLogger(__name__)

Subscriber = Callable[[DomainEvent], None]


class InProcessEventPublisher:
    def __init__(self) -> None:
        self._subscribers: dict[type[DomainEvent], list[Subscriber]] = defaultdict(list)

    def subscribe(self, event_type: type[DomainEvent], subscriber: Subscriber) -> None:
        self._subscribers[event_type].append(subscriber)

    def publish(self, events: Sequence[DomainEvent]) -> None:
        if events:
            # Runs immediately when no transaction is open; otherwise after it commits.
            transaction.on_commit(lambda: self._dispatch(events))

    def _dispatch(self, events: Sequence[DomainEvent]) -> None:
        for event in events:
            for subscriber in self._subscribers[type(event)]:
                try:
                    subscriber(event)
                except Exception:
                    # A failing side effect must not turn a committed booking into an error.
                    logger.exception(
                        "event subscriber failed", extra={"event": type(event).__name__}
                    )
