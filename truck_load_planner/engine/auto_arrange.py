from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Optional, Callable
from .package import Package
from .candidate_points import generate_candidates, tighten_position
from . import scorer as scorer_mod


@dataclass
class AutoArrangeResult:
    placed_packages: int = 0
    failed_packages: int = 0
    utilization: float = 0.0
    total_score: float = 0.0
    warnings: list[str] = field(default_factory=list)
    unplaced_packages: list[str] = field(default_factory=list)
    placement_count: int = 0
    debug_log: list[dict] = field(default_factory=list)


class AutoArrangeStrategy(Protocol):
    def arrange(
        self,
        planner: Planner,
        packages: list[Package],
        progress_callback: Optional[Callable] = None,
        cancel_callback: Optional[Callable] = None,
        debug: bool = False,
    ) -> AutoArrangeResult:
        ...

def _volume(package: Package) -> float:
    return package.length_mm * package.width_mm * package.height_mm

def _footprint(package: Package) -> float:
    return package.length_mm * package.width_mm

def _largest_first_order(packages: list[Package]) -> list[Package]:
    return sorted(
        packages,
        key=lambda p: (
            0 if not p.stackable else 1,
            -p.width_mm,
            -p.length_mm,
            -_volume(p),
            -p.weight_kg,
        ),
    )

def _run_ordered_pass(
    planner,
    ordered_packages: list[Package],
    trace_label: str,
    progress_callback: Optional[Callable] = None,
    cancel_callback: Optional[Callable] = None,
    debug: bool = False,
) -> AutoArrangeResult:
    result = AutoArrangeResult()
    total = len(ordered_packages)

    for idx, pkg in enumerate(ordered_packages):
        if cancel_callback and cancel_callback():
            result.warnings.append("Auto Arrange cancelled by user")
            break

        expanded = generate_candidates(planner, pkg)

        max_cands = getattr(planner, '_candidate_limit', None)
        if max_cands and len(expanded) > max_cands:
            expanded = expanded[:max_cands]

        best_pos = None
        best_score = float("-inf")
        best_debug_entry = None
        candidates_tried = 0
        all_candidate_details = []

        for candidate in expanded:
            candidates_tried += 1
            candidate_detail = {"input_pos": dict(candidate)}

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
                candidate_detail["valid"] = False
                candidate_detail["reason"] = str(vresult.reasons)
            else:
                candidate_detail["valid"] = True
                candidate_detail["pos"] = {"x": tx, "y": ty, "z": tz, "rotation": trot}
                if (
                    tx != candidate["x"]
                    or ty != candidate["y"]
                    or tz != candidate["z"]
                    or trot != candidate["rotation"]
                ):
                    candidate_detail["tightened_from"] = dict(candidate)

                score = planner.evaluate_position(
                    pkg, tx, ty, tz, trot, debug=False,
                    remaining_packages=ordered_packages[idx + 1:],
                )
                candidate_detail["raw_score"] = round(score.total, 1)
                if hasattr(score, 'breakdown'):
                    candidate_detail["breakdown"] = {
                        k: round(v, 2) for k, v in score.breakdown.items()
                    }
                if score.total > best_score:
                    best_score = score.total
                    best_pos = {"x": tx, "y": ty, "z": tz, "rotation": trot}

            all_candidate_details.append(candidate_detail)

        if best_pos is not None:
            best_debug_entry = {
                "package_name": pkg.name,
                "candidates_evaluated": candidates_tried,
                "all_candidate_details": all_candidate_details,
                "best_score": round(best_score, 1),
                "chosen_position": best_pos,
                "valid_candidates_found": True,
            }

            pkg_name = pkg.name if pkg else "?"
            p_result = planner.place_package(
                pkg, best_pos["x"], best_pos["y"], best_pos["z"],
                best_pos["rotation"],
                _trace_reason=f"{trace_label}/{pkg_name}",
            )
            if p_result.valid:
                result.placed_packages += 1
            else:
                result.failed_packages += 1
                result.unplaced_packages.append(pkg.name)
                if best_debug_entry:
                    best_debug_entry["valid_candidates_found"] = False
        else:
            result.failed_packages += 1
            result.unplaced_packages.append(pkg.name)
            best_debug_entry = {
                "package_name": pkg.name,
                "candidates_evaluated": candidates_tried,
                "best_score": 0.0,
                "chosen_position": None,
                "valid_candidates_found": False,
            }

        if debug and best_debug_entry:
            result.debug_log.append(best_debug_entry)

        if progress_callback:
            progress_callback(
                result.placed_packages + result.failed_packages,
                total,
                best_score if best_score > 0 else 0.0,
            )

    from .distribution import reassign_load_sequences
    reassign_load_sequences(planner.placements)

    stats = planner.get_statistics()
    result.utilization = stats.get("volume_used_pct", 0.0)
    result.placement_count = stats.get("packages_placed", 0)

    plan_score = planner.evaluate_plan()
    result.total_score = round(plan_score.total, 1)

    return result


class LargestFirstStrategy:
    def arrange(
        self,
        planner: Planner,
        packages: list[Package],
        progress_callback: Optional[Callable] = None,
        cancel_callback: Optional[Callable] = None,
        debug: bool = False,
    ) -> AutoArrangeResult:
        return _run_ordered_pass(
            planner,
            _largest_first_order(packages),
            "largest_first/main",
            progress_callback=progress_callback,
            cancel_callback=cancel_callback,
            debug=debug,
        )


class OptimizedStrategy:
    def _orders(self, packages: list[Package]) -> list[tuple[str, list[Package]]]:
        return [
            ("largest", _largest_first_order(packages)),
            ("floor_area", sorted(
                packages,
                key=lambda p: (
                    0 if not p.stackable else 1,
                    -_footprint(p),
                    -p.weight_kg,
                    -_volume(p),
                ),
            )),
            ("long_rows", sorted(
                packages,
                key=lambda p: (
                    0 if not p.stackable else 1,
                    -p.length_mm,
                    -p.width_mm,
                    -_volume(p),
                    -p.weight_kg,
                ),
            )),
            ("wide_rows", sorted(
                packages,
                key=lambda p: (
                    0 if not p.stackable else 1,
                    -p.width_mm,
                    -p.length_mm,
                    -p.weight_kg,
                    -_volume(p),
                ),
            )),
            ("stack_bases", sorted(
                packages,
                key=lambda p: (
                    0 if not p.stackable else 1,
                    -p.weight_kg,
                    -_footprint(p),
                    -p.height_mm,
                ),
            )),
        ]

    def _weight_profiles(self) -> list[tuple[str, dict[str, float]]]:
        # usable_space overrides are independently-tuned absolute values,
        # not multipliers relative to base — left as originally calibrated
        # (2.0/2.5) rather than scaled with the Phase 2 base bump (1->3),
        # which would double-apply the same boost and overweight this term
        # within these profiles. x_position's sign is flipped to match its
        # Phase 2 semantics change (was "prefer small xmin", now "reward
        # slice completion" — higher is better either way), magnitude kept.
        base = dict(scorer_mod.SCORING_WEIGHTS)
        dense = dict(base)
        dense.update({
            "usable_space": 2.0,
            "x_position": 350.0,
            "stack_level": 0.35,
            "tower_height": 0.35,
        })
        stack_friendly = dict(base)
        stack_friendly.update({
            "usable_space": 2.5,
            "x_position": 300.0,
            "contact_area": 1200.0,
            "stack_level": 0.15,
            "tower_height": 0.2,
        })
        return [
            ("safe", base),
            ("dense", dense),
            ("stack_friendly", stack_friendly),
        ]

    def _result_key(self, result: AutoArrangeResult) -> tuple[float, float, float]:
        return (
            result.placed_packages,
            result.utilization,
            result.total_score,
        )

    def arrange(
        self,
        planner,
        packages: list[Package],
        progress_callback: Optional[Callable] = None,
        cancel_callback: Optional[Callable] = None,
        debug: bool = False,
    ) -> AutoArrangeResult:
        initial_plan = planner.export_plan()
        original_weights = dict(scorer_mod.SCORING_WEIGHTS)
        original_limit = getattr(planner, '_candidate_limit', None)
        best_result: Optional[AutoArrangeResult] = None
        best_plan = initial_plan
        trial_summaries = []

        try:
            for weight_name, weights in self._weight_profiles():
                scorer_mod.SCORING_WEIGHTS.clear()
                scorer_mod.SCORING_WEIGHTS.update(weights)
                # Respect whatever candidate_limit the caller configured
                # (e.g. the "fast" profile's cap) instead of discarding it —
                # previously this unconditionally cleared it on every trial.

                for order_name, ordered in self._orders(packages):
                    if cancel_callback and cancel_callback():
                        break

                    planner.import_plan(initial_plan)
                    result = _run_ordered_pass(
                        planner,
                        ordered,
                        f"optimized/{weight_name}/{order_name}",
                        progress_callback=None,
                        cancel_callback=cancel_callback,
                        debug=debug,
                    )
                    summary = {
                        "profile": weight_name,
                        "order": order_name,
                        "placed": result.placed_packages,
                        "failed": result.failed_packages,
                        "utilization": result.utilization,
                        "score": result.total_score,
                    }
                    trial_summaries.append(summary)

                    if (
                        best_result is None
                        or self._result_key(result) > self._result_key(best_result)
                    ):
                        best_result = result
                        best_plan = planner.export_plan()

                    if result.placed_packages == len(packages):
                        break
        finally:
            scorer_mod.SCORING_WEIGHTS.clear()
            scorer_mod.SCORING_WEIGHTS.update(original_weights)
            planner._candidate_limit = original_limit

        planner.import_plan(best_plan)

        if best_result is None:
            best_result = AutoArrangeResult(
                failed_packages=len(packages),
                unplaced_packages=[p.name for p in packages],
            )

        if progress_callback:
            progress_callback(
                best_result.placed_packages + best_result.failed_packages,
                len(packages),
                best_result.total_score,
            )

        best_result.warnings.append("Optimized strategy tried multiple dense packing passes")
        if debug:
            best_result.debug_log.append({
                "optimized_trials": trial_summaries,
            })

        return best_result


class StrategyRegistry:
    _strategies: dict[str, type] = {}

    @classmethod
    def register(cls, name: str, strategy_cls: type) -> None:
        cls._strategies[name] = strategy_cls

    @classmethod
    def get(cls, name: str) -> Optional[type]:
        return cls._strategies.get(name)

    @classmethod
    def list(cls) -> list[str]:
        return list(cls._strategies.keys())


StrategyRegistry.register("largest_first", LargestFirstStrategy)
StrategyRegistry.register("optimized", OptimizedStrategy)
