"""
Axis-Aligned Bounding Box (AABB) operations.
Pure geometry — no business logic.

This is the single canonical AABB class, merged from the two
previously-diverged implementations that used to live here (a basic
version with no clearance support) and in truck_load_planner/engine/geometry.py
(a clearance-aware superset with point-containment and overlap helpers).
truck_load_planner.engine.geometry now re-exports this class so existing
``from truck_load_planner.engine.geometry import AABB`` imports keep
working unchanged.
"""


class AABB:
    """An axis-aligned bounding box defined by min/max corners."""

    __slots__ = ("xmin", "ymin", "zmin", "xmax", "ymax", "zmax")

    def __init__(self, xmin: float, ymin: float, zmin: float,
                 xmax: float, ymax: float, zmax: float):
        self.xmin = xmin
        self.ymin = ymin
        self.zmin = zmin
        self.xmax = xmax
        self.ymax = ymax
        self.zmax = zmax

    @classmethod
    def from_dimensions(cls, x: float, y: float, z: float,
                        length_mm: float, width_mm: float, height_mm: float,
                        rotation: int = 0, clearance: float = 0,
                        clearance_xy: float = None, clearance_z: float = None):
        """Create AABB for a package at (x,y,z) with given dimensions.

        Rotation 0/180: length→X axis, width→Y axis.
        Rotation 90/270: length→Y axis, width→X axis.

        With clearance=0 (the default), this produces a tight bounding
        box. Pass clearance / clearance_xy / clearance_z to pad the box
        outward — used for collision and door-sweep checks that need
        breathing room between packages.
        """
        if clearance_xy is None:
            clearance_xy = clearance
        if clearance_z is None:
            clearance_z = clearance
        if rotation in (90, 270):
            dx = width_mm
            dy = length_mm
        else:
            dx = length_mm
            dy = width_mm
        return cls(x - clearance_xy, y - clearance_xy, z - clearance_z,
                   x + dx + clearance_xy, y + dy + clearance_xy, z + height_mm + clearance_z)

    @property
    def width_x(self) -> float:
        return self.xmax - self.xmin

    @property
    def width_y(self) -> float:
        return self.ymax - self.ymin

    @property
    def width_z(self) -> float:
        return self.zmax - self.zmin

    @property
    def volume(self) -> float:
        return self.width_x * self.width_y * self.width_z

    def intersects(self, other: "AABB") -> bool:
        """Check if two AABBs overlap in 3D space."""
        return (
            self.xmin < other.xmax and self.xmax > other.xmin
            and self.ymin < other.ymax and self.ymax > other.ymin
            and self.zmin < other.zmax and self.zmax > other.zmin
        )

    def contains(self, other: "AABB") -> bool:
        """Check if this AABB fully contains another."""
        return (
            self.xmin <= other.xmin and self.xmax >= other.xmax
            and self.ymin <= other.ymin and self.ymax >= other.ymax
            and self.zmin <= other.zmin and self.zmax >= other.zmax
        )

    def contains_point(self, x: float, y: float, z: float, tol: float = 0.001) -> bool:
        return (
            self.xmin - tol <= x <= self.xmax + tol
            and self.ymin - tol <= y <= self.ymax + tol
            and self.zmin - tol <= z <= self.zmax + tol
        )

    def strictly_contains_point(self, x: float, y: float, z: float, tol: float = 0.001) -> bool:
        """Check if point is strictly inside (exclusive on max boundaries).

        A point on the right/front/top face of a package is a valid
        adjacent position, not an occupied one, so the max boundary
        is excluded.

        ``xmin - tol <= x < xmax`` — the tolerance on the min side
        catches floating-point near-zero; the strict ``< xmax``
        allows points exactly on the right/front/top face.
        """
        return (
            self.xmin - tol <= x < self.xmax
            and self.ymin - tol <= y < self.ymax
            and self.zmin - tol <= z < self.zmax
        )

    def translate(self, dx: float = 0, dy: float = 0, dz: float = 0) -> "AABB":
        return AABB(
            self.xmin + dx, self.ymin + dy, self.zmin + dz,
            self.xmax + dx, self.ymax + dy, self.zmax + dz,
        )

    def overlap_area_xy(self, other: "AABB") -> float:
        dx = max(0, min(self.xmax, other.xmax) - max(self.xmin, other.xmin))
        dy = max(0, min(self.ymax, other.ymax) - max(self.ymin, other.ymin))
        return dx * dy
