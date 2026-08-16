from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import Optional

from truck_load_planner.engine.package import Package
from truck_load_planner.engine.placement import Placement
from truck_load_planner.engine.container import Container


@dataclass
class PackingResult:
    success: bool = True
    placements: list = field(default_factory=list)
    unplaced_packages: list = field(default_factory=list)
    vehicle_placements: dict = field(default_factory=dict)
    vehicle_containers: dict = field(default_factory=dict)
    statistics: dict = field(default_factory=dict)
    runtime_ms: float = 0.0
    validation_failures: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


@dataclass
class ValidationFailure:
    package_name: str
    check: str
    reason: str


class PackingEngine(ABC):
    @abstractmethod
    def pack(
        self,
        vehicle,
        packages: list[Package],
        options: Optional[dict] = None,
    ) -> PackingResult:
        ...
