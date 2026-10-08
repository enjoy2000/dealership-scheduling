"""Chooses the bay and technician for a requested slot (rule A9)."""

from collections.abc import Sequence
from dataclasses import dataclass

from contexts.scheduling.domain.errors import NoCapacityAvailable
from contexts.scheduling.domain.model.resources import ServiceBay, TechnicianLoad
from contexts.scheduling.domain.model.value_objects import BayId, Skill, TechnicianId


@dataclass(frozen=True)
class Allocation:
    bay_id: BayId
    technician_id: TechnicianId


class ResourceAllocator:
    """Pure and deterministic: least-loaded qualified technician, then lowest id; lowest-id bay.

    Callers pass resources already known to be free for the slot. Qualification is
    re-checked here so an unqualified technician can never be assigned (§7 rule 6).
    """

    def allocate(
        self,
        required_skill: Skill,
        free_bays: Sequence[ServiceBay],
        free_technicians: Sequence[TechnicianLoad],
    ) -> Allocation:
        qualified = [
            candidate
            for candidate in free_technicians
            if candidate.technician.is_qualified_for(required_skill)
        ]
        if not free_bays or not qualified:
            raise NoCapacityAvailable()

        bay = min(free_bays, key=lambda b: b.id)
        chosen = min(qualified, key=lambda c: (c.load, c.technician.id))
        return Allocation(bay_id=bay.id, technician_id=chosen.technician.id)
