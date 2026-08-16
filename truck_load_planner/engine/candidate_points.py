from .package import Package


def _effective_floor_dimensions(package: Package, rotation: int) -> tuple[float, float]:
    if rotation in (90, 270):
        return package.width_mm, package.length_mm
    return package.length_mm, package.width_mm

def _is_valid(planner, package: Package, x: float, y: float, z: float,
              rotation: int) -> bool:
    return planner.validate_position(package, x, y, z, rotation).valid

def _slide_lower_axis(
    planner,
    package: Package,
    x: float,
    y: float,
    z: float,
    rotation: int,
    axis: str,
    step: float,
) -> tuple[float, float]:
    current = x if axis == "x" else y

    for _ in range(200):
        if current <= 0:
            return x, y

        trial = max(0.0, current - step)
        tx = trial if axis == "x" else x
        ty = trial if axis == "y" else y

        if _is_valid(planner, package, tx, ty, z, rotation):
            x, y = tx, ty
            current = trial
            continue

        low = trial
        high = current
        for _ in range(20):
            mid = (low + high) / 2
            tx = mid if axis == "x" else x
            ty = mid if axis == "y" else y
            if _is_valid(planner, package, tx, ty, z, rotation):
                high = mid
            else:
                low = mid

        if high < current:
            tx = high if axis == "x" else x
            ty = high if axis == "y" else y
            if _is_valid(planner, package, tx, ty, z, rotation):
                return tx, ty
        return x, y

    return x, y

def tighten_position(
    planner,
    package: Package,
    x: float,
    y: float,
    z: float,
    rotation: int,
) -> tuple[float, float, float, int]:
    if not _is_valid(planner, package, x, y, z, rotation):
        return x, y, z, rotation

    h_clr = float(getattr(package, "horizontal_clearance_mm", 10.0) or 0.0)
    step = max(50.0, h_clr * 2)

    for _ in range(3):
        old_x, old_y = x, y
        x, y = _slide_lower_axis(planner, package, x, y, z, rotation, "x", step)
        x, y = _slide_lower_axis(planner, package, x, y, z, rotation, "y", step)
        if abs(x - old_x) < 0.001 and abs(y - old_y) < 0.001:
            break

    return x, y, z, rotation

def generate_candidates(
    planner,
    package: Package,
) -> list[dict]:
    # 1. Base geometric anchors from state
    base_points = set(planner.get_candidate_points())

    # 2. Expand rotations
    container = planner.container
    rotations = [0]
    if package.allow_rotation:
        rotations.append(90)

    candidates = []
    seen = set()

    for x, y, z in base_points:
        for rot in rotations:
            _, effective_width = _effective_floor_dimensions(package, rot)
            y_options = {float(y)}
            right_y = container.width - effective_width
            if right_y >= 0:
                y_options.add(float(right_y))

            for candidate_y in y_options:
                if x > container.length or candidate_y > container.width or z > container.height:
                    continue
                key = (x, candidate_y, z, rot)
                if key not in seen:
                    seen.add(key)
                    candidates.append({
                        "x": x,
                        "y": candidate_y,
                        "z": z,
                        "rotation": rot,
                    })

    # Sort candidates by Z (lowest first), then X (deepest first), then Y
    candidates.sort(key=lambda c: (c["z"], c["x"], c["y"]))
    return candidates
