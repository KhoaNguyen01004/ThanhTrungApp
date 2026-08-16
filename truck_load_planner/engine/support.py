"""
Stacking support validation.
Ensures packages are placed on adequate support below them using a
combined-support model.  The union of XY overlap regions from all
supporting packages must cover a configurable percentage of the
candidate's footprint, and the candidate's footprint centre must lie
within the combined support region to prevent unstable bridging.

Stacking decisions use a capacity-based model rather than a simple
boolean: each base package may specify a maximum top weight, a
maximum number of stack layers, or a stacking mode (NONE / LIGHT_ONLY
/ NORMAL) to better reflect real warehouse practice.
"""

from .geometry import AABB
from .placement import Placement
from .package import Package, StackingMode


_GRID_SAMPLES = 20    # samples per axis for union coverage estimation

# Package.max_stack_layers == 0 is documented/DB-default as "no explicit
# per-package limit" (docs/TRUCK_LOAD_PLANNER.md), not "physically
# unlimited" — without a system-wide ceiling, unspecified packages could
# tower indefinitely. Used two ways: (1) as the per-base breadth fallback
# in _check_stacking_rules ("how many packages can share one base's top
# surface") when a package doesn't set its own max_stack_layers, and (2)
# as the hard column-depth cap in check_support ("how many packages tall
# can a single-file tower be") — (1) alone can't constrain (2), since a
# linear column never has more than one package directly on any given
# package.
_SYSTEM_MAX_STACK_LAYERS = 3


def _footprint_centre(aabb: AABB) -> tuple[float, float]:
    return (aabb.xmin + aabb.xmax) / 2, (aabb.ymin + aabb.ymax) / 2


def _count_above(placements, base_pl) -> int:
    """Count how many packages are stacked directly on top of *base_pl*
    — same Z as its top face, and XY-overlapping its footprint.

    (XY overlap was missing until the Phase 1 max_stack_layers hard-cap
    fix made this function load-bearing for the ~100% of packages that
    don't set an explicit per-package limit — before that it only ran
    for packages with a non-zero max_stack_layers, so a Z-only match
    counting *any* placement in the whole plan at the same height,
    regardless of position, was mostly dormant. Left unfixed would have
    made the hard cap fire based on unrelated packages sharing a height
    elsewhere in the container.)
    """
    base = base_pl.package
    if base is None:
        return 0
    base_len = base.length_mm if hasattr(base, 'length_mm') else getattr(base, 'length', 0)
    base_wid = base.width_mm if hasattr(base, 'width_mm') else getattr(base, 'width', 0)
    base_hei = base.height_mm if hasattr(base, 'height_mm') else getattr(base, 'height', 0)
    base_aabb = AABB.from_dimensions(
        base_pl.x, base_pl.y, base_pl.z,
        base_len, base_wid, base_hei,
        base_pl.rotation, clearance=0,
    )
    base_top = base_aabb.zmax

    count = 0
    for pl in placements:
        if pl is base_pl:
            continue
        pa = pl.package
        if pa is None or abs(pl.z - base_top) >= 0.001:
            continue
        pa_len = pa.length_mm if hasattr(pa, 'length_mm') else getattr(pa, 'length', 0)
        pa_wid = pa.width_mm if hasattr(pa, 'width_mm') else getattr(pa, 'width', 0)
        pa_hei = pa.height_mm if hasattr(pa, 'height_mm') else getattr(pa, 'height', 0)
        pl_aabb = AABB.from_dimensions(
            pl.x, pl.y, pl.z, pa_len, pa_wid, pa_hei, pl.rotation, clearance=0,
        )
        if (pl_aabb.xmin < base_aabb.xmax and pl_aabb.xmax > base_aabb.xmin
                and pl_aabb.ymin < base_aabb.ymax and pl_aabb.ymax > base_aabb.ymin):
            count += 1
    return count


def _tower_depth(placements: list, pl: Placement, _visited: set = None) -> int:
    """Return *pl*'s own 0-indexed layer number in its column (0 = on the
    floor) by walking down through whatever it's resting on.

    This is a genuinely different question from ``_count_above``'s
    per-base breadth check: a linear single-file tower never has more
    than one package directly on any given package, so a breadth cap
    can't limit how many layers deep a column goes. This does.
    """
    if _visited is None:
        _visited = set()
    if id(pl) in _visited:
        return 0
    _visited.add(id(pl))

    pa = pl.package
    if pa is None or pl.z <= 0.001:
        return 0

    pa_len = pa.length_mm if hasattr(pa, 'length_mm') else getattr(pa, 'length', 0)
    pa_wid = pa.width_mm if hasattr(pa, 'width_mm') else getattr(pa, 'width', 0)
    pa_hei = pa.height_mm if hasattr(pa, 'height_mm') else getattr(pa, 'height', 0)
    pl_aabb = AABB.from_dimensions(
        pl.x, pl.y, pl.z, pa_len, pa_wid, pa_hei, pl.rotation, clearance=0,
    )

    deepest_below = -1
    for other in placements:
        if other is pl:
            continue
        oa = other.package
        if oa is None:
            continue
        o_len = oa.length_mm if hasattr(oa, 'length_mm') else getattr(oa, 'length', 0)
        o_wid = oa.width_mm if hasattr(oa, 'width_mm') else getattr(oa, 'width', 0)
        o_hei = oa.height_mm if hasattr(oa, 'height_mm') else getattr(oa, 'height', 0)
        o_aabb = AABB.from_dimensions(
            other.x, other.y, other.z, o_len, o_wid, o_hei, other.rotation, clearance=0,
        )
        if abs(o_aabb.zmax - pl_aabb.zmin) < 0.001 and (
            o_aabb.xmin < pl_aabb.xmax and o_aabb.xmax > pl_aabb.xmin
            and o_aabb.ymin < pl_aabb.ymax and o_aabb.ymax > pl_aabb.ymin
        ):
            deepest_below = max(deepest_below, _tower_depth(placements, other, _visited))
    return deepest_below + 1


def _check_stacking_rules(
    below_pl,
    top_package: Package,
    placements: list,
) -> tuple[bool, list[str]]:
    """Check capacity-based stacking rules for one below package.

    Returns (valid, reasons).
    """
    pa = below_pl.package
    if pa is None:
        return True, []

    reasons = []

    # ── Top package is unstackable: cannot sit on anything ──────────
    top_mode = getattr(top_package, 'stacking_mode', StackingMode.NORMAL)
    if top_mode == StackingMode.NONE:
        return False, [f"'{top_package.name}' is unstackable (cannot be placed on top of other packages)"]

    mode = getattr(pa, 'stacking_mode', StackingMode.NORMAL)
    max_top = getattr(pa, 'max_top_weight_kg', 0.0)
    max_layers = getattr(pa, 'max_stack_layers', 0)

    # ── StackingMode.NONE: nothing allowed above ───────────────────
    if mode == StackingMode.NONE:
        return False, [f"Cannot stack on '{pa.name}' (stacking mode: NONE)"]

    # ── StackingMode.LIGHT_ONLY: lightweight packages only ──────────
    if mode == StackingMode.LIGHT_ONLY:
        if max_top > 0 and top_package.weight_kg > max_top:
            return False, [
                f"'{top_package.name}' ({top_package.weight_kg} kg) "
                f"exceeds '{pa.name}' max_top_weight ({max_top} kg)"
            ]

    # ── Max stack layers (explicit per-package limit, else system cap) ──
    effective_max_layers = max_layers if max_layers > 0 else _SYSTEM_MAX_STACK_LAYERS
    current_above = _count_above(placements, below_pl)
    if current_above >= effective_max_layers:
        return False, [
            f"'{pa.name}' already has {current_above} packages "
            f"on top (max: {effective_max_layers})"
        ]

    # ── Weight rule (all modes): top must be lighter than base ──────
    if top_package.weight_kg is not None and pa.weight_kg is not None:
        if top_package.weight_kg > pa.weight_kg:
            return False, [
                f"'{top_package.name}' ({top_package.weight_kg} kg) heavier "
                f"than '{pa.name}' ({pa.weight_kg} kg)"
            ]

    # ── Footprint area rule: top footprint must be ≤ base footprint ──
    top_fp = top_package.length_mm * top_package.width_mm
    base_fp = pa.length_mm * pa.width_mm
    if top_fp > base_fp:
        return False, [
            f"'{top_package.name}' footprint ({top_fp:.0f} mm²) larger "
            f"than '{pa.name}' footprint ({base_fp:.0f} mm²)"
        ]

    return True, []


def check_support(
    placements: list,
    candidate_aabb: AABB,
    package: Package = None,
    support_threshold: float = 0.50,
) -> dict:
    """Validate that the candidate has adequate support below.

    Rules:
      1. If z=0 (floor) → always supported.
      2. Each package directly below is checked against capacity-based
         stacking rules (stacking mode, max top weight, max layers).
      3. Top package must be lighter than every package directly below.
      4. The union of XY-overlap regions from all below packages must
         cover at least ``support_threshold`` (0-1) of the candidate's
         footprint area.
      5. The candidate's XY footprint centre must lie within at least
         one below package's XY extent.

    Args:
        placements: Current list of Placement objects.
        candidate_aabb: AABB of the package being placed.
        package: The package being placed (for weight check).
        support_threshold: Minimum fraction of candidate footprint that
            must be covered by the union of below-package XY overlap
            (default 0.50 = 50%).

    Returns:
        {"valid": True, "reasons": []} or
        {"valid": False, "reasons": ["..."]}

    Note: "packages directly below" (below) is intentionally matched by
    Z-height alone (``pkg_zmax == z_bottom``) across *all* placements,
    not narrowed by XY proximity first — a same-height package anywhere
    in the plan is checked against stacking-mode/weight/footprint rules
    before the XY-overlap coverage/centroid check below runs. A spatial-
    index-narrowed version was tried during the Phase 3 performance pass
    and reverted: narrowing by XY first changed real outcomes (167/2000
    candidates in a randomized check against real placements), because
    it silently dropped same-height-but-elsewhere packages that this
    step currently rules against before geometry is considered. That may
    itself be a latent bug worth revisiting, but changing it wasn't the
    goal of a performance pass — flagged for separate investigation
    rather than fixed as a drive-by.
    """
    z_bottom = candidate_aabb.zmin
    if z_bottom == 0:
        return {"valid": True, "reasons": []}

    candidate_l = candidate_aabb.xmax - candidate_aabb.xmin
    candidate_w = candidate_aabb.ymax - candidate_aabb.ymin
    candidate_area = candidate_l * candidate_w
    if candidate_area <= 0:
        return {"valid": False, "reasons": ["Package has zero footprint"]}

    # ── Collect packages directly below ──────────────────────────────
    below_placements = []
    for pl in placements:
        pa = pl.package
        if pa is None:
            continue
        pkg_zmax = pl.z + (
            pa.height_mm if hasattr(pa, 'height_mm')
            else getattr(pa, 'height', 0)
        )
        if abs(pkg_zmax - z_bottom) < 0.001:
            below_placements.append(pl)

    if not below_placements:
        return {"valid": False, "reasons": ["No support below package"]}

    # ── Hard tower-depth cap (independent of max_stack_layers' per-base
    #    breadth check above, which can't limit a single-file column) ────
    deepest_base_layer = max(_tower_depth(placements, bp) for bp in below_placements)
    if deepest_base_layer + 1 >= _SYSTEM_MAX_STACK_LAYERS:
        return {
            "valid": False,
            "reasons": [
                f"Column would reach {deepest_base_layer + 2} packages tall, "
                f"exceeding the system limit of {_SYSTEM_MAX_STACK_LAYERS}"
            ],
        }

    # ── Verify each below package: stacking rules + weight ────────────
    below_aabbs = []
    for pl in below_placements:
        pa = pl.package
        if pa is None:
            continue

        # Capacity-based stacking check
        if package is not None:
            ok, reasons = _check_stacking_rules(pl, package, placements)
            if not ok:
                return {"valid": False, "reasons": reasons}

        pkg_len = pa.length_mm if hasattr(pa, 'length_mm') \
                  else getattr(pa, 'length', 0)
        pkg_wid = pa.width_mm if hasattr(pa, 'width_mm') \
                  else getattr(pa, 'width', 0)
        pkg_hei = pa.height_mm if hasattr(pa, 'height_mm') \
                  else getattr(pa, 'height', 0)

        below_aabb = AABB.from_dimensions(
            pl.x, pl.y, pl.z,
            pkg_len, pkg_wid, pkg_hei,
            pl.rotation, clearance=0,
        )
        below_aabbs.append(below_aabb)

    # ── Combined-support coverage ─────────────────────────────────────
    # Grid-sample the candidate's XY footprint and check which sample
    # points fall inside *any* below package AABB.
    cx_min, cx_max = candidate_aabb.xmin, candidate_aabb.xmax
    cy_min, cy_max = candidate_aabb.ymin, candidate_aabb.ymax
    step_x = (cx_max - cx_min) / _GRID_SAMPLES if _GRID_SAMPLES > 0 else 1
    step_y = (cy_max - cy_min) / _GRID_SAMPLES if _GRID_SAMPLES > 0 else 1

    supported_samples = 0
    total_samples = 0
    for i in range(_GRID_SAMPLES):
        px = cx_min + (i + 0.5) * step_x
        for j in range(_GRID_SAMPLES):
            py = cy_min + (j + 0.5) * step_y
            total_samples += 1
            for ba in below_aabbs:
                if ba.xmin <= px <= ba.xmax and ba.ymin <= py <= ba.ymax:
                    supported_samples += 1
                    break

    coverage = supported_samples / total_samples if total_samples > 0 else 0.0
    if coverage < support_threshold:
        return {
            "valid": False,
            "reasons": [
                f"Combined support coverage {coverage:.1%} < "
                f"{support_threshold:.0%} of candidate footprint"
            ],
        }

    # ── Centre-of-mass check: the candidate's XY centre must be
    #    within the XY bounds of at least one below package ──────────
    cx, cy = _footprint_centre(candidate_aabb)
    centre_supported = any(
        ba.xmin <= cx <= ba.xmax and ba.ymin <= cy <= ba.ymax
        for ba in below_aabbs
    )
    if not centre_supported:
        return {
            "valid": False,
            "reasons": [
                f"Candidate footprint centre ({cx:.0f}, {cy:.0f}) not "
                f"supported by any package below"
            ],
        }

    return {"valid": True, "reasons": []}
