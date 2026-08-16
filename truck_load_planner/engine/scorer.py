from dataclasses import dataclass, field
from typing import Optional
from .package import Package
from .placement import Placement
from .container import Container
from .geometry import AABB

SCORING_WEIGHTS = {
    # usable_space boosted 3x (was 1) so its dead-strip penalty (-1500 now,
    # was -500) reliably outweighs a high contact_area score (max 1000) —
    # previously a placement with great contact could still win despite
    # leaving an unusable gap for remaining packages.
    "usable_space": 3,
    "contact_area": 1000,
    # x_position now measures row/slice completion (higher = better; see
    # _score_x_position), not "prefer small xmin" — weight sign flipped
    # accordingly from the pre-Phase-2 version.
    "x_position": 200,
    "weight_balance": 50,
    "stack_level": 1,
    "tower_height": 1,
}

@dataclass
class PlacementScore:
    total: float = 0.0
    breakdown: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "total": round(self.total, 1),
            "breakdown": {k: round(v, 1) for k, v in self.breakdown.items()},
            "warnings": self.warnings,
            "metadata": self.metadata,
        }

def _make_aabb(package: Package, x: float, y: float, z: float,
               rotation: int = 0) -> AABB:
    return AABB.from_dimensions(
        x, y, z,
        package.length_mm,
        package.width_mm,
        package.height_mm,
        rotation,
    )

_FACE_TOLERANCE = 1.0
_GAP_TOLERANCE = 50.0

def _overlap_len(a1: float, a2: float, b1: float, b2: float) -> float:
    return max(0.0, min(a2, b2) - max(a1, b1))

def _overlap_2d(
    a1: tuple[float, float], a2: tuple[float, float],
    b1: tuple[float, float], b2: tuple[float, float],
) -> bool:
    return _overlap_len(a1[0], a1[1], a2[0], a2[1]) > 0 and \
           _overlap_len(b1[0], b1[1], b2[0], b2[1]) > 0

def _build_others_with_layers(placements: list) -> list[tuple[AABB, int]]:
    sorted_pls = sorted(placements, key=lambda p: p.z)
    result = []
    for pl in sorted_pls:
        if pl.package is None:
            continue
        aabb = _make_aabb(pl.package, pl.x, pl.y, pl.z, pl.rotation)
        layer = 0
        if aabb.zmin > 0.001:
            for o_aabb, o_layer in result:
                if abs(aabb.zmin - o_aabb.zmax) <= _FACE_TOLERANCE and _overlap_2d(
                    (aabb.xmin, aabb.xmax), (o_aabb.xmin, o_aabb.xmax),
                    (aabb.ymin, aabb.ymax), (o_aabb.ymin, o_aabb.ymax),
                ):
                    layer = max(layer, o_layer + 1)
            if layer == 0:
                layer = 1
        result.append((aabb, layer))
    return result

def _score_package_contact(aabb: AABB, others: list[AABB]) -> float:
    l = aabb.xmax - aabb.xmin
    w = aabb.ymax - aabb.ymin
    h = aabb.zmax - aabb.zmin
    max_possible = l * w + l * h + w * h
    if max_possible <= 0:
        return 0.0

    total_contact = 0.0
    for o in others:
        if abs(aabb.xmin - o.xmax) <= _FACE_TOLERANCE and _overlap_2d(
            (aabb.ymin, aabb.ymax), (o.ymin, o.ymax),
            (aabb.zmin, aabb.zmax), (o.zmin, o.zmax),
        ):
            dy = _overlap_len(aabb.ymin, aabb.ymax, o.ymin, o.ymax)
            dz = _overlap_len(aabb.zmin, aabb.zmax, o.zmin, o.zmax)
            total_contact += dy * dz

        if abs(aabb.xmax - o.xmin) <= _FACE_TOLERANCE and _overlap_2d(
            (aabb.ymin, aabb.ymax), (o.ymin, o.ymax),
            (aabb.zmin, aabb.zmax), (o.zmin, o.zmax),
        ):
            dy = _overlap_len(aabb.ymin, aabb.ymax, o.ymin, o.ymax)
            dz = _overlap_len(aabb.zmin, aabb.zmax, o.zmin, o.zmax)
            total_contact += dy * dz

        if abs(aabb.ymin - o.ymax) <= _FACE_TOLERANCE and _overlap_2d(
            (aabb.xmin, aabb.xmax), (o.xmin, o.xmax),
            (aabb.zmin, aabb.zmax), (o.zmin, o.zmax),
        ):
            dx = _overlap_len(aabb.xmin, aabb.xmax, o.xmin, o.xmax)
            dz = _overlap_len(aabb.zmin, aabb.zmax, o.zmin, o.zmax)
            total_contact += dx * dz

        if abs(aabb.ymax - o.ymin) <= _FACE_TOLERANCE and _overlap_2d(
            (aabb.xmin, aabb.xmax), (o.xmin, o.xmax),
            (aabb.zmin, aabb.zmax), (o.zmin, o.zmax),
        ):
            dx = _overlap_len(aabb.xmin, aabb.xmax, o.xmin, o.xmax)
            dz = _overlap_len(aabb.zmin, aabb.zmax, o.zmin, o.zmax)
            total_contact += dx * dz

        if abs(aabb.zmin - o.zmax) <= _FACE_TOLERANCE and _overlap_2d(
            (aabb.xmin, aabb.xmax), (o.xmin, o.xmax),
            (aabb.ymin, aabb.ymax), (o.ymin, o.ymax),
        ):
            dx = _overlap_len(aabb.xmin, aabb.xmax, o.xmin, o.xmax)
            dy = _overlap_len(aabb.ymin, aabb.ymax, o.ymin, o.ymax)
            total_contact += dx * dy

        if abs(aabb.zmax - o.zmin) <= _FACE_TOLERANCE and _overlap_2d(
            (aabb.xmin, aabb.xmax), (o.xmin, o.xmax),
            (aabb.ymin, aabb.ymax), (o.ymin, o.ymax),
        ):
            dx = _overlap_len(aabb.xmin, aabb.xmax, o.xmin, o.xmax)
            dy = _overlap_len(aabb.ymin, aabb.ymax, o.ymin, o.ymax)
            total_contact += dx * dy

    return min(total_contact / max_possible, 1.0)

# layer0-vs-layer1 gap kept small (contra a naive 1000/300 split) so contact_area/
# usable_space can outweigh it when stacking is genuinely the better placement;
# the steep drop below layer2 still discourages deep, less-stable towers.
def _score_stack_and_tower(aabb: AABB, others_with_layers: list[tuple[AABB, int]]) -> tuple[float, float]:
    layer = 0
    if aabb.zmin > 0.001:
        for o_aabb, o_layer in others_with_layers:
            if abs(aabb.zmin - o_aabb.zmax) <= _FACE_TOLERANCE and _overlap_2d(
                (aabb.xmin, aabb.xmax), (o_aabb.xmin, o_aabb.xmax),
                (aabb.ymin, aabb.ymax), (o_aabb.ymin, o_aabb.ymax),
            ):
                layer = max(layer, o_layer + 1)
        if layer == 0:
            layer = 1
            
    if layer == 0:
        stack_score = 200.0
    elif layer == 1:
        stack_score = 150.0
    elif layer == 2:
        stack_score = 50.0
    else:
        stack_score = -500.0

    tower_layer = layer
    expanded_xmin = aabb.xmin - 500
    expanded_xmax = aabb.xmax + 500
    expanded_ymin = aabb.ymin - 500
    expanded_ymax = aabb.ymax + 500
    
    for o_aabb, o_layer in others_with_layers:
        if _overlap_len(expanded_xmin, expanded_xmax, o_aabb.xmin, o_aabb.xmax) > 0 and \
           _overlap_len(expanded_ymin, expanded_ymax, o_aabb.ymin, o_aabb.ymax) > 0:
            tower_layer = max(tower_layer, o_layer)

    if tower_layer == 0:
        tower_score = 100.0
    elif tower_layer == 1:
        tower_score = 60.0
    elif tower_layer == 2:
        tower_score = -50.0
    elif tower_layer == 3:
        tower_score = -300.0
    else:
        tower_score = -800.0

    return stack_score, tower_score

def _score_y_balance(aabb: AABB, package: Package, placements: list,
                     container: Container) -> float:
    if container.width <= 0:
        return 0.0

    total_weight = package.weight_kg
    cy = (aabb.ymin + aabb.ymax) / 2
    weighted_y = cy * package.weight_kg

    for pl in placements:
        if pl.package is None:
            continue
        pkg = pl.package
        w = pkg.weight_kg
        if w <= 0:
            continue
        pkg_aabb = _make_aabb(pkg, pl.x, pl.y, pl.z, pl.rotation)
        weighted_y += ((pkg_aabb.ymin + pkg_aabb.ymax) / 2) * w
        total_weight += w

    if total_weight <= 0:
        return 0.0

    center_y = weighted_y / total_weight
    ideal = container.width / 2
    max_dist = container.width / 2
    dist = abs(center_y - ideal)
    return max(0.0, 1.0 - dist / max_dist)

def _score_usable_space(
    aabb: AABB,
    others: list[AABB],
    container: Container,
    remaining_packages: Optional[list] = None,
) -> float:
    if container.width <= 0 or not remaining_packages:
        return 0.0

    left_gap = max(0.0, aabb.ymin)
    right_gap = max(0.0, container.width - aabb.ymax)

    for o in others:
        if not _overlap_2d(
            (aabb.xmin, aabb.xmax), (o.xmin, o.xmax),
            (aabb.zmin, aabb.zmax), (o.zmin, o.zmax),
        ):
            continue

        if o.ymax <= aabb.ymin + _FACE_TOLERANCE:
            left_gap = min(left_gap, max(0.0, aabb.ymin - o.ymax))

        if o.ymin >= aabb.ymax - _FACE_TOLERANCE:
            right_gap = min(right_gap, max(0.0, o.ymin - aabb.ymax))

    gaps = [
        0.0 if gap <= _GAP_TOLERANCE else gap
        for gap in (left_gap, right_gap)
    ]
    positive_gaps = [gap for gap in gaps if gap > 0]
    max_gap = max(positive_gaps, default=0.0)
    if max_gap == 0:
        return 100.0

    floor_dims: list[float] = []
    fit_count = 0
    for pkg in remaining_packages:
        length = float(getattr(pkg, "length_mm", 0) or 0)
        width = float(getattr(pkg, "width_mm", 0) or 0)
        min_dim = min(d for d in (length, width) if d > 0) if length > 0 or width > 0 else 0
        if min_dim <= 0:
            continue
        floor_dims.append(min_dim)
        if min_dim <= max_gap + _FACE_TOLERANCE:
            fit_count += 1

    if not floor_dims:
        return 0.0

    min_pkg_dim = min(floor_dims)
    if any(gap < min_pkg_dim for gap in positive_gaps):
        return -500.0

    usable_ratio = fit_count / len(remaining_packages)
    width_ratio = (
        (aabb.ymax - aabb.ymin) / container.width
        if container.width > 0 else 0.0
    )
    return min(500.0, usable_ratio * 350.0 + width_ratio * 150.0)

def _score_x_position(aabb: AABB, others: list[AABB], container: Container) -> float:
    """Row/slice-completion: reward a candidate that closes out the width
    at the deepest X reached so far (within its own height band), instead
    of skipping past an open row into fresh container depth. Restricted to
    packages whose Z-range overlaps the candidate's — a stack elsewhere at
    a different height shouldn't count against this candidate's row."""
    if container.width <= 0 or container.length <= 0:
        return 0.0

    same_band = [
        o for o in others
        if _overlap_len(aabb.zmin, aabb.zmax, o.zmin, o.zmax) > 0
    ]
    front_x = max((o.xmax for o in same_band), default=0.0)

    at_front = front_x == 0.0 or abs(aabb.xmin - front_x) <= _FACE_TOLERANCE
    if not at_front:
        # Skipping ahead of the still-open row — no completion bonus, but
        # still mildly prefer shallower depth so placement keeps advancing
        # once a row is actually closed out.
        return max(0.0, 1.0 - aabb.xmin / container.length)

    covered_width = sum(
        max(0.0, o.ymax - o.ymin) for o in same_band
        if o.xmin <= front_x + _FACE_TOLERANCE and o.xmax >= front_x - _FACE_TOLERANCE
    )
    remaining_width = max(0.0, container.width - covered_width)
    if remaining_width <= 0:
        return 0.0

    candidate_width = aabb.ymax - aabb.ymin
    return min(1.0, candidate_width / remaining_width)

def score_placement(
    package: Package,
    x: float,
    y: float,
    z: float,
    rotation: int,
    placements: list,
    container: Container,
    debug: bool = False,
    remaining_packages: Optional[list] = None,
) -> PlacementScore:
    aabb = _make_aabb(package, x, y, z, rotation)
    others_with_layers = _build_others_with_layers(placements)
    others = [o for o, _ in others_with_layers]
    
    weights = SCORING_WEIGHTS
    warnings: list[str] = []

    stack_score, tower_score = _score_stack_and_tower(aabb, others_with_layers)

    raw = {
        "usable_space": _score_usable_space(aabb, others, container, remaining_packages),
        "contact_area": _score_package_contact(aabb, others),
        "x_position": _score_x_position(aabb, others, container),
        "weight_balance": _score_y_balance(aabb, package, placements, container),
        "stack_level": stack_score,
        "tower_height": tower_score,
    }

    breakdown = {}
    total = 0.0
    for key, raw_score in raw.items():
        sub = raw_score * weights.get(key, 0)
        breakdown[key] = sub
        total += sub

    if raw["contact_area"] < 0.1 and len(placements) > 0:
        warnings.append("Package is isolated from others")

    metadata = {
        "position": {"x": x, "y": y, "z": z},
        "rotation": rotation,
        "package_name": package.name,
        "neighbor_count": len(others),
        "stack_level": raw["stack_level"],
        "tower_height": raw["tower_height"],
    }

    if debug:
        print(f"\n  Score for '{package.name}' @ ({x:.0f}, {y:.0f}, {z:.0f})")
        for key in weights:
            print(f"    {key:20s} {raw[key]:5.2f} \u00d7 {weights[key]:g} = {breakdown[key]:.1f}")
        print(f"    {'total':20s} {total:.1f}")
        if warnings:
            print(f"    warnings: {warnings}")

    return PlacementScore(
        total=total,
        breakdown=breakdown,
        warnings=warnings,
        metadata=metadata,
    )
