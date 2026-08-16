"""
PlanningState — holds all mutable state for a single loading session.
Manages placements, sequence counter, Extreme Point Set, and a
Uniform Grid spatial index for fast collision/sweep queries.
"""

from typing import Optional, Callable

from .package import Package
from .placement import Placement
from .container import Container
from .geometry import AABB
from .spatial import UniformGrid
from .trace_mutations import M


class PlanningState:
    """Encapsulates placements, sequence counter, extreme points, and
    a spatial index for fast proximity queries.

    ``append_placement`` updates extreme points incrementally (O(1) average)
    and inserts into the spatial grid (O(cell_count) average).
    ``pop_placement`` and ``insert_placement`` rebuild from scratch (O(N)),
    which is acceptable since those are user-initiated operations.
    ``get_candidate_points`` returns the extreme point set directly
    — no regeneration at call time.
    """

    def __init__(self, container: Container, features: Optional[list] = None):
        self.container = container
        self.features = features or []
        self._placements: list[Placement] = []
        self._sequence_counter: int = 0
        self._extreme_points: set[tuple[float, float, float]] = {(0, 0, 0)}
        # Auto-tuned cell size: ~1/10 of smallest container dimension
        cs = min(container.length, container.width, container.height) / 10 if container else 500
        cs = max(200.0, min(cs, 1000.0))
        self._spatial = UniformGrid(cell_size=cs)

    # ── Public read access ─────────────────────────────────────────────

    @property
    def placements(self) -> list[Placement]:
        return self._placements

    @property
    def sequence_counter(self) -> int:
        return self._sequence_counter

    @sequence_counter.setter
    def sequence_counter(self, value: int) -> None:
        self._sequence_counter = value

    # ── Mutations ──────────────────────────────────────────────────────

    def append_placement(
        self,
        package: Package,
        x: float,
        y: float,
        z: float,
        rotation: int = 0,
        door_used: str = "rear",
    ) -> Placement:
        """Append a new placement and update extreme points + spatial index."""
        self._sequence_counter += 1
        placement = Placement(
            package_id=package.id or 0,
            x=x, y=y, z=z,
            rotation=rotation,
            load_sequence=self._sequence_counter,
            package=package,
            door_used=door_used,
        )
        h_clr = getattr(package, 'horizontal_clearance_mm', 10.0)
        v_clr = getattr(package, 'vertical_clearance_mm', 0.0)
        aabb = AABB.from_dimensions(
            x, y, z,
            package.length_mm, package.width_mm, package.height_mm,
            rotation, clearance_xy=h_clr, clearance_z=v_clr,
        )
        self._placements.append(placement)
        self._spatial.insert(placement, aabb)
        self._extreme_points_add(package, x, y, z, rotation)
        M.log_insert("PlanningState.append_placement", placement, "new placement")
        return placement

    def pop_placement(self, index: int) -> Optional[Placement]:
        """Remove the placement at *index* and rebuild extreme points + grid."""
        if 0 <= index < len(self._placements):
            pl = self._placements.pop(index)
            M.log_remove("PlanningState.pop_placement", pl, f"idx={index}")
            self._spatial.remove(pl)
            self._rebuild_extreme_points()
            return pl
        return None

    def insert_placement(
        self,
        index: int,
        package: Package,
        x: float,
        y: float,
        z: float,
        rotation: int,
        load_sequence: Optional[int] = None,
    ) -> Placement:
        """Insert a placement at *index* and rebuild extreme points + grid."""
        placement = Placement(
            package_id=package.id or 0,
            x=x, y=y, z=z,
            rotation=rotation,
            load_sequence=load_sequence,
            package=package,
        )
        h_clr = getattr(package, 'horizontal_clearance_mm', 10.0)
        v_clr = getattr(package, 'vertical_clearance_mm', 0.0)
        aabb = AABB.from_dimensions(
            x, y, z,
            package.length_mm, package.width_mm, package.height_mm,
            rotation, clearance_xy=h_clr, clearance_z=v_clr,
        )
        self._placements.insert(index, placement)
        self._spatial.insert(placement, aabb)
        self._rebuild_extreme_points()
        M.log_insert("PlanningState.insert_placement", placement, f"idx={index}")
        return placement

    # ── Candidate points (extreme points) ──────────────────────────────

    def get_candidate_points(self) -> list[tuple[float, float, float]]:
        """Return extreme points sorted by z, x, y — no regeneration."""
        return sorted(self._extreme_points, key=lambda p: (p[2], p[0], p[1]))

    # ── Bulk import (bypasses sequence_counter auto-increment) ─────────

    def import_placements(self, placement_dicts: list[dict]) -> None:
        """Replace all placements from saved data and rebuild indices."""
        old_ids = {id(pl): pl for pl in self._placements}
        self._placements.clear()
        self._spatial.clear()
        self._sequence_counter = 0
        for pd in placement_dicts:
            pkg = None
            if "_package" in pd:
                pkg = Package.from_dict(pd["_package"])
            elif "package" in pd:
                pkg = Package.from_dict(pd["package"])
            pl = Placement(
                package_id=pd["package_id"],
                x=pd.get("x", 0), y=pd.get("y", 0), z=pd.get("z", 0),
                rotation=pd.get("rotation", 0),
                load_sequence=pd.get("load_sequence"),
                package=pkg,
            )
            self._placements.append(pl)
            M.log_insert("PlanningState.import_placements", pl, "from snapshot")
            if pkg:
                h_clr = getattr(pkg, 'horizontal_clearance_mm', 10.0)
                v_clr = getattr(pkg, 'vertical_clearance_mm', 0.0)
                aabb = AABB.from_dimensions(
                    pl.x, pl.y, pl.z,
                    pkg.length_mm, pkg.width_mm, pkg.height_mm,
                    pl.rotation, clearance_xy=h_clr, clearance_z=v_clr,
                )
                self._spatial.insert(pl, aabb)
        self._rebuild_extreme_points()
        for old_pl in old_ids.values():
            M.log_remove("PlanningState.import_placements", old_pl, "cleared by snapshot restore")

    # ── Public query interface ─────────────────────────────────────────

    def query_aabb(self, aabb: AABB) -> list[tuple[Placement, AABB]]:
        """Return (placement, aabb) pairs whose grid cells overlap *aabb*.

        Used by the validation pipeline for fast collision and sweep checks.
        """
        return self._spatial.query(aabb)

    # ── Reset ──────────────────────────────────────────────────────────

    def reset(self) -> None:
        self._placements.clear()
        self._spatial.clear()
        self._sequence_counter = 0
        self._extreme_points = {(0, 0, 0)}

    # ── Internal: incremental extreme point update ─────────────────────

    def _extreme_points_add(
        self,
        package: Package,
        x: float,
        y: float,
        z: float,
        rotation: int,
    ) -> None:
        """Incrementally update extreme points after placing a package."""
        h_clr = getattr(package, 'horizontal_clearance_mm', 10.0)
        v_clr = getattr(package, 'vertical_clearance_mm', 0.0)
        pkg_aabb = AABB.from_dimensions(
            x, y, z,
            package.length_mm,
            package.width_mm,
            package.height_mm,
            rotation, clearance_xy=h_clr, clearance_z=v_clr,
        )

        # 1. Remove extreme points inside the just-placed package's clearance zone
        remaining = {
            ep for ep in self._extreme_points
            if not pkg_aabb.strictly_contains_point(*ep)
        }

        # 2. Build three new extreme points (accounting for clearance)
        if rotation in (90, 270):
            l_eff = package.width_mm
            w_eff = package.length_mm
        else:
            l_eff = package.length_mm
            w_eff = package.width_mm

        new_pts = [
            (x + l_eff + 2 * h_clr, y, z),   # right face (X)
            (x, y + w_eff + 2 * h_clr, z),   # front face (Y)
            (x, y, z + package.height_mm + 2 * v_clr),  # top face (Z)
        ]

        cl, cw, ch = (
            self.container.length,
            self.container.width,
            self.container.height,
        )

        # 3. Add each new point if inside container and not inside any existing package's clearance zone
        for pt in new_pts:
            if pt[0] > cl + 0.001 or pt[1] > cw + 0.001 or pt[2] > ch + 0.001:
                continue
            inside = False
            # Exclude the package we just placed (the last one)
            for pl in self._placements[:-1]:
                if pl.package is None:
                    continue
                pl_h_clr = getattr(pl.package, 'horizontal_clearance_mm', 10.0)
                pl_v_clr = getattr(pl.package, 'vertical_clearance_mm', 0.0)
                pl_aabb = AABB.from_dimensions(
                    pl.x, pl.y, pl.z,
                    pl.package.length_mm,
                    pl.package.width_mm,
                    pl.package.height_mm,
                    pl.rotation, clearance_xy=pl_h_clr, clearance_z=pl_v_clr,
                )
                if pl_aabb.strictly_contains_point(*pt):
                    inside = True
                    break
            if not inside:
                remaining.add(pt)

        self._extreme_points = remaining

    # ── Internal: full rebuild (after pop/insert) ──────────────────────

    def _rebuild_extreme_points(self) -> None:
        """Regenerate extreme points from scratch (same logic as original
        ``generate_candidate_points`` but stored as a persistent set)."""
        points: set[tuple[float, float, float]] = {(0, 0, 0)}

        for pl in self._placements:
            pkg = pl.package
            if pkg is None:
                continue
            h_clr = getattr(pkg, 'horizontal_clearance_mm', 10.0)
            v_clr = getattr(pkg, 'vertical_clearance_mm', 0.0)
            if pl.rotation in (90, 270):
                l_eff = pkg.width_mm
                w_eff = pkg.length_mm
            else:
                l_eff = pkg.length_mm
                w_eff = pkg.width_mm

            points.add((pl.x + l_eff + 2 * h_clr, pl.y, pl.z))
            points.add((pl.x, pl.y + w_eff + 2 * h_clr, pl.z))
            points.add((pl.x, pl.y, pl.z + pkg.height_mm + 2 * v_clr))

        # Filter container bounds
        cl, cw, ch = (
            self.container.length,
            self.container.width,
            self.container.height,
        )
        filtered: set[tuple[float, float, float]] = set()
        for x, y, z in points:
            if x <= cl + 0.001 and y <= cw + 0.001 and z <= ch + 0.001:
                filtered.add((x, y, z))

        # Filter points inside placed packages' clearance zones
        for pl in self._placements:
            if pl.package is None:
                continue
            pl_h_clr = getattr(pl.package, 'horizontal_clearance_mm', 10.0)
            pl_v_clr = getattr(pl.package, 'vertical_clearance_mm', 0.0)
            pl_aabb = AABB.from_dimensions(
                pl.x, pl.y, pl.z,
                pl.package.length_mm,
                pl.package.width_mm,
                pl.package.height_mm,
                pl.rotation, clearance_xy=pl_h_clr, clearance_z=pl_v_clr,
            )
            to_remove = set()
            for pt in filtered:
                if pl_aabb.strictly_contains_point(*pt):
                    to_remove.add(pt)
            filtered -= to_remove

        self._extreme_points = filtered
