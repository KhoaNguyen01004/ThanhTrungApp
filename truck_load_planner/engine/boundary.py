"""
Boundary validation — checks whether a package fits inside the container.
"""

from .geometry import AABB


def check_boundary(package_aabb: AABB, container_aabb: AABB) -> dict:
    if container_aabb.contains(package_aabb):
        return {"pass": True, "errors": []}
    errors = []
    if package_aabb.xmin < container_aabb.xmin:
        errors.append("Package extends beyond front wall")
    if package_aabb.xmax > container_aabb.xmax:
        errors.append("Package extends beyond rear wall")
    if package_aabb.ymin < container_aabb.ymin:
        errors.append("Package extends beyond left wall")
    if package_aabb.ymax > container_aabb.ymax:
        errors.append("Package extends beyond right wall")
    if package_aabb.zmin < container_aabb.zmin:
        errors.append("Package extends below floor")
    if package_aabb.zmax > container_aabb.zmax:
        errors.append("Package exceeds cargo height")
    return {"pass": False, "errors": errors}
