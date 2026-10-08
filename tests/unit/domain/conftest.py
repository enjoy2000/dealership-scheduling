from datetime import time
from zoneinfo import ZoneInfo

import pytest

from contexts.scheduling.domain.model.value_objects import OpeningHours


@pytest.fixture
def london_hours() -> OpeningHours:
    return OpeningHours(ZoneInfo("Europe/London"), time(8, 0), time(17, 0))


@pytest.fixture
def new_york_hours() -> OpeningHours:
    return OpeningHours(ZoneInfo("America/New_York"), time(9, 0), time(18, 0))
