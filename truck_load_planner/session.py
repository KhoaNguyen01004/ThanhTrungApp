"""
LoadPlanningSession — orchestrates the in-memory state of an editing session.
Refactored to delegate all planning logic to engine.Planner.
"""

from typing import Optional, Callable

from truck_load_planner.models import ContainerConfig, Package as LegacyPackage
from truck_load_planner.engine.planner import Planner
from truck_load_planner.engine.package import Package as EnginePackage
from truck_load_planner.engine.container import Container
from truck_load_planner.engine.placement import Placement
from truck_load_planner.engine.geometry import AABB
from truck_load_planner.engine.validation import validate_placement
from truck_load_planner.engine.weight import calculate_total_weight
from truck_load_planner.engine.statistics import compute_statistics
from truck_load_planner.engine.auto_arrange import AutoArrangeResult
from truck_load_planner.logistics.volume import calculate_occupied_m3, container_volume_m3
from truck_load_planner.logistics.constraints import get_door_status


def _to_engine_pkg(pkg) -> EnginePackage:
    """Convert a legacy Package (from models) to engine Package."""
    if isinstance(pkg, EnginePackage):
        return pkg
    return EnginePackage.from_legacy(pkg)


def _from_legacy_dict(d: dict) -> EnginePackage:
    """Build an engine Package from a legacy dict (underscore keys)."""
    return EnginePackage.from_legacy(d, prefix="_")


def _engine_placement_to_dict(pl: Placement) -> dict:
    """Convert engine Placement to legacy dict format for backward compat."""
    pkg = pl.package
    return {
        "package_id": pl.package_id,
        "x": pl.x, "y": pl.y, "z": pl.z,
        "rotation": pl.rotation,
        "load_sequence": pl.load_sequence,
        "door_used": getattr(pl, "door_used", "rear"),
        "_package": pkg,
        "_name": pkg.name if pkg else "",
        "_weight_kg": pkg.weight_kg if pkg else 0,
        "_length": pkg.length_mm if pkg else 0,
        "_width": pkg.width_mm if pkg else 0,
        "_height": pkg.height_mm if pkg else 0,
        "_aabb": AABB.from_dimensions(
            pl.x, pl.y, pl.z,
            pkg.length_mm if pkg else 0,
            pkg.width_mm if pkg else 0,
            pkg.height_mm if pkg else 0,
            pl.rotation,
        ) if pkg else None,
    }


class LoadPlanningSession:
    """Represents one editing session for a load plan.

    This class wraps engine.Planner and provides backward-compatible
    dict-based interfaces for existing consumers (routes, UI).
    """

    def __init__(self):
        self._planner: Optional[Planner] = None
        self.container: Optional[ContainerConfig] = None
        self.features: list = []
        self.load_plan_id: Optional[int] = None
        self.vehicle_id: Optional[int] = None

    @property
    def placements(self) -> list:
        """Return placements as legacy dicts for backward compatibility."""
        if not self._planner:
            return []
        return [_engine_placement_to_dict(p) for p in self._planner.placements]

    def select_container(self, container: ContainerConfig, features: list = None):
        self.container = container
        self.features = features or []
        engine_container = Container(
            id=container.id,
            name=container.name,
            length=container.cargo_length_mm,
            width=container.cargo_width_mm,
            height=container.cargo_height_mm,
            payload_kg=container.payload_kg,
            features=self.features,
        )
        self._planner = Planner(engine_container, self.features)

    def load_placements(self, placements_data: list):
        """Bulk-load placements from legacy dicts (used by routes)."""
        if not self._planner:
            return
        self._planner.load_legacy_placements(placements_data)

    def try_place(self, package, x: float, y: float, z: float = 0,
                  rotation: int = 0) -> dict:
        if not self._planner:
            return {"accepted": False, "errors": ["No container selected"]}
        ep = _to_engine_pkg(package)
        result = self._planner.place_package(ep, x, y, z, rotation)
        if result.valid:
            pl = self._planner.placements[-1]
            return {"accepted": True, "placement": _engine_placement_to_dict(pl)}
        return {"accepted": False, "errors": result.reasons}

    def move_placement(self, index: int, new_x: float, new_y: float) -> dict:
        if not self._planner:
            return {"accepted": False, "errors": ["No container selected"]}
        if index < 0 or index >= len(self._planner.placements):
            return {"accepted": False, "errors": ["Invalid placement index"]}
        old = self._planner.placements[index]
        result = self._planner.move_package(index, new_x, new_y)
        if result.valid:
            return {"accepted": True, "placement": _engine_placement_to_dict(self._planner.placements[index])}
        return {"accepted": False, "errors": result.reasons}

    def remove_placement(self, index: int):
        if self._planner:
            self._planner.remove_package(index)

    def duplicate_placement(self, index: int) -> dict:
        if not self._planner:
            return {"accepted": False, "errors": ["No container selected"]}
        if index < 0 or index >= len(self._planner.placements):
            return {"accepted": False, "errors": ["Invalid placement index"]}
        p = self._planner.placements[index]
        return self.try_place(
            p.package, p.x + 50, p.y + 50, p.z, p.rotation
        )

    def get_status(self) -> dict:
        if not self._planner or not self.container:
            return {}
        stats = self._planner.get_statistics()
        container_aabb = AABB(
            0, 0, 0,
            self.container.cargo_length_mm,
            self.container.cargo_width_mm,
            self.container.cargo_height_mm,
        )
        engine_placements = self._planner.placements
        doors = get_door_status(
            [_engine_placement_to_dict(p) for p in engine_placements],
            self.features, container_aabb,
        )
        return {
            "weight_kg": stats["weight_used_kg"],
            "payload_kg": self.container.payload_kg,
            "remaining_kg": stats["weight_remaining_kg"],
            "occupied_m3": stats["volume_used_m3"],
            "capacity_m3": round(self.container.cargo_volume_m3, 4),
            "remaining_m3": stats["volume_remaining_m3"],
            "package_count": stats["packages_placed"],
            "doors": doors,
            "load_sequence": [p.load_sequence for p in engine_placements],
        }

    def to_save_data(self, plan_name: str = "", planner_name: str = "",
                     shipment_id: Optional[int] = None,
                     notes: str = "") -> dict:
        if not self._planner:
            return {}
        return {
            "name": plan_name,
            "vehicle_id": self.vehicle_id,
            "shipment_id": shipment_id,
            "planner": planner_name,
            "notes": notes,
            "status": "draft",
            "placements": [
                {
                    "package_id": p.package_id,
                    "x": p.x, "y": p.y, "z": p.z,
                    "rotation": p.rotation,
                    "load_sequence": p.load_sequence,
                }
                for p in self._planner.placements
            ],
        }

    def load_from_data(self, container: ContainerConfig, features: list,
                       placements_data: list, vehicle_id: Optional[int] = None,
                       load_plan_id: Optional[int] = None):
        self.select_container(container, features)
        self.vehicle_id = vehicle_id
        self.load_plan_id = load_plan_id
        self.load_placements(placements_data)

    def auto_arrange(
        self,
        shipment_items: Optional[list] = None,
        packages: Optional[list[EnginePackage]] = None,
        strategy: str = "optimized",
        progress_callback: Optional[Callable] = None,
        cancel_callback: Optional[Callable] = None,
        debug: bool = False,
    ) -> AutoArrangeResult:
        """Run auto-arrange for a set of packages.

        Accepts either a list of shipment items (with quantity expansion)
        or a pre-expanded list of engine Package objects.

        Args:
            shipment_items: List of ShipmentItem-like objects with
                .package (or .package_id) and .quantity attributes.
            packages: Pre-expanded list of EnginePackage objects
                (used when shipment_items is not provided).
            strategy: Registered strategy name.
            progress_callback: Called as fn(placed, total, score).
            cancel_callback: Called as fn() → bool.
            debug: Collect structured debug entries.

        Returns:
            AutoArrangeResult with placed/failed counts and statistics.
        """
        if not self._planner:
            return AutoArrangeResult(
                warnings=["No container selected"],
            )

        pkgs: list[EnginePackage] = []

        if shipment_items:
            for item in shipment_items:
                raw_pkg = getattr(item, "package", None) or getattr(item, "_package", None)
                if raw_pkg is None:
                    continue
                qty = getattr(item, "quantity", 1) or 1
                ep = _to_engine_pkg(raw_pkg)
                for _ in range(qty):
                    pkgs.append(ep)
        elif packages:
            pkgs = list(packages)

        if not pkgs:
            return AutoArrangeResult(warnings=["No packages to arrange"])

        return self._planner.auto_arrange(
            pkgs,
            strategy=strategy,
            progress_callback=progress_callback,
            cancel_callback=cancel_callback,
            debug=debug,
        )

    def reset(self):
        if self._planner:
            self._planner.reset()
        self.container = None
        self.features = []
        self.load_plan_id = None
        self.vehicle_id = None
