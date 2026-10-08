import pytest
from django.core.management import call_command

from contexts.scheduling.container import Container
from tests.unit.application.fakes import FixedClock
from tests.unit.domain.time_helpers import utc

NOW = utc(2026, 11, 1, 12)


@pytest.fixture
def container() -> Container:
    call_command("seed_demo", verbosity=0)
    return Container(clock=FixedClock(NOW))
