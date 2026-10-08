import pytest

from contexts.scheduling.domain.errors import NoCapacityAvailable
from contexts.scheduling.domain.model.resources import ServiceBay, Technician, TechnicianLoad
from contexts.scheduling.domain.model.value_objects import BayId, DealershipId, Skill, TechnicianId
from contexts.scheduling.domain.services.resource_allocator import Allocation, ResourceAllocator

DEALERSHIP = DealershipId(1)
BRAKES = Skill("brakes")
allocator = ResourceAllocator()


def bay(bay_id: int) -> ServiceBay:
    return ServiceBay(BayId(bay_id), DEALERSHIP, f"Bay {bay_id}")


def tech(tech_id: int, *skills: str, load: int = 0) -> TechnicianLoad:
    technician = Technician(
        TechnicianId(tech_id), DEALERSHIP, f"Tech {tech_id}", frozenset(Skill(s) for s in skills)
    )
    return TechnicianLoad(technician, load)


def test_allocates_lowest_id_bay_and_only_qualified_technician():
    allocation = allocator.allocate(BRAKES, [bay(3), bay(1), bay(2)], [tech(7, "brakes")])

    assert allocation == Allocation(bay_id=BayId(1), technician_id=TechnicianId(7))


def test_prefers_least_loaded_technician():
    candidates = [tech(1, "brakes", load=2), tech(2, "brakes", load=0), tech(3, "brakes", load=1)]

    allocation = allocator.allocate(BRAKES, [bay(1)], candidates)

    assert allocation.technician_id == TechnicianId(2)


def test_breaks_load_ties_by_lowest_technician_id():
    candidates = [tech(5, "brakes", load=1), tech(4, "brakes", load=1), tech(9, "brakes", load=3)]

    allocation = allocator.allocate(BRAKES, [bay(1)], candidates)

    assert allocation.technician_id == TechnicianId(4)


def test_never_assigns_an_unqualified_technician_even_if_less_loaded():
    candidates = [tech(1, "oil_service", "general", load=0), tech(2, "brakes", load=5)]

    allocation = allocator.allocate(BRAKES, [bay(1)], candidates)

    assert allocation.technician_id == TechnicianId(2)


def test_no_free_bay_means_no_capacity():
    with pytest.raises(NoCapacityAvailable):
        allocator.allocate(BRAKES, [], [tech(1, "brakes")])


def test_no_qualified_technician_means_no_capacity():
    with pytest.raises(NoCapacityAvailable):
        allocator.allocate(BRAKES, [bay(1)], [tech(1, "oil_service")])


def test_no_technicians_means_no_capacity():
    with pytest.raises(NoCapacityAvailable):
        allocator.allocate(BRAKES, [bay(1)], [])


def test_technician_qualification():
    technician = tech(1, "brakes", "general").technician

    assert technician.is_qualified_for(Skill("brakes"))
    assert not technician.is_qualified_for(Skill("oil_service"))
