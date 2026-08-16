"""
Collision detection — checks whether two packages (via their AABBs) overlap.
Pure geometry check, no business logic.
"""

from .geometry import AABB


def check_collision(a: AABB, b: AABB) -> bool:
    """Return True if two AABBs overlap (i.e., a collision exists)."""
    return a.intersects(b)
