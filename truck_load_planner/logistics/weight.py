"""
Weight validation — tracks running total and checks against payload.

Delegates to truck_load_planner.engine.weight via adapters.py — see
truck_load_planner/logistics/adapters.py for the dict-placement to
Placement-like-view conversion this requires.
"""

from truck_load_planner.logistics.adapters import calculate_total_weight, check_weight

__all__ = ["calculate_total_weight", "check_weight"]
