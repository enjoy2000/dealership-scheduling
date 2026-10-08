"""Base type for domain events shared by every bounded context."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    occurred_at: datetime
