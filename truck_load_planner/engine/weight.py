"""
Weight validation — tracks running total and checks against payload.
No placement logic.
"""


def calculate_total_weight(placements: list) -> float:
    total = 0.0
    for p in placements:
        if p.package:
            total += p.package.weight_kg
        else:
            total += getattr(p, "_weight_kg", 0)
    return total


def check_weight(placements: list, payload_kg: float) -> dict:
    current = calculate_total_weight(placements)
    remaining = payload_kg - current
    if remaining >= 0:
        return {
            "pass": True,
            "current_kg": current,
            "payload_kg": payload_kg,
            "remaining_kg": remaining,
        }
    return {
        "pass": False,
        "current_kg": current,
        "payload_kg": payload_kg,
        "remaining_kg": remaining,
        "errors": [f"Weight exceeded by {-remaining:.1f} kg"],
    }
