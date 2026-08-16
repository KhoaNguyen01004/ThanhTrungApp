"""
Planner — single entry point for all planning operations.
The UI should never call geometry/validation modules directly.
"""

from typing import Optional, Callable

from .package import Package
from .placement import Placement
from .container import Container
from .geometry import AABB
from .state import PlanningState
from .validation import validate_placement, ValidationResult, ValidationMode
from .statistics import compute_statistics
from .scorer import score_placement, PlacementScore, SCORING_WEIGHTS
from .auto_arrange import AutoArrangeResult
from .trace_mutations import M


class Planner:
    """Coordinates all subsystems for a single loading session."""

    def __init__(self, container: Container, features: Optional[list] = None,
                 candidate_limit: Optional[int] = None):
        self.state = PlanningState(container, features)
        self._candidate_limit = candidate_limit

    @property
    def container(self) -> Container:
        return self.state.container

    @container.setter
    def container(self, value: Container) -> None:
        self.state.container = value

    @property
    def features(self) -> list:
        return self.state.features

    @features.setter
    def features(self, value: list) -> None:
        self.state.features = value

    @property
    def placements(self) -> list:
        return self.state.placements

    def place_package(
        self,
        package: Package,
        x: float,
        y: float,
        z: float = 0,
        rotation: int = 0,
        _trace_reason: str = "place_package",
    ) -> ValidationResult:
        mode = getattr(self, '_validation_mode', ValidationMode.INSERTION)
        result = validate_placement(
            self.state.placements, package,
            x, y, z, rotation,
            self.state.container, self.state.features,
            query_aabb_fn=self.state.query_aabb,
            mode=mode,
        )
        if result.valid:
            pl = self.state.append_placement(package, x, y, z, rotation, door_used=result.door_used)
            # Re-log with caller context (append_placement already logged as "new placement")
            M.log("Planner.place_package", pl, None, (x, y, z, rotation), _trace_reason)
        return result

    def move_package(self, index: int, new_x: float, new_y: float) -> ValidationResult:
        if index < 0 or index >= len(self.state.placements):
            return ValidationResult(False, ["Invalid placement index"])

        old = self.state.pop_placement(index)
        M.log_remove("Planner.move_package/pop", old, f"idx={index}")

        result = validate_placement(
            self.state.placements, old.package,
            new_x, new_y, old.z, old.rotation,
            self.state.container, self.state.features,
            query_aabb_fn=self.state.query_aabb,
        )
        if result.valid:
            pl = self.state.insert_placement(
                index, old.package, new_x, new_y, old.z, old.rotation,
                load_sequence=old.load_sequence,
            )
            M.log("Planner.move_package/insert", pl,
                  (old.x, old.y, old.z, old.rotation),
                  (new_x, new_y, old.z, old.rotation), f"idx={index}")
        else:
            pl = self.state.insert_placement(
                index, old.package, old.x, old.y, old.z, old.rotation,
                load_sequence=old.load_sequence,
            )
            M.log("Planner.move_package/restore", pl,
                  (old.x, old.y, old.z, old.rotation),
                  (old.x, old.y, old.z, old.rotation), "validation failed")
        return result

    def remove_package(self, index: int) -> None:
        pl = self.state.pop_placement(index)
        if pl:
            M.log_remove("Planner.remove_package", pl, f"idx={index}")

    def validate(self) -> ValidationResult:
        from .boundary import check_boundary
        from .collision import check_collision
        from .weight import check_weight
        from .support import check_support

        reasons = []
        container_aabb = AABB(0, 0, 0, self.state.container.length,
                              self.state.container.width, self.state.container.height)

        # ── 1. Weight (cheapest: one sum) ──────────────────────────────
        wresult = check_weight(self.state.placements, self.state.container.payload_kg)
        if not wresult["pass"]:
            reasons.extend(wresult.get("errors", []))

        # ── 2. Per-package boundary + collision (moderate) ─────────────
        pl_to_index = {id(pl): i for i, pl in enumerate(self.state.placements)}
        checked_pairs: set[tuple[int, int]] = set()
        for i, pl in enumerate(self.state.placements):
            pkg = pl.package
            if pkg is None:
                continue
            h_clr = getattr(pkg, 'horizontal_clearance_mm', 10.0)
            v_clr = getattr(pkg, 'vertical_clearance_mm', 0.0)
            actual_aabb = AABB.from_dimensions(
                pl.x, pl.y, pl.z,
                pkg.length_mm, pkg.width_mm, pkg.height_mm,
                pl.rotation, clearance=0,
            )
            br = check_boundary(actual_aabb, container_aabb)
            if not br["pass"]:
                reasons.extend(f"[{i}] {e}" for e in br["errors"])
                continue
            coll_aabb = AABB.from_dimensions(
                pl.x, pl.y, pl.z,
                pkg.length_mm, pkg.width_mm, pkg.height_mm,
                pl.rotation, clearance_xy=h_clr, clearance_z=v_clr,
            )
            nearby = self.state.query_aabb(coll_aabb)
            for other_pl, other_aabb in nearby:
                j = pl_to_index.get(id(other_pl))
                if j is None or i >= j or (i, j) in checked_pairs:
                    continue
                checked_pairs.add((i, j))
                if check_collision(coll_aabb, other_aabb):
                    reasons.append(f"Collision between [{i}] and [{j}]")

        # ── 3. Support (moderate: per-package area checks) ────────────
        for pl in self.state.placements:
            if pl.package is None:
                continue
            paabb = AABB.from_dimensions(
                pl.x, pl.y, pl.z,
                pl.package.length_mm, pl.package.width_mm,
                pl.package.height_mm, pl.rotation, clearance=0,
            )
            sresult = check_support(self.state.placements, paabb, package=pl.package)
            if not sresult["valid"]:
                reasons.extend(sresult.get("reasons", []))

        return ValidationResult(valid=len(reasons) == 0, reasons=reasons)

    def get_statistics(self) -> dict:
        return compute_statistics(self.state.placements, self.state.container)

    def get_candidate_points(self) -> list:
        return self.state.get_candidate_points()

    def score_placement(
        self,
        package: Package,
        x: float,
        y: float,
        z: float,
        rotation: int,
        debug: bool = False,
        remaining_packages: Optional[list] = None,
    ) -> PlacementScore:
        return score_placement(
            package, x, y, z, rotation,
            self.state.placements, self.state.container,
            debug=debug,
            remaining_packages=remaining_packages,
        )

    def evaluate_position(
        self,
        package: Package,
        x: float,
        y: float,
        z: float,
        rotation: int = 0,
        debug: bool = False,
        remaining_packages: Optional[list] = None,
    ) -> PlacementScore:
        """Score a single placement position.

        This is the preferred API for external callers (Auto Arrange, solvers).
        Delegates to score_placement internally.
        """
        return self.score_placement(
            package, x, y, z, rotation,
            debug=debug,
            remaining_packages=remaining_packages,
        )

    def evaluate_candidates(
        self,
        package: Package,
        candidate_positions: list,
        debug: bool = False,
    ) -> list:
        """Score and rank candidate positions for a package.

        Each candidate is a dict or tuple with x, y, z, rotation.
        Returns a list of (position_dict, score) tuples sorted descending by score.
        """
        scored = []
        for pos in candidate_positions:
            if isinstance(pos, dict):
                x = pos.get("x", 0)
                y = pos.get("y", 0)
                z = pos.get("z", 0)
                rotation = pos.get("rotation", 0)
            else:
                x, y, z, rotation = (*pos, 0)[:4]

            s = self.score_placement(package, x, y, z, rotation, debug=debug)
            scored.append((pos, s))

        scored.sort(key=lambda item: item[1].total, reverse=True)
        return scored

    def evaluate_plan(self, debug: bool = False) -> PlacementScore:
        """Score the entire load plan by averaging individual placement scores.

        Returns:
            PlacementScore representing overall plan quality.
        """
        if not self.state.placements:
            return PlacementScore(
                total=0.0,
                breakdown={},
                warnings=["No packages in plan"],
                metadata={"package_count": 0},
            )

        scores: list[PlacementScore] = []
        for pl in self.state.placements:
            if pl.package is None:
                continue
            s = self.score_placement(
                pl.package, pl.x, pl.y, pl.z, pl.rotation,
                debug=debug,
            )
            scores.append(s)

        n = len(scores)
        if n == 0:
            return PlacementScore(
                total=0.0,
                breakdown={},
                warnings=["No scored packages in plan"],
                metadata={"package_count": 0},
            )

        avg_breakdown: dict[str, float] = {}
        for key in SCORING_WEIGHTS:
            avg_breakdown[key] = sum(s.breakdown.get(key, 0) for s in scores) / n

        avg_total = sum(s.total for s in scores) / n
        all_warnings = []
        for s in scores:
            all_warnings.extend(s.warnings)

        return PlacementScore(
            total=min(avg_total, 100.0),
            breakdown=avg_breakdown,
            warnings=all_warnings[:10],
            metadata={
                "package_count": n,
                "individual_scores": [s.total for s in scores],
            },
        )

    def validate_position(
        self,
        package: Package,
        x: float,
        y: float,
        z: float,
        rotation: int = 0,
    ) -> ValidationResult:
        """Validate a single candidate position without placing."""
        mode = getattr(self, '_validation_mode', ValidationMode.INSERTION)
        return validate_placement(
            self.state.placements, package,
            x, y, z, rotation,
            self.state.container, self.state.features,
            query_aabb_fn=self.state.query_aabb,
            mode=mode,
        )

    def auto_arrange(
        self,
        packages: list[Package],
        strategy: str = "optimized",
        progress_callback: Optional[Callable] = None,
        cancel_callback: Optional[Callable] = None,
        debug: bool = False,
    ) -> AutoArrangeResult:
        """Run the named auto-arrange strategy.

        Args:
            packages: List of engine Package objects to place.
            strategy: Name of registered strategy ('largest_first', …).
            progress_callback: Called as fn(placed, total, current_score)
                              after each package attempt.
            cancel_callback: Called as fn() → bool; if True, stop early.
            debug: Collect structured debug entries into result.

        Returns:
            AutoArrangeResult with placed/failed counts, utilisation, score.
        """
        from .auto_arrange import StrategyRegistry
        strategy_cls = StrategyRegistry.get(strategy)
        if strategy_cls is None:
            raise ValueError(
                f"Unknown auto-arrange strategy '{strategy}'. "
                f"Registered: {StrategyRegistry.list()}"
            )
        strat = strategy_cls()
        return strat.arrange(
            self, packages,
            progress_callback=progress_callback,
            cancel_callback=cancel_callback,
            debug=debug,
        )

    def export_plan(self) -> dict:
        return {
            "container": self.state.container.to_dict() if self.state.container else None,
            "features": self.state.features,
            "placements": [
                {
                    "package_id": p.package_id,
                    "x": p.x, "y": p.y, "z": p.z,
                    "rotation": p.rotation,
                    "load_sequence": p.load_sequence,
                    "_package": p.package.to_dict() if p.package else None,
                }
                for p in self.state.placements
            ],
            "statistics": self.get_statistics(),
        }

    def import_plan(self, data: dict) -> None:
        placements_data = data.get("placements", [])
        self.state.import_placements(placements_data)
        max_seq = 0
        for pd in placements_data:
            seq = pd.get("load_sequence", 0) or 0
            if seq > max_seq:
                max_seq = seq
        self.state.sequence_counter = max_seq

    def load_legacy_placements(self, placement_dicts: list[dict]) -> None:
        """Load placements from legacy dicts (used by LoadPlanningSession).

        Handles the format produced by ``_engine_placement_to_dict`` where
        ``_package`` may be an EnginePackage instance, a legacy Package, or
        a dict with underscore keys.
        """
        converted = []
        max_seq = 0
        for pd in placement_dicts:
            pkg = pd.get("_package")
            if pkg is None:
                old_clr = pd.get("clearance_mm", pd.get("clearance", None))
                h_clr = float(old_clr) if old_clr is not None else 10.0
                pkg = Package(
                    id=pd.get("package_id"),
                    name=pd.get("_name", pd.get("name", "")),
                    length_mm=pd.get("_length", pd.get("length", 0)),
                    width_mm=pd.get("_width", pd.get("width", 0)),
                    height_mm=pd.get("_height", pd.get("height", 0)),
                    weight_kg=pd.get("_weight_kg", pd.get("weight_kg", 0)),
                    stackable=bool(pd.get("stackable", pd.get("allow_stacking", 0))),
                    allow_rotation=bool(pd.get("allow_rotation", 1)),
                    horizontal_clearance_mm=h_clr,
                )
            elif not isinstance(pkg, dict):
                # EnginePackage or legacy model — convert to dict
                h_clr = float(getattr(pkg, 'horizontal_clearance_mm',
                              getattr(pkg, 'clearance_mm', 10.0)))
                pkg = Package(
                    id=getattr(pkg, "id", None),
                    name=getattr(pkg, "name", getattr(pkg, "_name", "")),
                    length_mm=getattr(pkg, "length_mm", getattr(pkg, "length", 0)),
                    width_mm=getattr(pkg, "width_mm", getattr(pkg, "width", 0)),
                    height_mm=getattr(pkg, "height_mm", getattr(pkg, "height", 0)),
                    weight_kg=getattr(pkg, "weight_kg", 0),
                    stackable=bool(getattr(pkg, "stackable", getattr(pkg, "allow_stacking", 0))),
                    allow_rotation=bool(getattr(pkg, "allow_rotation", 1)),
                    horizontal_clearance_mm=h_clr,
                )
            else:
                pkg = Package.from_dict(pkg)

            converted.append({
                "package_id": pd["package_id"],
                "x": pd.get("x", 0), "y": pd.get("y", 0), "z": pd.get("z", 0),
                "rotation": pd.get("rotation", 0),
                "load_sequence": pd.get("load_sequence"),
                "_package": pkg.to_dict() if pkg else None,
            })
            seq = pd.get("load_sequence", 0) or 0
            if seq > max_seq:
                max_seq = seq

        self.state.import_placements(converted)
        self.state.sequence_counter = max_seq

    def reset(self) -> None:
        self.state.reset()
