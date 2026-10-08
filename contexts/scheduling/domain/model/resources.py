"""Schedulable resources of a dealership."""

from dataclasses import dataclass

from contexts.scheduling.domain.model.value_objects import BayId, DealershipId, Skill, TechnicianId


@dataclass(frozen=True)
class ServiceBay:
    id: BayId
    dealership_id: DealershipId
    name: str


@dataclass(frozen=True)
class Technician:
    id: TechnicianId
    dealership_id: DealershipId
    name: str
    skills: frozenset[Skill]

    def is_qualified_for(self, skill: Skill) -> bool:
        return skill in self.skills


@dataclass(frozen=True)
class TechnicianLoad:
    """A free technician together with their workload that local day (input to rule A9)."""

    technician: Technician
    load: int
