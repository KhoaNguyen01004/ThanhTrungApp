"""
Vehicle Cost Model — computes estimated transportation cost for a vehicle.

Kept separate from the geometry engine so that fuel consumption, operating
costs, and other business factors remain independent of packing logic.

Cost factors (configurable via OPTIMIZATION_WEIGHTS):
  - Fuel consumption (L/100km or configured default)
  - Empty volume penalty (unused cargo volume)
  - Empty floor area penalty (unused floor space)
  - Fixed vehicle cost

Usage:
    model = VehicleCostModel(OPTIMIZATION_WEIGHTS)
    cost = model.estimate_cost(vinfo, total_pkg_volume_mm3,
                               total_pkg_weight_kg, largest_pkg_dim)
"""

OPTIMIZATION_WEIGHTS = {
    "fuel_cost_weight": 1.0,
    "empty_volume_penalty_weight": 1.0,
    "empty_floor_area_penalty_weight": 0.5,
    "fixed_vehicle_cost": 0.0,
    "default_fuel_consumption": 12.0,
}

FUEL_COST_PER_L = 1.0


def compute_vehicle_volume_mm3(vinfo):
    return (vinfo.get("cargo_length_mm", 0) *
            vinfo.get("cargo_width_mm", 0) *
            vinfo.get("cargo_height_mm", 0))


def compute_vehicle_floor_mm2(vinfo):
    return (vinfo.get("cargo_length_mm", 0) *
            vinfo.get("cargo_width_mm", 0))


def _get_fuel_consumption(vinfo):
    """Get fuel consumption (L/100km) from vinfo, with fallback to default."""
    normal = vinfo.get("normal_l_per_100km")
    if normal is not None and normal > 0:
        return float(normal)
    return OPTIMIZATION_WEIGHTS.get("default_fuel_consumption", 12.0)


class VehicleCostModel:
    """Computes estimated transportation cost for a vehicle.

    The cost is a weighted sum of fuel consumption (as a relative score),
    expected empty volume, expected empty floor area, and a fixed cost.

    All factors are normalised so the cost is a dimensionless score where
    lower = more economical.
    """

    def __init__(self, weights: dict | None = None):
        self.weights = dict(OPTIMIZATION_WEIGHTS)
        if weights:
            self.weights.update(weights)

    def estimate_cost(
        self,
        vinfo: dict,
        total_pkg_volume_mm3: float = 0,
        total_pkg_weight_kg: float = 0,
        largest_pkg_dim: tuple[float, float, float] | None = None,
    ) -> float:
        """Compute estimated transportation cost.
        Lower = more economical. Used for vehicle ranking before packing.
        """
        cost = 0.0
        vol = compute_vehicle_volume_mm3(vinfo)

        fuel = _get_fuel_consumption(vinfo)
        fuel_score = fuel * self.weights.get("fuel_cost_weight", 1.0) * FUEL_COST_PER_L
        cost += fuel_score

        empty_vol = max(0.0, vol - total_pkg_volume_mm3)
        penalty = (empty_vol / max(vol, 1)) * 100 * self.weights.get("empty_volume_penalty_weight", 1.0)
        cost += penalty

        floor_area = compute_vehicle_floor_mm2(vinfo)
        pkg_floor_estimate = total_pkg_volume_mm3 / max(vinfo.get("cargo_height_mm", 1), 1)
        empty_floor = max(0.0, floor_area - pkg_floor_estimate)
        floor_penalty = (empty_floor / max(floor_area, 1)) * 100 * self.weights.get("empty_floor_area_penalty_weight", 0.5)
        cost += floor_penalty

        cost += self.weights.get("fixed_vehicle_cost", 0.0)

        return cost

    def quick_feasibility_filter(
        self,
        vinfo: dict,
        total_pkg_volume_mm3: float,
        total_pkg_weight_kg: float,
        largest_pkg_dim: tuple[float, float, float],
    ) -> tuple[bool, str]:
        """Quick pre-packing feasibility check.
        Returns (is_feasible, reason) where reason is empty if feasible.
        """
        vol = compute_vehicle_volume_mm3(vinfo)
        if vol <= 0:
            return False, "Vehicle has zero cargo volume"

        if total_pkg_volume_mm3 > 0 and total_pkg_volume_mm3 > vol:
            return False, f"Package volume exceeds vehicle capacity ({total_pkg_volume_mm3:.0f} > {vol:.0f} mm\u00b3)"

        payload = vinfo.get("payload_kg", 0)
        if payload > 0 and total_pkg_weight_kg > payload:
            return False, f"Package weight exceeds payload ({total_pkg_weight_kg:.0f} > {payload:.0f} kg)"

        if largest_pkg_dim:
            l, w, h = largest_pkg_dim
            cl = vinfo.get("cargo_length_mm", 0)
            cw = vinfo.get("cargo_width_mm", 0)
            ch = vinfo.get("cargo_height_mm", 0)
            if (l > cl or w > cw or h > ch) and (w > cl or l > cw or h > ch):
                return False, f"Package dimensions exceed container in all orientations"

        return True, ""

    def evaluate_vehicle_cost(self, vinfo: dict, placements: list) -> float:
        """Compute actual transportation cost for a vehicle after packing.

        Uses actual placed packages to compute real volume utilisation,
        floor utilisation, and fuel score.  Lower = more economical.

        Args:
            vinfo: Vehicle info dict (cargo dimensions, fuel data, etc.).
            placements: List of engine Placement objects in this vehicle.

        Returns:
            Total cost for this vehicle (dimensionless score).
        """
        vol = compute_vehicle_volume_mm3(vinfo)
        if vol <= 0:
            return float("inf")

        actual_pkg_vol = 0.0
        actual_pkg_weight = 0.0
        actual_floor = 0.0
        for pl in placements:
            pkg = pl.package
            if pkg is None:
                continue
            actual_pkg_vol += pkg.length_mm * pkg.width_mm * pkg.height_mm
            actual_pkg_weight += pkg.weight_kg
            if pl.z == 0:
                actual_floor += pkg.length_mm * pkg.width_mm

        cost = 0.0

        fuel = _get_fuel_consumption(vinfo)
        cost += fuel * self.weights.get("fuel_cost_weight", 1.0) * FUEL_COST_PER_L

        empty_vol = max(0.0, vol - actual_pkg_vol)
        vol_penalty = (empty_vol / max(vol, 1)) * 100 * self.weights.get("empty_volume_penalty_weight", 1.0)
        cost += vol_penalty

        floor_area = compute_vehicle_floor_mm2(vinfo)
        empty_floor = max(0.0, floor_area - actual_floor)
        floor_penalty = (empty_floor / max(floor_area, 1)) * 100 * self.weights.get("empty_floor_area_penalty_weight", 0.5)
        cost += floor_penalty

        cost += self.weights.get("fixed_vehicle_cost", 0.0)

        return cost


def compute_fleet_cost(vehicle_sessions) -> float:
    """Compute total transportation cost for a fleet solution.

    Sums the post-packing cost of every vehicle that has at least one
    placement.  Lower = more economical fleet.

    Args:
        vehicle_sessions: List of (vinfo_dict, LoadPlanningSession) tuples.

    Returns:
        Total fleet cost.
    """
    model = VehicleCostModel()
    total = 0.0
    for vinfo, session in vehicle_sessions:
        if not session._planner.placements:
            continue
        total += model.evaluate_vehicle_cost(vinfo, session._planner.placements)
    return total
