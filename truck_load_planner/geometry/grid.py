"""
Grid snapping utilities.
Pure geometry — no business logic.
"""


def snap_to_grid(value: float, grid_size: float) -> float:
    """Snap a coordinate to the nearest grid step."""
    if grid_size <= 0:
        return value
    return round(value / grid_size) * grid_size


def snap_point(x: float, y: float, grid_size: float):
    """Snap both x and y coordinates to the grid."""
    return snap_to_grid(x, grid_size), snap_to_grid(y, grid_size)
