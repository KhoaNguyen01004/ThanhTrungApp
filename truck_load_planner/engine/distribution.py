from truck_load_planner.engine.package import Package
from truck_load_planner.engine.placement import Placement
from truck_load_planner.engine.trace_mutations import M
from truck_load_planner.engine.candidate_points import generate_candidates, tighten_position
from truck_load_planner.engine.auto_arrange import _run_ordered_pass
from truck_load_planner.engine.vehicle_selection import (
    SmallestVehicleThatFitsStrategy,
    vehicle_capacity,
)


def reassign_load_sequences(placements: list) -> None:
    indexed = list(enumerate(placements))
    indexed.sort(key=lambda e: (e[1].x, e[1].z, e[1].y))
    for seq, (_, pl) in enumerate(indexed, 1):
        if isinstance(pl, Placement):
            old_seq = pl.load_sequence
            pl.load_sequence = seq
            if old_seq != seq:
                M.log("reassign_load_sequences", pl,
                      (pl.x, pl.y, pl.z, pl.rotation),
                      (pl.x, pl.y, pl.z, pl.rotation),
                      f"load_sequence {old_seq}->{seq}")


def find_best_for_pkg(pkg, vinfo, session, remaining_pkgs=None):
    best_score = float("-inf")
    best_pos = None
    planner = session._planner
    
    candidates = generate_candidates(planner, pkg)

    for candidate in candidates:
        tx, ty, tz, trot = tighten_position(
            planner,
            pkg,
            candidate["x"],
            candidate["y"],
            candidate["z"],
            candidate["rotation"],
        )
        
        vresult = planner.validate_position(pkg, tx, ty, tz, trot)
        if not vresult.valid:
            continue

        score = planner.evaluate_position(
            pkg, tx, ty, tz, trot,
            remaining_packages=remaining_pkgs,
        )
        
        if score.total > best_score:
            best_score = score.total
            best_pos = {"x": tx, "y": ty, "z": tz, "rotation": trot}

    return best_score, best_pos


def _vehicle_capacity(vinfo):
    return vehicle_capacity(vinfo)


def distribute_across_vehicles(
    packages,
    vehicle_sessions,
    debug=False,
    profile=None,
    strategy=None,
):
    sorted_pkgs = sorted(
        packages,
        key=lambda p: (
            0 if not p.stackable else 1,
            -p.width_mm,
            -p.length_mm,
            -(p.length_mm * p.width_mm * p.height_mm),
            -p.weight_kg,
        ),
    )

    if strategy is None:
        strategy = SmallestVehicleThatFitsStrategy()
    selected = strategy.select_vehicles(sorted_pkgs, vehicle_sessions, profile)

    placed = 0
    placed_vehicle_map = {vinfo["vehicle_id"]: [] for vinfo, _ in vehicle_sessions}
    remaining_pkgs = list(sorted_pkgs)

    for vinfo, session in selected:
        if not remaining_pkgs:
            break

        preplaced = bool(session._planner.placements)
        if preplaced:
            for pl in session._planner.placements:
                if pl.package:
                    placed += 1
                    placed_vehicle_map[vinfo["vehicle_id"]].append(pl.package.name)
                    if pl.package in remaining_pkgs:
                        remaining_pkgs.remove(pl.package)
            continue

        # Delegate the per-vehicle placement loop to the same
        # candidate/tighten/validate/score/place pipeline the
        # single-vehicle path uses (auto_arrange.py::_run_ordered_pass)
        # instead of a second hand-written copy of it, so scoring/
        # stacking fixes apply identically to both paths.
        pool = list(remaining_pkgs)
        result = _run_ordered_pass(
            session._planner, pool,
            f"distribute_across_vehicles/{vinfo['vehicle_id']}",
            debug=debug,
        )
        placed += result.placed_packages
        for pl in session._planner.placements:
            if pl.package:
                placed_vehicle_map[vinfo["vehicle_id"]].append(pl.package.name)
        still_unplaced = set(result.unplaced_packages)
        remaining_pkgs = [p for p in pool if p.name in still_unplaced]

    failed = len(remaining_pkgs)
    unplaced = [p.name for p in remaining_pkgs]

    for _, session in selected:
        pls = session._planner.placements
        if pls:
            reassign_load_sequences(pls)

    stats = {"rearrangement_attempts": 0}
    return placed, failed, unplaced, placed_vehicle_map, stats
