"""
Placement orchestrator — coordinates all validation checks before accepting a placement.
"""

from truck_load_planner.geometry.aabb import AABB
from truck_load_planner.logistics.boundary import check_boundary
from truck_load_planner.logistics.weight import check_weight
from truck_load_planner.logistics.volume import check_volume
from truck_load_planner.logistics.constraints import check_constraints


def try_place(placements: list, package, container_aabb: AABB,
              features: list, payload_kg: float,
              x: float, y: float, z: float,
              rotation: int = 0) -> dict:
    """Validate whether a package can be placed at (x, y, z).

    Args:
        placements: Current list of placed package dicts
        package: Package dataclass with dimensions
        container_aabb: AABB of the container interior
        features: List of container feature dicts
        payload_kg: Max payload in kg
        x, y, z: Coordinates in mm
        rotation: 0, 90, 180, 270

    Returns:
        {"accepted": True, "placement": {...}} or
        {"accepted": False, "errors": [...], "warnings": [...]}
    """
    errors = []
    warnings = []

    # Build candidate AABB
    candidate = AABB.from_dimensions(
        x, y, z,
        package.length, package.width, package.height,
        rotation
    )

    # 1. Boundary check
    boundary_result = check_boundary(candidate, container_aabb)
    if not boundary_result["pass"]:
        errors.extend(boundary_result.get("errors", []))

    # 2. Collision check against existing placements
    for p in placements:
        existing = p.get("_aabb")
        if existing and candidate.intersects(existing):
            errors.append(f"Collision with {p.get('_name', 'package')}")

    # 3. Constraint check (doors, lift gates — status only)
    constraint_result = check_constraints(
        placements + [{"_aabb": candidate, "_package": package}],
        features, container_aabb
    )
    if not constraint_result["pass"]:
        errors.extend(constraint_result.get("violations", []))

    # 4. Weight check
    simulated = placements + [{
        "_weight_kg": package.weight_kg,
        "_length": package.length,
        "_width": package.width,
        "_height": package.height,
        "_aabb": candidate,
    }]
    weight_result = check_weight(simulated, payload_kg)
    if not weight_result["pass"]:
        errors.extend(weight_result.get("errors", []))
    if weight_result.get("remaining_kg", 0) < payload_kg * 0.1:
        warnings.append("Approaching payload limit")

    # 5. Volume check
    cl = container_aabb.xmax - container_aabb.xmin
    cw = container_aabb.ymax - container_aabb.ymin
    ch = container_aabb.zmax - container_aabb.zmin
    volume_result = check_volume(simulated, cl, cw, ch)
    if not volume_result["pass"]:
        errors.extend(volume_result.get("errors", []))

    if errors:
        return {"accepted": False, "errors": errors, "warnings": warnings}

    placement = {
        "package_id": package.id,
        "x": x,
        "y": y,
        "z": z,
        "rotation": rotation,
        "_name": package.name,
        "_weight_kg": package.weight_kg,
        "_length": package.length,
        "_width": package.width,
        "_height": package.height,
        "_aabb": candidate,
        "_package": package,
    }

    return {"accepted": True, "placement": placement, "warnings": warnings}
