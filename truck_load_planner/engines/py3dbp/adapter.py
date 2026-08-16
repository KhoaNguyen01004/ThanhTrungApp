import time
from typing import Optional

from py3dbp import Packer, Bin, Item as Py3dbpItem

from truck_load_planner.engine.package import Package
from truck_load_planner.engine.placement import Placement
from truck_load_planner.engine.container import Container
from truck_load_planner.engine.validation import validate_placement
from truck_load_planner.engines.base import PackingEngine, PackingResult, ValidationFailure


class Py3dbpPackingEngine(PackingEngine):
    def __init__(self):
        self._packer = None

    def pack(
        self,
        vehicle,
        packages: list[Package],
        options: Optional[dict] = None,
    ) -> PackingResult:
        start = time.perf_counter()

        bins_processed = 0
        all_placements = []
        vehicle_placements = {}
        vehicle_containers = {}
        validation_failures = []
        remaining = list(packages)

        for vinfo in sorted(vehicle, key=lambda v: -v["cargo_length_mm"] * v["cargo_width_mm"] * v["cargo_height_mm"]):
            if not remaining:
                break

            packer = Packer()
            pybin = Bin(
                name=str(vinfo["vehicle_id"]),
                width=float(vinfo["cargo_width_mm"]),
                height=float(vinfo["cargo_height_mm"]),
                depth=float(vinfo["cargo_length_mm"]),
                max_weight=float(vinfo["payload_kg"]),
            )
            packer.add_bin(pybin)

            pkg_map = {}
            for pkg in remaining:
                pyitem = Py3dbpItem(
                    name=pkg.name,
                    width=float(pkg.width_mm),
                    height=float(pkg.height_mm),
                    depth=float(pkg.length_mm),
                    weight=float(pkg.weight_kg),
                )
                pyitem._package_ref = pkg
                packer.add_item(pyitem)
                pkg_map[id(pyitem)] = pkg

            packer.pack(bigger_first=True, distribute_items=True, number_of_decimals=0)

            container = Container(
                id=vinfo.get("cc_id"),
                name=vinfo.get("container_name", ""),
                length=float(vinfo["cargo_length_mm"]),
                width=float(vinfo["cargo_width_mm"]),
                height=float(vinfo["cargo_height_mm"]),
                payload_kg=float(vinfo["payload_kg"]),
            )
            vehicle_containers[vinfo["vehicle_id"]] = container
            features = vinfo.get("features", [])
            bin_placements = []

            for pyitem in pybin.items:
                pkg = getattr(pyitem, "_package_ref", None)
                if pkg is None:
                    continue

                our_x = float(pyitem.position[2])
                our_y = float(pyitem.position[0])
                our_z = float(pyitem.position[1])

                rot = 0
                placed = False
                for candidate_rot in (0, 90):
                    if not pkg.allow_rotation and candidate_rot != 0:
                        continue
                    result = validate_placement(
                        bin_placements, pkg,
                        our_x, our_y, our_z, candidate_rot,
                        container, features,
                    )
                    if result.valid:
                        rot = candidate_rot
                        placed = True
                        break

                if placed:
                    pl = Placement(
                        package_id=pkg.id or 0,
                        x=our_x, y=our_y, z=our_z,
                        rotation=rot,
                        package=pkg,
                    )
                    bin_placements.append(pl)
                else:
                    validation_failures.append(
                        ValidationFailure(
                            package_name=pkg.name,
                            check="validation",
                            reason="No valid rotation at py3dbp position",
                        )
                    )

            for pyitem in pybin.unfitted_items:
                pkg = getattr(pyitem, "_package_ref", None)
                if pkg:
                    validation_failures.append(
                        ValidationFailure(
                            package_name=pkg.name,
                            check="py3dbp_fit",
                            reason="Could not fit geometrically",
                        )
                    )

            if bin_placements:
                bins_processed += 1
                vehicle_placements[vinfo["vehicle_id"]] = bin_placements
                all_placements.extend(bin_placements)

            placed_ids = {id(pl.package) for pl in bin_placements if pl.package}
            remaining = [p for p in remaining if id(p) not in placed_ids]

        elapsed = (time.perf_counter() - start) * 1000

        return self._build_result(
            all_placements, vehicle_placements, vehicle_containers,
            packages, validation_failures, remaining, elapsed,
        )

    def _build_result(
        self, all_placements, vehicle_placements, vehicle_containers,
        packages, validation_failures, remaining, elapsed_ms,
    ):
        total_placed = len(all_placements)
        total_stacks = sum(1 for pl in all_placements if pl.z > 0)
        total_weight = sum(pl.package.weight_kg for pl in all_placements if pl.package)
        total_volume_mm3 = sum(
            pl.package.length_mm * pl.package.width_mm * pl.package.height_mm
            for pl in all_placements if pl.package
        )
        volume_used_m3 = total_volume_mm3 / 1_000_000_000

        used_container_ids = set()
        for vid, pls in vehicle_placements.items():
            if pls:
                used_container_ids.add(vid)
        total_capacity_m3 = sum(
            vehicle_containers[vid].volume_m3 for vid in used_container_ids
        )
        total_payload = sum(
            vehicle_containers[vid].payload_kg for vid in used_container_ids
        )

        vol_util = (volume_used_m3 / total_capacity_m3 * 100) if total_capacity_m3 > 0 else 0.0
        wt_util = (total_weight / total_payload * 100) if total_payload > 0 else 0.0

        max_stack_height = 0
        for pl in all_placements:
            if pl.package:
                top = pl.z + pl.package.height_mm
                if top > max_stack_height:
                    max_stack_height = top

        stats = {
            "packages_placed": total_placed,
            "weight_used_kg": round(total_weight, 2),
            "volume_used_pct": round(vol_util, 1),
            "weight_used_pct": round(wt_util, 1),
            "vehicles_used": len([v for v in vehicle_placements.values() if v]),
            "stacks": total_stacks,
            "max_stack_height_mm": max_stack_height,
        }

        return PackingResult(
            success=len(all_placements) > 0,
            placements=all_placements,
            unplaced_packages=[p.name for p in remaining],
            vehicle_placements=vehicle_placements,
            vehicle_containers=vehicle_containers,
            statistics=stats,
            runtime_ms=round(elapsed_ms, 2),
            validation_failures=validation_failures,
        )
