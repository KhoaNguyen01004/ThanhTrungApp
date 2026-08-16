"""
Statistics engine — computes all KPIs from placements and container.
"""

from .container import Container
from .placement import Placement


def compute_statistics(
    placements: list,
    container: Container,
) -> dict:
    """Compute loading statistics for the current plan.

    Returns:
        {
            "packages_placed": int,
            "weight_used_kg": float,
            "weight_remaining_kg": float,
            "volume_used_m3": float,
            "volume_remaining_m3": float,
            "volume_used_pct": float,
            "floor_used_pct": float,
        }
    """
    packages_placed = len(placements)

    weight_used = 0.0
    volume_mm3 = 0.0
    floor_footprints = []

    for pl in placements:
        pkg = pl.package
        if pkg is None:
            continue
        weight_used += pkg.weight_kg
        volume_mm3 += pkg.length_mm * pkg.width_mm * pkg.height_mm

        if pl.z == 0:
            floor_footprints.append(
                pkg.length_mm * pkg.width_mm
            )

    volume_used_m3 = volume_mm3 / 1_000_000_000
    capacity_m3 = container.volume_m3
    volume_remaining = max(0.0, capacity_m3 - volume_used_m3)
    volume_pct = (volume_used_m3 / capacity_m3 * 100) if capacity_m3 > 0 else 0.0

    floor_area = container.length * container.width
    floor_used = sum(floor_footprints)
    floor_pct = (floor_used / floor_area * 100) if floor_area > 0 else 0.0

    return {
        "packages_placed": packages_placed,
        "weight_used_kg": round(weight_used, 2),
        "weight_remaining_kg": round(max(0, container.payload_kg - weight_used), 2),
        "volume_used_m3": round(volume_used_m3, 4),
        "volume_remaining_m3": round(volume_remaining, 4),
        "volume_used_pct": round(volume_pct, 1),
        "floor_used_pct": round(floor_pct, 1),
    }
