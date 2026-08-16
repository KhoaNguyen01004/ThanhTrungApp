"""
Constraint system — generic container feature detection.
Replaces door.py with a type-driven approach.
Each feature type defines how its geometry translates to an AABB region.
"""

from truck_load_planner.geometry.aabb import AABB


def feature_to_aabb(feature: dict, container_aabb: AABB) -> AABB | None:
    """Convert a container feature to an AABB constraint region.

    Feature types and their geometry_json schemas:
      rear_door  → {"width_mm": ..., "height_mm": ...}
                    Region: very rear of container, full width of door
      side_door  → {"width_mm": ..., "height_mm": ..., "position_from_front_mm": ...}
                    Region: along the right wall at the given position
      lift_gate  → {"width_mm": ..., "capacity_kg": ...}
                    Region: at the rear, similar to rear door
    """
    ftype = feature.get("feature_type", "")
    geo = feature.get("geometry", {})

    if ftype == "rear_door":
        w = geo.get("width_mm", 0)
        h = geo.get("height_mm", 0)
        if w <= 0 or h <= 0:
            return None
        return AABB(
            container_aabb.xmax - 100,
            container_aabb.ymin,
            container_aabb.zmax - h,
            container_aabb.xmax,
            container_aabb.ymin + w,
            container_aabb.zmax,
        )

    if ftype == "side_door":
        w = geo.get("width_mm", 0)
        h = geo.get("height_mm", 0)
        pos = geo.get("position_from_front_mm", 0)
        if w <= 0 or h <= 0:
            return None
        return AABB(
            container_aabb.xmin + pos,
            container_aabb.ymax - w,
            container_aabb.zmax - h,
            container_aabb.xmin + pos + w,
            container_aabb.ymax,
            container_aabb.zmax,
        )

    if ftype == "lift_gate":
        w = geo.get("width_mm", 0)
        if w <= 0:
            return None
        return AABB(
            container_aabb.xmax - 100,
            container_aabb.ymin,
            container_aabb.zmin,
            container_aabb.xmax,
            container_aabb.ymin + w,
            container_aabb.zmax,
        )

    return None


def get_constraint_aabbs(features: list, container_aabb: AABB) -> list:
    """Convert all features to a list of (feature_label, AABB, feature_type) tuples."""
    result = []
    for f in features:
        aabb = feature_to_aabb(f, container_aabb)
        if aabb:
            result.append((f.get("label", f.get("feature_type", "")), aabb, f.get("feature_type", "")))
    return result


def check_constraints(placements: list, features: list, container_aabb: AABB) -> dict:
    """Check all placements against all constraint features.

    Returns:
        {"pass": True} or {"pass": False, "violations": [...]}
    """
    constraints = get_constraint_aabbs(features, container_aabb)
    violations = []

    for label, constraint_aabb, ftype in constraints:
        for p in placements:
            pa = p.get("_aabb")
            if pa and pa.intersects(constraint_aabb):
                # doors, lift gates — just a warning / status
                pass

    if violations:
        return {"pass": False, "violations": violations}

    return {"pass": True, "violations": []}


def get_door_status(placements: list, features: list, container_aabb: AABB) -> dict:
    """Return accessible/blocked status for each door-like feature."""
    result = {}
    for f in features:
        ftype = f.get("feature_type", "")
        if ftype not in ("rear_door", "side_door"):
            continue
        label = f.get("label", ftype)
        aabb = feature_to_aabb(f, container_aabb)
        if aabb is None:
            result[label] = "none"
            continue
        blocked = any(
            p.get("_aabb") and p["_aabb"].intersects(aabb)
            for p in placements
        )
        result[label] = "blocked" if blocked else "accessible"
    return result
