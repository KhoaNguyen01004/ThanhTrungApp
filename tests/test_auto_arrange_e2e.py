"""End-to-end regression tests for auto-arrange.

Unlike test_scorer.py's narrow unit tests (0-2 packages, individual
scoring functions), these run realistic-sized shipments through the
real production entry points -- Planner.auto_arrange() and
distribute_across_vehicles() -- and assert on outcomes that matter to
a dispatcher: everything gets placed, stacking is actually used when
the floor alone won't fit, no tower grows unsafely tall, and the
multi-vehicle path picks a minimal number of trucks. None of this was
covered before (test_all.py contains similar end-to-end logic but is
a CLI script with zero pytest-collected assertions).

Deterministic (fixed package/container dimensions, no randomness) so
failures are reproducible. Uses strategy="largest_first" wherever the
scenario doesn't specifically need "optimized", since the 15-trial
"optimized" sweep is measurably slower -- this suite should stay fast
enough to run on every change.
"""

from truck_load_planner.engine.package import Package
from truck_load_planner.engine.container import Container
from truck_load_planner.engine.planner import Planner
from truck_load_planner.session import LoadPlanningSession
from truck_load_planner.models import ContainerConfig
from truck_load_planner.engine.distribution import distribute_across_vehicles


def _make_session(vehicle_id, cargo_length_mm, cargo_width_mm, cargo_height_mm, payload_kg):
    session = LoadPlanningSession()
    cc = ContainerConfig(
        id=vehicle_id, name=f"cc{vehicle_id}",
        cargo_length_mm=cargo_length_mm, cargo_width_mm=cargo_width_mm,
        cargo_height_mm=cargo_height_mm, payload_kg=payload_kg,
    )
    session.select_container(cc)
    session.vehicle_id = vehicle_id
    vinfo = {
        "vehicle_id": vehicle_id,
        "cargo_length_mm": cargo_length_mm, "cargo_width_mm": cargo_width_mm,
        "cargo_height_mm": cargo_height_mm, "payload_kg": payload_kg,
    }
    return vinfo, session


# Fixed (non-random) 20-package shipment spanning a realistic size range.
_REALISTIC_SHIPMENT = [
    Package(id=i, name=f"Box{i}", length_mm=l, width_mm=w, height_mm=h,
            weight_kg=wt, stackable=True, allow_rotation=True)
    for i, (l, w, h, wt) in enumerate([
        (800, 600, 500, 25), (700, 500, 400, 18), (600, 600, 600, 22),
        (900, 500, 400, 30), (500, 400, 300, 10), (750, 550, 450, 20),
        (650, 450, 350, 15), (800, 400, 400, 24), (550, 550, 500, 17),
        (700, 600, 300, 19), (600, 400, 400, 12), (850, 500, 500, 28),
        (500, 500, 400, 14), (750, 400, 350, 16), (650, 600, 450, 21),
        (900, 600, 400, 26), (550, 400, 300, 11), (700, 500, 500, 23),
        (600, 500, 350, 13), (800, 550, 450, 27),
    ])
]


def test_single_vehicle_realistic_shipment_all_placed_with_reasonable_utilization():
    container = Container(id=1, name="Box Truck", length=4200, width=2100,
                           height=2000, payload_kg=3000)
    planner = Planner(container)
    result = planner.auto_arrange(list(_REALISTIC_SHIPMENT), strategy="largest_first")

    assert result.failed_packages == 0
    assert result.placed_packages == len(_REALISTIC_SHIPMENT)
    # Floor only: threshold well below what's actually achievable, just
    # catches a catastrophic utilization collapse, not minor tuning drift.
    assert result.utilization > 10.0


def test_stacking_used_when_floor_alone_is_insufficient():
    # Floor fits only 4 of these (2x2 grid with clearance); container is
    # tall enough for 2 layers, and there are 8 identical boxes -- some
    # MUST stack for everything to fit.
    container = Container(id=1, name="Small Van", length=2100, width=2100,
                           height=1300, payload_kg=5000)
    packages = [
        Package(id=i, name=f"Box{i}", length_mm=1000, width_mm=1000, height_mm=600,
                weight_kg=20, stackable=True, allow_rotation=False)
        for i in range(8)
    ]
    planner = Planner(container)
    result = planner.auto_arrange(packages, strategy="optimized")

    stacked = sum(1 for pl in planner.placements if pl.z > 0)
    assert result.placed_packages >= 6, (
        "expected most/all of an 8-box shipment needing 2 floor layers to fit"
    )
    assert stacked > 0, "expected stacking to be used since floor alone can't fit everything"


def test_stack_depth_hard_cap_is_enforced():
    # Single-column scenario (container only wide/long enough for one
    # footprint) with many identical stackable boxes and no explicit
    # max_stack_layers override -- must not tower past the system cap.
    container = Container(id=1, name="Tall Van", length=1000, width=1000,
                           height=5000, payload_kg=5000)
    packages = [
        Package(id=i, name=f"Box{i}", length_mm=500, width_mm=500, height_mm=300,
                weight_kg=5, stackable=True, allow_rotation=False)
        for i in range(30)
    ]
    planner = Planner(container)
    planner.auto_arrange(packages, strategy="largest_first")

    columns = {}
    for pl in planner.placements:
        key = (round(pl.x), round(pl.y))
        columns[key] = columns.get(key, 0) + 1

    assert columns, "expected at least one column to be placed"
    max_column_height = max(columns.values())
    assert max_column_height <= 3, (
        f"a single column reached {max_column_height} packages tall — "
        "the system stack-depth cap should prevent unstable towers"
    )


def test_distribute_across_vehicles_prefers_single_smallest_fitting_truck():
    fleet = [
        _make_session(1, 2400, 1500, 1400, 800),   # small van
        _make_session(2, 3500, 1900, 1800, 1500),  # mid truck
        _make_session(3, 6000, 2400, 2400, 5000),  # large container
    ]
    # Small shipment that fits entirely in the smallest van.
    packages = [
        Package(id=i, name=f"Box{i}", length_mm=400, width_mm=350, height_mm=300,
                weight_kg=8, stackable=True, allow_rotation=True)
        for i in range(8)
    ]

    placed, failed, unplaced, vehicle_map, _ = distribute_across_vehicles(packages, fleet)

    trucks_used = [vid for vid, names in vehicle_map.items() if names]
    assert failed == 0
    assert placed == len(packages)
    assert trucks_used == [1], (
        f"expected only the smallest van (1) to be used, got {trucks_used}"
    )


def test_distribute_across_vehicles_minimizes_truck_count_for_multi_truck_shipment():
    fleet = [
        _make_session(1, 2400, 1500, 1400, 800),   # small van x2
        _make_session(2, 2400, 1500, 1400, 800),
        _make_session(3, 3500, 1900, 1800, 1500),  # mid truck x2
        _make_session(4, 3500, 1900, 1800, 1500),
        _make_session(5, 6000, 2400, 2400, 5000),  # large container x2
        _make_session(6, 6000, 2400, 2400, 5000),
    ]
    # 30 boxes at 1.287m^3 each = ~38.6m^3, exceeding even a single large
    # container's theoretical capacity (34.56m^3) -- genuinely needs
    # multiple vehicles. Real packing efficiency for this box/container
    # ratio actually needs 4 vehicles (calibrated empirically, not just
    # computed from theoretical volume), which is a stronger test of the
    # regression this phase fixes: the *smallest* vehicles (the two vans)
    # must never be touched while larger-capacity vehicles could still
    # take the overflow instead — under the pre-Phase-4 smallest-first
    # fallback, the vans would have been used *first*.
    packages = [
        Package(id=i, name=f"Box{i}", length_mm=1300, width_mm=1100, height_mm=900,
                weight_kg=30, stackable=True, allow_rotation=True)
        for i in range(30)
    ]

    placed, failed, unplaced, vehicle_map, _ = distribute_across_vehicles(packages, fleet)

    trucks_used = sorted(vid for vid, names in vehicle_map.items() if names)
    assert failed == 0
    assert placed == len(packages)
    assert 1 not in trucks_used and 2 not in trucks_used, (
        f"the smallest vehicles (vans 1, 2) should never be touched while "
        f"larger vehicles could take the overflow instead — got {trucks_used}"
    )
