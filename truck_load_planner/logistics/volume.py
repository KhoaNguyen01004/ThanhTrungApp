"""
Volume validation — computes occupied and remaining volume from dimensions.
Volume is NEVER stored; always computed from L × W × H.
"""


def calculate_occupied_m3(placements: list) -> float:
    """Sum volume of all placed packages in m³."""
    total_mm3 = 0.0
    for p in placements:
        pkg = p.get("_package")
        if pkg:
            total_mm3 += pkg.length * pkg.width * pkg.height
        else:
            total_mm3 += p["_length"] * p["_width"] * p["_height"]
    return total_mm3 / 1_000_000_000


def container_volume_m3(length_mm: float, width_mm: float, height_mm: float) -> float:
    """Compute container cargo volume from dimensions in m³."""
    return (length_mm * width_mm * height_mm) / 1_000_000_000


def check_volume(placements: list, length_mm: float, width_mm: float, height_mm: float) -> dict:
    """Check if occupied volume exceeds container cargo volume.

    Returns:
        {"pass": True|False, "occupied_m3": ..., "capacity_m3": ..., "remaining_m3": ...}
    """
    occupied = calculate_occupied_m3(placements)
    capacity = container_volume_m3(length_mm, width_mm, height_mm)
    remaining = capacity - occupied
    if remaining >= -0.001:
        return {"pass": True, "occupied_m3": round(occupied, 4),
                "capacity_m3": round(capacity, 4),
                "remaining_m3": round(remaining, 4)}
    return {"pass": False, "occupied_m3": round(occupied, 4),
            "capacity_m3": round(capacity, 4),
            "remaining_m3": round(remaining, 4),
            "errors": [f"Volume exceeded by {-remaining:.4f} m³"]}
