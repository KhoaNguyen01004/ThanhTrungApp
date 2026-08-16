import time
from typing import Optional

from truck_load_planner.engine.package import Package
from truck_load_planner.engine.container import Container
from truck_load_planner.engine.distribution import distribute_across_vehicles
from truck_load_planner.engine.statistics import compute_statistics
from truck_load_planner.session import LoadPlanningSession
from truck_load_planner.models import ContainerConfig
from truck_load_planner.engines.base import PackingEngine, PackingResult


class InternalPackingEngine(PackingEngine):
    def pack(
        self,
        vehicle,
        packages: list[Package],
        options: Optional[dict] = None,
    ) -> PackingResult:
        opts = options or {}
        debug = opts.get("debug", False)

        start = time.perf_counter()

        vehicle_sessions = self._build_sessions(vehicle)

        placed, failed, unplaced, _, _ = distribute_across_vehicles(
            packages, vehicle_sessions, debug=debug,
        )

        elapsed = (time.perf_counter() - start) * 1000

        return self._build_result(vehicle_sessions, packages, elapsed)

    def _build_sessions(self, vehicle):
        from truck_load_planner.session import LoadPlanningSession
        sessions = []
        for vinfo in vehicle:
            cc = ContainerConfig(
                id=vinfo["cc_id"],
                name=vinfo.get("container_name", ""),
                cargo_length_mm=vinfo["cargo_length_mm"],
                cargo_width_mm=vinfo["cargo_width_mm"],
                cargo_height_mm=vinfo["cargo_height_mm"],
                payload_kg=vinfo["payload_kg"],
            )
            session = LoadPlanningSession()
            session.select_container(cc)
            session.vehicle_id = vinfo["vehicle_id"]
            sessions.append((vinfo, session))
        return sessions

    def _build_result(self, vehicle_sessions, packages, elapsed_ms):
        all_placements = []
        vehicle_placements = {}
        vehicle_containers = {}
        total_placed = 0

        for vinfo, session in vehicle_sessions:
            planner = session._planner
            placements = list(planner.placements)
            if not placements:
                continue
            vid = vinfo["vehicle_id"]
            vehicle_placements[vid] = placements
            vehicle_containers[vid] = planner.container
            all_placements.extend(placements)
            total_placed += len(placements)

        stats = self._compute_fleet_stats(vehicle_sessions)

        return PackingResult(
            success=len(all_placements) > 0,
            placements=all_placements,
            unplaced_packages=[p.name for p in packages
                              if not any(id(p) == id(pl.package)
                                        for pl in all_placements)],
            vehicle_placements=vehicle_placements,
            vehicle_containers=vehicle_containers,
            statistics=stats,
            runtime_ms=round(elapsed_ms, 2),
        )

    def _compute_fleet_stats(self, vehicle_sessions):
        total_placed = 0
        total_weight = 0.0
        total_volume_mm3 = 0.0
        total_capacity_m3 = 0.0
        total_payload = 0.0
        total_stacks = 0
        max_stack_height = 0
        used_vehicles = 0

        for vinfo, session in vehicle_sessions:
            planner = session._planner
            placements = planner.placements
            container = planner.container
            if not placements:
                continue
            used_vehicles += 1
            stats = compute_statistics(placements, container)
            total_placed += stats["packages_placed"]
            total_weight += stats["weight_used_kg"]
            total_capacity_m3 += container.volume_m3
            total_payload += container.payload_kg

            for pl in placements:
                if pl.package is None:
                    continue
                total_volume_mm3 += pl.package.length_mm * pl.package.width_mm * pl.package.height_mm
                if pl.z > 0:
                    total_stacks += 1

            for pl in placements:
                if pl.package is None:
                    continue
                top = pl.z + pl.package.height_mm
                if top > max_stack_height:
                    max_stack_height = top

        volume_used_m3 = total_volume_mm3 / 1_000_000_000
        vol_util = (volume_used_m3 / total_capacity_m3 * 100) if total_capacity_m3 > 0 else 0.0
        wt_util = (total_weight / total_payload * 100) if total_payload > 0 else 0.0

        return {
            "packages_placed": total_placed,
            "weight_used_kg": round(total_weight, 2),
            "volume_used_pct": round(vol_util, 1),
            "weight_used_pct": round(wt_util, 1),
            "vehicles_used": used_vehicles,
            "stacks": total_stacks,
            "max_stack_height_mm": max_stack_height,
        }
