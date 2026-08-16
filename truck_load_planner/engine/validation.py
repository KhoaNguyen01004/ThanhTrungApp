"""
Validation system — combines boundary, collision, weight, and support checks
into a single ValidationResult with explicit reasons.

Checks are ordered from cheapest to most expensive so impossible candidates
are rejected as early as possible (Priority 3: Progressive Filtering).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable

from .geometry import AABB
from .boundary import check_boundary
from .collision import check_collision
from .weight import check_weight
from .support import check_support
from .access import check_door_fit, check_door_sweep
from .container import Container
from .placement import Placement
from .package import Package


class ValidationMode(Enum):
    INSERTION = "insertion"
    REPOSITION = "reposition"


@dataclass
class ValidationResult:
    valid: bool
    reasons: list = field(default_factory=list)
    door_used: str = "rear"

    def to_dict(self) -> dict:
        return {"valid": self.valid, "reasons": self.reasons, "door_used": self.door_used}


def validate_placement(
    placements: list,
    package: Package,
    x: float,
    y: float,
    z: float,
    rotation: int,
    container: Container,
    features: Optional[list] = None,
    query_aabb_fn: Optional[Callable] = None,
    mode: ValidationMode = ValidationMode.INSERTION,
) -> ValidationResult:
    """Run all validation checks in progressive order (cheapest first).

    Checks: boundary → payload → door fit → collision → support → door sweep.
    Each stage short-circuits — as soon as one fails, remaining expensive
    checks are skipped.

    When *query_aabb_fn* is provided, collision and sweep checks use
    the spatial index instead of iterating all *placements*.

    *mode* controls which checks apply:
      - INSERTION (default): full validation including door fit and sweep.
      - REPOSITION:     skip door fit and sweep — used during compaction
                         where the package is already inside the container.
    """
    reasons = []

    h_clr = getattr(package, 'horizontal_clearance_mm', 10.0)
    v_clr = getattr(package, 'vertical_clearance_mm', 0.0)
    # Actual AABB (no clearance) — used for boundary check so packages
    # can touch container walls. Clearance on the wall-facing side
    # doesn't make physical sense (package can't extend past the wall).
    actual_aabb = AABB.from_dimensions(
        x, y, z,
        package.length_mm, package.width_mm, package.height_mm,
        rotation, clearance=0,
    )
    # Inflated AABB (with per-axis clearance) — used for collision and
    # door sweeps so there is breathing room between packages.
    # Horizontal clearance separates side-by-side packages; vertical
    # clearance separates stacked packages.
    candidate_aabb = AABB.from_dimensions(
        x, y, z,
        package.length_mm, package.width_mm, package.height_mm,
        rotation, clearance_xy=h_clr, clearance_z=v_clr,
    )

    container_aabb = AABB(
        0, 0, 0,
        container.length,
        container.width,
        container.height,
    )

    # ── 1. Boundary (cheapest: 6 comparisons) ─────────────────────────
    bresult = check_boundary(actual_aabb, container_aabb)
    if not bresult["pass"]:
        return ValidationResult(valid=False, reasons=bresult["errors"])

    # ── 2. Payload / Weight (cheap: one sum) ──────────────────────────
    simulated = placements + [
        Placement(
            package_id=package.id or 0,
            x=x, y=y, z=z,
            rotation=rotation,
            package=package,
        )
    ]
    wresult = check_weight(simulated, container.payload_kg)
    if not wresult["pass"]:
        return ValidationResult(valid=False, reasons=wresult.get("errors", []))

    # ── 3. Door fit (cheap: a few size comparisons, no sweep) ─────────
    doors_info = None
    if mode == ValidationMode.INSERTION:
        feat_list = features or []
        if feat_list:
            fresult = check_door_fit(package, candidate_aabb, container, feat_list, rotation=rotation)
            if not fresult["fits"]:
                return ValidationResult(valid=False, reasons=fresult["reasons"])
            doors_info = fresult["doors"]
        else:
            # No door features configured — assume a full-width/full-height rear door
            # so that the sweep check (step 6) always validates the push path.
            doors_info = {
                "rear_door": {
                    "width_mm": container.width,
                    "height_mm": container.height,
                },
                "side_doors": [],
            }

    # ── 4. Collision (moderate: spatial query + AABB intersects) ──────
    if query_aabb_fn:
        for _, existing_aabb in query_aabb_fn(candidate_aabb):
            if check_collision(candidate_aabb, existing_aabb):
                reasons.append("Collision with nearby package")
                break
    else:
        for pl in placements:
            if pl.package is None:
                continue
            pkg = pl.package
            ph_clr = getattr(pkg, 'horizontal_clearance_mm', 10.0)
            pv_clr = getattr(pkg, 'vertical_clearance_mm', 0.0)
            existing_aabb = AABB.from_dimensions(
                pl.x, pl.y, pl.z,
                pkg.length_mm, pkg.width_mm, pkg.height_mm,
                pl.rotation,
                clearance_xy=ph_clr, clearance_z=pv_clr,
            )
            if check_collision(candidate_aabb, existing_aabb):
                reasons.append(f"Collision with '{pkg.name}'")
                break
    if reasons:
        return ValidationResult(valid=False, reasons=reasons)

    # ── 5. Support (moderate: below-package search + area checks) ─────
    # Use actual AABB (no clearance) — physical support doesn't need clearance
    sresult = check_support(placements, actual_aabb, package=package)
    if not sresult["valid"]:
        return ValidationResult(valid=False, reasons=sresult.get("reasons", []))

    # ── 6. Door sweep (most expensive: sweep AABB + spatial query) ────
    door_used = "rear"
    if mode == ValidationMode.INSERTION and doors_info:
        dresult = check_door_sweep(
            placements, package, candidate_aabb,
            container, doors_info,
            rotation=rotation,
            query_aabb_fn=query_aabb_fn,
        )
        if not dresult["valid"]:
            return ValidationResult(valid=False, reasons=dresult.get("reasons", []))
        door_used = dresult.get("door_used", "rear")

    return ValidationResult(valid=True, reasons=[], door_used=door_used)
