from __future__ import annotations

from typing import Optional, Protocol

from .package import Package


def vehicle_capacity(vinfo: dict) -> float:
    vol_mm3 = (
        vinfo.get("cargo_length_mm", 0)
        * vinfo.get("cargo_width_mm", 0)
        * vinfo.get("cargo_height_mm", 0)
    )
    payload = vinfo.get("payload_kg", 0)
    return vol_mm3 * max(payload, 1)


def _cheap_could_fit_all(packages: list[Package], vinfo: dict) -> bool:
    """Fast necessary-condition check, no arrangement attempted.

    Rejects a vehicle outright if total package volume/weight exceeds
    capacity, or any single package's smallest two dimensions can't fit
    the cargo cross-section even after rotation. Used to skip an actual
    (expensive) arrangement attempt against a vehicle that obviously
    can't work.
    """
    cl = vinfo.get("cargo_length_mm", 0)
    cw = vinfo.get("cargo_width_mm", 0)
    ch = vinfo.get("cargo_height_mm", 0)
    payload = vinfo.get("payload_kg", 0)
    if cl <= 0 or cw <= 0 or ch <= 0:
        return False

    total_volume = sum(
        p.length_mm * p.width_mm * p.height_mm for p in packages
    )
    total_weight = sum(p.weight_kg for p in packages)
    if total_volume > cl * cw * ch:
        return False
    if payload and total_weight > payload:
        return False

    for p in packages:
        if p.height_mm > ch:
            return False
        dims_fit_unrotated = p.length_mm <= cl and p.width_mm <= cw
        dims_fit_rotated = p.allow_rotation and p.width_mm <= cl and p.length_mm <= cw
        if not (dims_fit_unrotated or dims_fit_rotated):
            return False
    return True


class VehicleSelectionStrategy(Protocol):
    """Protocol for vehicle-selection strategies.

    ``select_vehicles`` receives the full package list and all available
    vehicle sessions.  It may evaluate candidates and optionally pre-place
    packages into sessions (via ``planner.auto_arrange``).  It returns the
    list of ``(vinfo, session)`` tuples in the order they should be used
    by the placement loop.  If a session already has placements on return,
    the caller treats it as already packed.
    """

    def select_vehicles(
        self,
        packages: list[Package],
        vehicle_sessions: list,
        profile=None,
    ) -> list:
        ...


class SmallestVehicleThatFitsStrategy:
    """Try each vehicle from smallest to largest; return the first that
    packs every package (cheapest single-truck answer). If none fits
    everything alone, fall back to largest-first order for incremental
    multi-vehicle packing — filling big vehicles before small ones uses
    fewer trucks overall than filling small ones first."""

    def select_vehicles(
        self,
        packages: list[Package],
        vehicle_sessions: list,
        profile=None,
    ) -> list:
        initial_states = {
            vinfo["vehicle_id"]: session._planner.export_plan()
            for vinfo, session in vehicle_sessions
        }

        sorted_asc = sorted(
            vehicle_sessions,
            key=lambda vs: vehicle_capacity(vs[0]),
        )

        for vinfo, session in sorted_asc:
            if not _cheap_could_fit_all(packages, vinfo):
                continue
            planner = session._planner
            # Cheap single-pass probe first — the 15-trial "optimized"
            # strategy is too expensive to run per candidate vehicle.
            # Only spend it once, on the vehicle that already proved
            # feasible, to refine the final layout.
            result = planner.auto_arrange(packages, strategy="largest_first")
            if result.failed_packages == 0:
                # Reset to the true empty baseline before refining — calling
                # auto_arrange again on the already-populated planner would
                # place every package a second time on top of the first.
                planner.import_plan(initial_states[vinfo["vehicle_id"]])
                planner.auto_arrange(packages, strategy="optimized")
                for v2, s2 in vehicle_sessions:
                    if v2["vehicle_id"] != vinfo["vehicle_id"]:
                        s2._planner.import_plan(
                            initial_states[v2["vehicle_id"]]
                        )
                return [(vinfo, session)]
            planner.import_plan(initial_states[vinfo["vehicle_id"]])

        for vinfo, session in vehicle_sessions:
            session._planner.import_plan(initial_states[vinfo["vehicle_id"]])
        return sorted(
            vehicle_sessions,
            key=lambda vs: vehicle_capacity(vs[0]),
            reverse=True,
        )


class LargestVehicleFirstStrategy:
    """Original behaviour: largest-capacity vehicles first."""

    def select_vehicles(
        self,
        packages: list[Package],
        vehicle_sessions: list,
        profile=None,
    ) -> list:
        return sorted(
            vehicle_sessions,
            key=lambda vs: vehicle_capacity(vs[0]),
            reverse=True,
        )


class StrategyRegistry:
    _strategies: dict[str, type] = {}

    @classmethod
    def register(cls, name: str, strategy_cls: type) -> None:
        cls._strategies[name] = strategy_cls

    @classmethod
    def get(cls, name: str) -> Optional[type]:
        return cls._strategies.get(name)

    @classmethod
    def list(cls) -> list[str]:
        return list(cls._strategies.keys())


StrategyRegistry.register("smallest_fits", SmallestVehicleThatFitsStrategy)
StrategyRegistry.register("largest_first", LargestVehicleFirstStrategy)
