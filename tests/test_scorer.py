import pytest

from truck_load_planner.engine.package import Package
from truck_load_planner.engine.placement import Placement
from truck_load_planner.engine.container import Container
from truck_load_planner.engine.planner import Planner
from truck_load_planner.engine.candidate_points import (
    generate_candidates,
    tighten_position,
)
from truck_load_planner.engine.scorer import (
    score_placement,
    _score_package_contact,
    _score_stack_and_tower,
    _score_y_balance,
    _score_usable_space,
    _make_aabb,
    _build_others_with_layers,
    SCORING_WEIGHTS,
    PlacementScore,
)
from truck_load_planner.engine.auto_arrange import StrategyRegistry
from truck_load_planner.engine.geometry import AABB


PACKAGE = Package(id=1, name="Box", length_mm=1000, width_mm=800,
                  height_mm=600, weight_kg=50, stackable=True)

CONTAINER = Container(
    id=1, name="40ft Container",
    length=12000, width=2400, height=2700, payload_kg=28000,
)


def _make(pkg: Package, x: float, y: float, z: float,
          rotation: int = 0) -> Placement:
    return Placement(
        package_id=pkg.id or 0, x=x, y=y, z=z,
        rotation=rotation, package=pkg,
    )


def test_determinism():
    placements = [_make(Package(id=2, name="A", length_mm=500,
                                width_mm=500, height_mm=500), 0, 0, 0)]
    s1 = score_placement(PACKAGE, 1200, 0, 0, 0, placements, CONTAINER)
    s2 = score_placement(PACKAGE, 1200, 0, 0, 0, placements, CONTAINER)
    assert s1.total == s2.total
    assert s1.breakdown == s2.breakdown


def test_stack_and_tower_on_floor():
    aabb = _make_aabb(PACKAGE, 0, 0, 0, 0)
    stack, tower = _score_stack_and_tower(aabb, [])
    assert stack == 200.0
    assert tower == 100.0


def test_stack_and_tower_floating():
    aabb = _make_aabb(PACKAGE, 0, 0, 500, 0)
    stack, tower = _score_stack_and_tower(aabb, [])
    assert stack == 150.0  # Assumes 1 layer since it's floating
    assert tower == 60.0


def test_stack_and_tower_stacked():
    placements = [_make(PACKAGE, 0, 0, 0, 0)]
    others = _build_others_with_layers(placements)
    aabb = _make_aabb(PACKAGE, 0, 0, 600, 0)
    stack, tower = _score_stack_and_tower(aabb, others)
    assert stack == 150.0
    assert tower == 60.0


def test_package_contact_no_neighbors():
    aabb = _make_aabb(PACKAGE, 5000, 500, 0, 0)
    assert _score_package_contact(aabb, []) == 0.0


def test_package_contact_side_by_side():
    aabb = _make_aabb(PACKAGE, 1000, 0, 0, 0)
    neighbor = Package(id=2, name="Neighbor", length_mm=1000,
                       width_mm=800, height_mm=600)
    neighbor_aabb = _make_aabb(neighbor, 0, 0, 0, 0)
    score = _score_package_contact(aabb, [neighbor_aabb])
    assert score > 0.0
    assert score <= 1.0


def test_package_contact_full_face():
    box = Package(id=1, name="Box", length_mm=1000,
                  width_mm=1000, height_mm=1000)
    aabb = _make_aabb(box, 1000, 0, 0, 0)
    other_aabb = _make_aabb(box, 0, 0, 0, 0)
    score = _score_package_contact(aabb, [other_aabb])
    assert score > 0.0
    assert score <= 1.0


def test_y_balance_centered():
    w = CONTAINER.width
    pkg = Package(id=2, name="Center", length_mm=500, width_mm=500,
                  height_mm=500, weight_kg=50)
    aabb = _make_aabb(pkg, 0, (w - 500) / 2, 0, 0)
    score = _score_y_balance(aabb, pkg, [], CONTAINER)
    assert score == pytest.approx(1.0, abs=0.01)


def test_y_balance_edge():
    pkg = Package(id=2, name="Edge", length_mm=500, width_mm=500,
                  height_mm=500, weight_kg=50)
    aabb = _make_aabb(pkg, 0, 0, 0, 0)
    score = _score_y_balance(aabb, pkg, [], CONTAINER)
    assert score < 0.5


def test_usable_space_no_remaining_packages_neutral():
    aabb = _make_aabb(PACKAGE, 0, 0, 0, 0)
    assert _score_usable_space(aabb, [], CONTAINER, []) == 0.0
    assert _score_usable_space(aabb, [], CONTAINER, None) == 0.0


def test_usable_space_penalizes_dead_strip():
    wide = Package(id=10, name="Wide", length_mm=1000, width_mm=1900,
                   height_mm=600)
    remaining = [
        Package(id=11, name="TooWideA", length_mm=1200, width_mm=600,
                height_mm=500),
        Package(id=12, name="TooWideB", length_mm=1300, width_mm=700,
                height_mm=500),
    ]
    aabb = _make_aabb(wide, 0, 0, 0, 0)

    assert _score_usable_space(aabb, [], CONTAINER, remaining) == -500.0


def test_usable_space_rewards_rotation_that_keeps_fit_width():
    pkg = Package(id=10, name="Rotating", length_mm=1600, width_mm=900,
                  height_mm=600, weight_kg=50)
    remaining = [
        Package(id=11, name="FitsA", length_mm=1200, width_mm=1000,
                height_mm=500),
        Package(id=12, name="FitsB", length_mm=1300, width_mm=1100,
                height_mm=500),
    ]

    rot0 = _score_usable_space(_make_aabb(pkg, 0, 0, 0, 0),
                               [], CONTAINER, remaining)
    rot90 = _score_usable_space(_make_aabb(pkg, 0, 0, 0, 90),
                                [], CONTAINER, remaining)

    assert rot0 == pytest.approx(406.25)
    assert rot90 == -500.0


def test_usable_space_penalizes_dead_strip_even_with_usable_other_side():
    wall = Package(id=10, name="Wall", length_mm=1000, width_mm=800,
                   height_mm=600)
    candidate = Package(id=11, name="Candidate", length_mm=1000,
                        width_mm=800, height_mm=600)
    remaining = [
        Package(id=12, name="Small", length_mm=700, width_mm=250,
                height_mm=500),
        Package(id=13, name="Large", length_mm=900, width_mm=650,
                height_mm=500),
    ]
    others = [_make_aabb(wall, 0, 0, 0, 0)]
    aabb = _make_aabb(candidate, 0, 1000, 0, 0)

    assert _score_usable_space(aabb, others, CONTAINER, remaining) == -500.0


def test_usable_space_prefers_wider_rotation_when_gaps_stay_usable():
    pkg = Package(id=10, name="Rotating", length_mm=1600, width_mm=900,
                  height_mm=600, weight_kg=50)
    remaining = [
        Package(id=11, name="SmallA", length_mm=900, width_mm=700,
                height_mm=500),
        Package(id=12, name="SmallB", length_mm=1000, width_mm=700,
                height_mm=500),
    ]

    rot0 = _score_usable_space(_make_aabb(pkg, 0, 0, 0, 0),
                               [], CONTAINER, remaining)
    rot90 = _score_usable_space(_make_aabb(pkg, 0, 0, 0, 90),
                                [], CONTAINER, remaining)

    assert rot90 > rot0


def test_placement_score_to_dict():
    score = PlacementScore(
        total=85.3,
        breakdown={"contact_area": 50.0, "x_position": 20.0},
        warnings=["Test warning"],
        metadata={"key": "value"},
    )
    d = score.to_dict()
    assert d["total"] == 85.3
    assert d["breakdown"]["contact_area"] == 50.0
    assert d["warnings"] == ["Test warning"]
    assert d["metadata"]["key"] == "value"


def test_score_placement_returns_placementscore():
    result = score_placement(
        PACKAGE, 0, 0, 0, 0, [], CONTAINER,
    )
    assert isinstance(result, PlacementScore)
    assert "contact_area" in result.breakdown
    assert "x_position" in result.breakdown
    assert "stack_level" in result.breakdown
    assert "tower_height" in result.breakdown
    assert "weight_balance" in result.breakdown
    assert "usable_space" in result.breakdown


def test_score_placement_deterministic():
    placements = [_make(Package(id=3, name="Other", length_mm=400,
                                width_mm=400, height_mm=400), 2000, 0, 0)]
    r1 = score_placement(
        PACKAGE, 1000, 0, 0, 0, placements, CONTAINER,
    )
    r2 = score_placement(
        PACKAGE, 1000, 0, 0, 0, placements, CONTAINER,
    )
    assert r1.total == r2.total
    assert r1.breakdown == r2.breakdown
    assert r1.warnings == r2.warnings


def test_weights_are_configurable():
    assert "contact_area" in SCORING_WEIGHTS
    assert "x_position" in SCORING_WEIGHTS
    assert "stack_level" in SCORING_WEIGHTS
    assert "tower_height" in SCORING_WEIGHTS
    assert "weight_balance" in SCORING_WEIGHTS
    assert "usable_space" in SCORING_WEIGHTS


def test_score_placement_prefers_usable_rotation():
    pkg = Package(id=10, name="Rotating", length_mm=1600, width_mm=900,
                  height_mm=600, weight_kg=50)
    remaining = [
        Package(id=11, name="FitsA", length_mm=900, width_mm=700,
                height_mm=500),
        Package(id=12, name="FitsB", length_mm=1000, width_mm=700,
                height_mm=500),
    ]

    rot0 = score_placement(
        pkg, 0, 0, 0, 0, [], CONTAINER, remaining_packages=remaining,
    )
    rot90 = score_placement(
        pkg, 0, 0, 0, 90, [], CONTAINER, remaining_packages=remaining,
    )

    assert rot90.breakdown["usable_space"] > rot0.breakdown["usable_space"]
    assert rot90.total > rot0.total


def test_generate_candidates_adds_rotation_aware_right_wall_anchor():
    planner = Planner(CONTAINER)
    pkg = Package(id=10, name="Rotating", length_mm=1600, width_mm=900,
                  height_mm=600, allow_rotation=True)

    candidates = generate_candidates(planner, pkg)

    assert {"x": 0, "y": 1500.0, "z": 0, "rotation": 0} in candidates
    assert {"x": 0, "y": 800.0, "z": 0, "rotation": 90} in candidates


def test_tighten_position_pushes_candidate_to_front():
    planner = Planner(CONTAINER)
    blocker = Package(id=10, name="Blocker", length_mm=1000, width_mm=500,
                      height_mm=500, horizontal_clearance_mm=0)
    moving = Package(id=11, name="Moving", length_mm=700, width_mm=500,
                     height_mm=500, horizontal_clearance_mm=0)
    assert planner.place_package(blocker, 0, 1000, 0, 0).valid

    x, y, z, rotation = tighten_position(planner, moving, 2000, 0, 0, 0)

    assert x == pytest.approx(0.0, abs=0.01)
    assert y == pytest.approx(0.0, abs=0.01)
    assert z == 0
    assert rotation == 0


def test_tighten_position_closes_middle_y_gap():
    planner = Planner(CONTAINER)
    blocker = Package(id=10, name="Blocker", length_mm=1000, width_mm=800,
                      height_mm=500, horizontal_clearance_mm=0)
    moving = Package(id=11, name="Moving", length_mm=700, width_mm=500,
                     height_mm=500, horizontal_clearance_mm=0)
    assert planner.place_package(blocker, 0, 0, 0, 0).valid

    x, y, _, _ = tighten_position(planner, moving, 0, 1800, 0, 0)

    assert x == pytest.approx(0.0, abs=0.01)
    assert y == pytest.approx(800.0, abs=0.01)


def test_auto_arrange_uses_remaining_packages_for_rotation_choice():
    planner = Planner(CONTAINER)
    packages = [
        Package(id=10, name="Rotating", length_mm=1600, width_mm=900,
                height_mm=600, weight_kg=50, allow_rotation=True),
        Package(id=11, name="Future", length_mm=900, width_mm=700,
                height_mm=500, weight_kg=30, allow_rotation=True),
    ]

    result = planner.auto_arrange(packages)

    assert result.placed_packages == 2
    assert planner.placements[0].rotation == 90


def test_optimized_strategy_registered_and_restores_weights():
    assert "optimized" in StrategyRegistry.list()
    original_weights = dict(SCORING_WEIGHTS)
    planner = Planner(CONTAINER)
    packages = [
        Package(id=10, name="Base", length_mm=1200, width_mm=1000,
                height_mm=500, weight_kg=80, stackable=True,
                allow_rotation=True),
        Package(id=11, name="Top", length_mm=900, width_mm=700,
                height_mm=400, weight_kg=30, stackable=True,
                allow_rotation=True),
    ]

    result = planner.auto_arrange(packages, strategy="optimized")

    assert result.placed_packages == 2
    assert dict(SCORING_WEIGHTS) == original_weights


def test_zero_sized_package():
    tiny = Package(id=99, name="Tiny", length_mm=1, width_mm=1,
                   height_mm=1)
    result = score_placement(tiny, 0, 0, 0, 0, [], CONTAINER)
    assert isinstance(result, PlacementScore)


def test_empty_placements_list():
    result = score_placement(PACKAGE, 0, 0, 0, 0, [], CONTAINER)
    assert isinstance(result, PlacementScore)
    assert result.breakdown["contact_area"] == 0.0
