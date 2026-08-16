"""
Adapters delegating truck_load_planner/logistics/ calls to their
truck_load_planner/engine/ equivalents.

Scope note: only functions with a genuine, behavior-preserving engine
equivalent are adapted here — check_boundary, calculate_total_weight,
and check_weight. The rest of logistics/ has no direct engine
counterpart to delegate to without inventing new engine behavior:

- logistics/volume.py (calculate_occupied_m3, container_volume_m3,
  check_volume) — pure dict-based arithmetic; engine tracks volume
  differently, inside Planner.get_statistics(), not as a standalone
  function operating on this module's placement-dict shape.
- logistics/constraints.py's get_door_status — reports live
  accessible/blocked status for already-placed packages, for the UI.
  engine/access.py answers a different question (can a *new* package
  reach its position through a door, via sweep-path validation during
  insertion) and has no "status for all current placements" function.
- logistics/placement.py's try_place — confirmed dead code (grepped:
  no caller outside this file; session.py's own similarly-named
  LoadPlanningSession.try_place is unrelated and already delegates to
  engine.Planner). Left untouched; it calls check_boundary/check_weight
  from boundary.py/weight.py, which now delegate here transitively.

Both adapted engine functions already work directly with this module's
data after the AABB unification (Section 6.2.2) — check_boundary takes
AABB objects on both sides with byte-for-byte identical logic, so no
conversion is needed. calculate_total_weight/check_weight expect
Placement-like objects (attribute access: `.package`, `._weight_kg`)
rather than this module's plain dicts, so a minimal read-only view
object bridges the two without duplicating the summation logic.
"""

from truck_load_planner.engine.boundary import check_boundary as _engine_check_boundary
from truck_load_planner.engine.weight import (
    calculate_total_weight as _engine_calculate_total_weight,
    check_weight as _engine_check_weight,
)


def check_boundary(package_aabb, container_aabb) -> dict:
    """Adapter: package/container AABBs are already the unified engine
    AABB type, so this is a direct delegate — no conversion needed."""
    return _engine_check_boundary(package_aabb, container_aabb)


class _PlacementWeightView:
    """Minimal read-only adapter exposing what engine.weight functions
    expect (`.package`, `._weight_kg` attribute access) from a legacy
    placement dict (`_weight_kg` key access). `package` is always None
    here so engine's calculate_total_weight falls back to `_weight_kg`
    — matching this module's original behavior of summing `_weight_kg`
    directly rather than trusting a possibly-stale `_package.weight_kg`.
    """
    __slots__ = ("package", "_weight_kg")

    def __init__(self, placement: dict):
        self.package = None
        self._weight_kg = placement.get("_weight_kg", 0)


def calculate_total_weight(placements: list) -> float:
    """Adapter: legacy dict placements → Placement-like view, then delegate."""
    return _engine_calculate_total_weight([_PlacementWeightView(p) for p in placements])


def check_weight(placements: list, payload_kg: float) -> dict:
    """Adapter: legacy dict placements → Placement-like view, then delegate."""
    return _engine_check_weight([_PlacementWeightView(p) for p in placements], payload_kg)
