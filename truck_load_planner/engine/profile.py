from dataclasses import dataclass
from typing import Optional


@dataclass
class PlannerProfile:
    name: str
    candidate_limit: Optional[int] = None
    tighten_step_mm: float = 200.0


FAST = PlannerProfile(
    name="fast",
    tighten_step_mm=200.0,
    candidate_limit=15,
)

BALANCED = PlannerProfile(
    name="balanced",
    tighten_step_mm=200.0,
)

PROFILES: dict[str, PlannerProfile] = {
    "fast": FAST,
    "balanced": BALANCED,
}
