"""
Backward-compatible re-export module.

The AABB class previously defined here has been merged into the single
canonical implementation at truck_load_planner.geometry.aabb (see that
module's docstring). The coordinate transform helpers previously
duplicated here now live solely in truck_load_planner.geometry.transform.
Both are re-exported so existing ``from truck_load_planner.engine.geometry
import AABB`` / ``import mm_to_px`` etc. call sites keep working unchanged.
"""
from truck_load_planner.geometry.aabb import AABB
from truck_load_planner.geometry.transform import (
    mm_to_px,
    px_to_mm,
    compute_scale,
    rotate_dimensions,
)

__all__ = ["AABB", "mm_to_px", "px_to_mm", "compute_scale", "rotate_dimensions"]
