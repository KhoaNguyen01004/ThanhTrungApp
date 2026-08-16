"""
Door access validation.
Ensures packages can be physically inserted through a door
(rear or side) and reach their final position without colliding
with already-placed packages.
"""

import json
from typing import Callable, Optional
from .geometry import AABB
from .package import Package
from .container import Container


def _extract_doors(features: list) -> dict:
    """Extract rear_door from features list (side doors ignored)."""
    rear = None
    for f in features:
        if isinstance(f, dict):
            ftype = f.get("feature_type", "")
            geo = f.get("geometry") or f.get("geometry_json", {})
        else:
            ftype = getattr(f, "feature_type", "")
            geo = getattr(f, "geometry", None) or getattr(f, "geometry_json", {})
        if isinstance(geo, str):
            try:
                geo = json.loads(geo)
            except Exception:
                geo = {}
        if ftype == "rear_door":
            rear = geo
    return {"rear_door": rear, "side_doors": []}


def _sweep_intersects(
    sweep_aabb: AABB,
    placements: list,
    query_aabb_fn: Optional[Callable] = None,
) -> bool:
    """Check if the sweep volume intersects any placed package.

    When *query_aabb_fn* is provided, only candidates from the spatial
    index are checked instead of iterating *placements*.
    """
    if query_aabb_fn:
        for _, paabb in query_aabb_fn(sweep_aabb):
            if sweep_aabb.intersects(paabb):
                return True
        return False
    for pl in placements:
        if pl.package is None:
            continue
        ph_clr = getattr(pl.package, 'horizontal_clearance_mm', 10.0)
        pv_clr = getattr(pl.package, 'vertical_clearance_mm', 0.0)
        paabb = AABB.from_dimensions(
            pl.x, pl.y, pl.z,
            pl.package.length_mm,
            pl.package.width_mm,
            pl.package.height_mm,
            pl.rotation,
            clearance_xy=ph_clr, clearance_z=pv_clr,
        )
        if sweep_aabb.intersects(paabb):
            return True
    return False


def check_rear_door(
    placements: list,
    package: Package,
    aabb: AABB,
    container: Container,
    door_geo: dict,
    rotation: int = 0,
    query_aabb_fn: Optional[Callable] = None,
) -> bool:
    """Check if package can be placed via the rear door.

    Package enters from the rear wall (x=container.length) moving
    inward along -X.  The cross-section (width x height) must fit
    through the door opening, and the sweep volume from the door to
    the final position must be clear of already-placed packages.
    """
    door_w = door_geo.get("width_mm", container.width)
    door_h = door_geo.get("height_mm", container.height)
    if door_w <= 0 or door_h <= 0:
        return False

    pkg_w = package.width_mm if rotation % 180 != 90 else package.length_mm
    pkg_h = package.height_mm

    if pkg_w > door_w or pkg_h > door_h:
        return False

    sweep = AABB(
        aabb.xmin, aabb.ymin, aabb.zmin,
        container.length, aabb.ymax, aabb.zmax,
    )
    return not _sweep_intersects(sweep, placements, query_aabb_fn=query_aabb_fn)


def check_side_door(
    placements: list,
    package: Package,
    aabb: AABB,
    container: Container,
    door_geo: dict,
    right_side: bool,
    rotation: int = 0,
    query_aabb_fn: Optional[Callable] = None,
) -> bool:
    """Check if package can be placed via a side door.

    ``right_side=True`` means door on the right wall (y=container.width),
    ``right_side=False`` means left wall (y=0).

    Package enters along -Y (right) or +Y (left).  The cross-section
    (length x height) must fit through the door opening, the sweep
    volume must be clear, and the package's X-range must overlap the
    door's X-range (so it can be reached from the side).
    """
    door_w = door_geo.get("width_mm", 0)
    door_h = door_geo.get("height_mm", 0)
    door_pos = door_geo.get("position_from_front_mm", 0)
    if door_w <= 0 or door_h <= 0:
        return False

    pkg_l = package.length_mm if rotation % 180 != 90 else package.width_mm
    pkg_h = package.height_mm

    if pkg_l > door_w or pkg_h > door_h:
        return False

    door_x_start = door_pos
    door_x_end = door_pos + door_w
    pkg_x_start = aabb.xmin
    pkg_x_end = aabb.xmax
    if pkg_x_end <= door_x_start or pkg_x_start >= door_x_end:
        return False

    if right_side:
        sweep = AABB(
            aabb.xmin, aabb.ymin, aabb.zmin,
            aabb.xmax, container.width, aabb.zmax,
        )
    else:
        sweep = AABB(
            aabb.xmin, 0, aabb.zmin,
            aabb.xmax, aabb.ymax, aabb.zmax,
        )
    return not _sweep_intersects(sweep, placements, query_aabb_fn=query_aabb_fn)


# ── Progressive door validation (split for Priority 3) ────────────────

def check_door_fit(
    package: Package,
    aabb: AABB,
    container: Container,
    features: list,
    rotation: int = 0,
) -> dict:
    """Cheap check (no sweep): does the package fit through the rear door?

    Side doors are ignored; all containers use a single rear door.
    """
    if not features:
        return {"fits": True, "doors": {}}

    doors = _extract_doors(features)

    if doors["rear_door"]:
        door_w = doors["rear_door"].get("width_mm", container.width)
        door_h = doors["rear_door"].get("height_mm", container.height)
        if door_w > 0 and door_h > 0:
            pkg_w = package.width_mm if rotation % 180 != 90 else package.length_mm
            pkg_h = package.height_mm
            if pkg_w <= door_w and pkg_h <= door_h:
                return {"fits": True, "doors": doors}

    return {
        "fits": False,
        "reasons": ["Package does not fit through rear door opening"],
    }


def check_door_sweep(
    placements: list,
    package: Package,
    aabb: AABB,
    container: Container,
    doors: dict,
    rotation: int = 0,
    query_aabb_fn: Optional[Callable] = None,
) -> dict:
    """Simplified door check — only rear door matters.
    Side doors are ignored; all containers use a single rear door.
    """
    if not doors.get("rear_door"):
        return {"valid": True, "door_used": "none"}
    if check_rear_door(placements, package, aabb, container, doors["rear_door"], rotation=rotation, query_aabb_fn=query_aabb_fn):
        return {"valid": True, "door_used": "rear"}
    return {
        "valid": False,
        "door_used": None,
        "reasons": ["Package cannot reach position through rear door"],
    }


def check_door_access(
    placements: list,
    package: Package,
    aabb: AABB,
    container: Container,
    features: list,
    rotation: int = 0,
    query_aabb_fn: Optional[Callable] = None,
) -> dict:
    """Full door validation (fit + sweep) — backward-compat convenience.

    Prefer calling ``check_door_fit`` then ``check_door_sweep`` separately
    so the expensive sweep only runs when all cheaper checks pass.
    """
    fit = check_door_fit(package, aabb, container, features, rotation=rotation)
    if not fit["fits"]:
        return {"valid": False, "door_used": None, "reasons": fit["reasons"]}
    return check_door_sweep(placements, package, aabb, container, fit["doors"], rotation=rotation, query_aabb_fn=query_aabb_fn)
