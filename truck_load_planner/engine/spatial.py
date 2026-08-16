"""
Uniform Grid spatial index.

Divides the container into fixed-size cells. Each placed package is
registered in every cell its AABB overlaps. Queries return only packages
whose cells intersect the query AABB, dramatically reducing pair checks.
"""

from .geometry import AABB
from .placement import Placement


class UniformGrid:
    """3D uniform grid for fast AABB overlap queries.

    Cell size is auto-tuned from container dimensions, clamped to
    a reasonable range. Typical reduction: query returns O(cell_count)
    candidates instead of O(N).
    """

    def __init__(self, cell_size: float = 500.0):
        self.cell_size = max(cell_size, 100.0)
        self._cells: dict[tuple[int, int, int], list[tuple[Placement, AABB]]] = {}
        self._all: list[tuple[Placement, AABB]] = []

    # ── Mutations ──────────────────────────────────────────────────────

    def insert(self, placement: Placement, aabb: AABB) -> None:
        """Register a placement and its AABB in the grid."""
        self._all.append((placement, aabb))
        for cell in self._cell_keys(aabb):
            self._cells.setdefault(cell, []).append((placement, aabb))

    def remove(self, placement: Placement) -> None:
        """Remove a placement (linear scan — only called on user operations)."""
        before = len(self._all)
        self._all = [(p, a) for p, a in self._all if p is not placement]
        if len(self._all) < before:
            self._rebuild()

    def clear(self) -> None:
        self._cells.clear()
        self._all.clear()

    # ── Query ──────────────────────────────────────────────────────────

    def query(self, aabb: AABB) -> list[tuple[Placement, AABB]]:
        """Return (placement, aabb) pairs whose cells overlap *aabb*.

        Returns each placement at most once.  The caller must still
        perform exact intersection tests on the returned candidates.
        """
        seen: set[int] = set()
        results: list[tuple[Placement, AABB]] = []
        for cell in self._cell_keys(aabb):
            for pair in self._cells.get(cell, ()):
                pid = id(pair[0])
                if pid not in seen:
                    seen.add(pid)
                    results.append(pair)
        return results

    def has_intersections(self, aabb: AABB) -> bool:
        """Fast check whether anything overlaps *aabb* (early exit)."""
        for cell in self._cell_keys(aabb):
            for placement, paabb in self._cells.get(cell, ()):
                if aabb.intersects(paabb):
                    return True
        return False

    # ── Internal ───────────────────────────────────────────────────────

    def _cell_keys(self, aabb: AABB) -> set[tuple[int, int, int]]:
        """Return all grid cell keys that *aabb* overlaps."""
        cs = self.cell_size
        keys: set[tuple[int, int, int]] = set()
        for x in range(int(aabb.xmin // cs), int(aabb.xmax // cs) + 1):
            for y in range(int(aabb.ymin // cs), int(aabb.ymax // cs) + 1):
                for z in range(int(aabb.zmin // cs), int(aabb.zmax // cs) + 1):
                    keys.add((x, y, z))
        return keys

    def _rebuild(self) -> None:
        self._cells.clear()
        for placement, aabb in self._all:
            for cell in self._cell_keys(aabb):
                self._cells.setdefault(cell, []).append((placement, aabb))
