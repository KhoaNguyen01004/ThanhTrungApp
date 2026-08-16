"""
Boundary validation — checks if a package fits inside the truck container.

Delegates to truck_load_planner.engine.boundary via adapters.py — see
truck_load_planner/logistics/adapters.py for why this is a safe direct
delegate (identical AABB type on both sides after Section 6.2.2's
unification, identical logic already).
"""

from truck_load_planner.logistics.adapters import check_boundary

__all__ = ["check_boundary"]
