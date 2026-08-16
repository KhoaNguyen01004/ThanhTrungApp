"""
Coordinate transformation utilities.
Pure geometry — no business logic.
"""


def mm_to_px(mm: float, scale: float) -> float:
    """Convert millimeters to pixels at given scale (px per mm)."""
    return mm * scale


def px_to_mm(px: float, scale: float) -> float:
    """Convert pixels to millimeters at given scale."""
    return px / scale


def compute_scale(truck_length_mm: float, truck_width_mm: float,
                  canvas_width_px: int, canvas_height_px: int,
                  margin_px: int = 40) -> float:
    """Compute the scale factor so the truck fits in the canvas with margins."""
    avail_w = canvas_width_px - 2 * margin_px
    avail_h = canvas_height_px - 2 * margin_px
    scale_x = avail_w / truck_length_mm if truck_length_mm else 1
    scale_y = avail_h / truck_width_mm if truck_width_mm else 1
    return min(scale_x, scale_y)


def rotate_dimensions(length: float, width: float, rotation: int):
    """Return (effective_length, effective_width) after rotation.
    Rotation in degrees: 0, 90, 180, 270.
    """
    if rotation % 180 == 90:
        return width, length
    return length, width
