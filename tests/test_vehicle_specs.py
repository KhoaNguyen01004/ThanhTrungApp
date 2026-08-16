"""
Tests for app/services/vehicle_specs.py — the vehicle envelope.

The case these exist for: cargo-compartment figures entered into envelope
fields. Every one of those numbers is a valid positive integer, so nothing
weaker than a cross-field check notices, and the mistake understates the
vehicle in the direction that routes it under a bridge it hits
(docs/VEHICLE_ROUTING_PLAN.md §3).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import vehicle_specs as vs


# Real rows from the fleet: 50H-36908, a "2.5 Tons" box truck.
REAL_CARGO = {
    "cargo_length_mm": 4285,
    "cargo_width_mm": 1850,
    "cargo_height_mm": 1810,
    "payload_kg": 1600,
}
REAL_ENVELOPE = {
    "gross_weight_kg": 4990,
    "overall_height_mm": 2900,
    "overall_width_mm": 2000,
    "overall_length_mm": 6200,
    "axle_load_kg": None,
}


class TestCoerceEnvelopeValue:
    def test_blank_stays_none_and_never_becomes_zero(self):
        # A 0 would be sent to ORS as a real restriction rather than as
        # "unknown", and would match no road at all.
        for blank in ("", "   ", None):
            assert vs.coerce_envelope_value(blank) is None

    def test_zero_and_negatives_are_treated_as_unknown(self):
        assert vs.coerce_envelope_value(0) is None
        assert vs.coerce_envelope_value("0") is None
        assert vs.coerce_envelope_value(-5) is None

    def test_numeric_strings_and_floats_are_accepted(self):
        assert vs.coerce_envelope_value("2900") == 2900
        assert vs.coerce_envelope_value(2900.0) == 2900
        assert vs.coerce_envelope_value(" 2900 ") == 2900

    def test_garbage_is_unknown_rather_than_an_exception(self):
        assert vs.coerce_envelope_value("tall") is None


class TestCargoConsistency:
    """The whole point of the module."""

    def test_cargo_figures_pasted_into_envelope_fields_are_rejected(self):
        mistaken = {
            "gross_weight_kg": REAL_CARGO["payload_kg"],
            "overall_height_mm": REAL_CARGO["cargo_height_mm"],
            "overall_width_mm": REAL_CARGO["cargo_width_mm"],
            "overall_length_mm": REAL_CARGO["cargo_length_mm"],
            "axle_load_kg": None,
        }
        errors, _ = vs.validate_envelope(mistaken, REAL_CARGO)
        # Three of the four fire, not one — the operator should see the whole
        # picture rather than fix a field at a time. Width is the exception by
        # design: its check is non-strict, because a body exactly as wide as
        # its cargo is physically possible, so an equal value cannot be called
        # an error. Three flags on one save is an unmissable signal anyway.
        assert len(errors) == 3
        assert any("overall_height_mm" in e for e in errors)
        assert any("overall_length_mm" in e for e in errors)
        assert any("gross_weight_kg" in e for e in errors)
        assert any("cargo compartment" in e for e in errors)

    def test_a_correct_envelope_passes_cleanly(self):
        errors, warnings = vs.validate_envelope(REAL_ENVELOPE, REAL_CARGO)
        assert errors == []
        assert warnings == []

    def test_height_must_strictly_exceed_the_cargo_box(self):
        # Equal is still wrong: the chassis and floor are not zero-thickness.
        envelope = {**REAL_ENVELOPE, "overall_height_mm": REAL_CARGO["cargo_height_mm"]}
        errors, _ = vs.validate_envelope(envelope, REAL_CARGO)
        assert any("overall_height_mm" in e for e in errors)

    def test_width_may_equal_the_cargo_width(self):
        # Unlike height and length, a body exactly as wide as its cargo is
        # physically possible.
        envelope = {**REAL_ENVELOPE, "overall_width_mm": REAL_CARGO["cargo_width_mm"]}
        errors, _ = vs.validate_envelope(envelope, REAL_CARGO)
        assert not any("overall_width_mm" in e for e in errors)

    def test_gross_weight_must_exceed_payload(self):
        envelope = {**REAL_ENVELOPE, "gross_weight_kg": REAL_CARGO["payload_kg"]}
        errors, _ = vs.validate_envelope(envelope, REAL_CARGO)
        assert any("gross_weight_kg" in e for e in errors)

    def test_unknown_values_are_not_checked_against_cargo(self):
        blank = {f: None for f in vs.ENVELOPE_FIELDS}
        errors, warnings = vs.validate_envelope(blank, REAL_CARGO)
        assert errors == []
        assert warnings == []

    def test_a_vehicle_with_no_cargo_config_skips_the_cross_check(self):
        errors, _ = vs.validate_envelope(REAL_ENVELOPE, None)
        assert errors == []


class TestPlausibilityWarnings:
    def test_out_of_range_warns_but_does_not_block(self):
        # 4.5 m is over the QCVN 09:2024 limit for a truck, but a hard block
        # would get the field left empty, which silently falls back to an
        # estimate — worse than a flagged number.
        envelope = {**REAL_ENVELOPE, "overall_height_mm": 4500}
        errors, warnings = vs.validate_envelope(envelope, REAL_CARGO)
        assert errors == []
        assert len(warnings) == 1
        assert "overall_height_mm" in warnings[0]

    def test_implausibly_small_also_warns(self):
        envelope = {**REAL_ENVELOPE, "gross_weight_kg": 900,
                    "overall_height_mm": 2900}
        _, warnings = vs.validate_envelope(envelope, None)
        assert any("gross_weight_kg" in w for w in warnings)


class TestResolveEnvelope:
    def test_a_fully_specified_vehicle_reports_source_vehicle(self):
        envelope, source = vs.resolve_envelope({"vehicle_type": "2.5 Tons", **REAL_ENVELOPE})
        assert source == "vehicle"
        assert envelope["overall_height_mm"] == 2900

    def test_an_empty_vehicle_falls_back_to_its_type(self):
        envelope, source = vs.resolve_envelope({"vehicle_type": "2.5 Tons"})
        assert source == "type_default"
        assert envelope["overall_height_mm"] == vs.TYPE_DEFAULTS["2.5 tons"]["overall_height_mm"]

    def test_partial_data_reports_mixed_and_prefers_the_vehicle(self):
        envelope, source = vs.resolve_envelope({
            "vehicle_type": "2.5 Tons",
            "overall_height_mm": 3050,
        })
        assert source == "mixed"
        assert envelope["overall_height_mm"] == 3050            # the vehicle's own
        assert envelope["gross_weight_kg"] == 4990              # from the type

    def test_an_unknown_type_with_no_data_reports_none(self):
        envelope, source = vs.resolve_envelope({"vehicle_type": "Hovercraft"})
        assert source == "none"
        assert envelope == {}

    def test_type_matching_ignores_case_and_padding(self):
        _, source = vs.resolve_envelope({"vehicle_type": "  CONTAINER  "})
        assert source == "type_default"

    def test_a_zero_in_the_column_is_treated_as_unknown(self):
        # Guards the NULL-vs-0 rule at the read side too, in case a 0 ever
        # reaches the column by some other route.
        envelope, source = vs.resolve_envelope({"vehicle_type": "2.5 Tons",
                                                "overall_height_mm": 0})
        assert envelope["overall_height_mm"] == vs.TYPE_DEFAULTS["2.5 tons"]["overall_height_mm"]
        assert source == "type_default"


class TestToOrsRestrictions:
    def test_converts_mm_and_kg_to_metres_and_tonnes(self):
        restrictions = vs.to_ors_restrictions({
            "overall_height_mm": 2900, "overall_width_mm": 2000,
            "overall_length_mm": 6200, "gross_weight_kg": 4990,
            "axle_load_kg": 3400,
        })
        assert restrictions == {
            "height": 2.9, "width": 2.0, "length": 6.2,
            "weight": 4.99, "axleload": 3.4,
        }

    def test_unknown_restrictions_are_omitted_never_sent_as_zero(self):
        restrictions = vs.to_ors_restrictions({"overall_height_mm": 2900})
        assert restrictions == {"height": 2.9}
        assert "weight" not in restrictions
        assert "axleload" not in restrictions

    def test_an_empty_envelope_produces_no_restrictions(self):
        assert vs.to_ors_restrictions({}) == {}

    def test_the_whole_fleet_of_type_defaults_converts_sanely(self):
        for vehicle_type, defaults in vs.TYPE_DEFAULTS.items():
            restrictions = vs.to_ors_restrictions(defaults)
            assert 1.5 < restrictions["height"] <= 4.0, vehicle_type
            assert 1.5 <= restrictions["width"] <= 2.5, vehicle_type
            assert 3.5 <= restrictions["length"] <= 12.2, vehicle_type
            assert restrictions["weight"] > 1.0, vehicle_type


class TestOrsVehicleType:
    """Decided by gross weight, never by the vehicle_type label. "2.5 Tons"
    and "10 Tons" are payload-class names for categorising the fleet; the real
    gross weights are nothing like those numbers."""

    def test_light_commercial_vehicles_are_goods(self):
        assert vs.ors_vehicle_type({"gross_weight_kg": 3490}) == "goods"
        assert vs.ors_vehicle_type({"gross_weight_kg": 3500}) == "goods"

    def test_anything_over_3500kg_is_hgv(self):
        assert vs.ors_vehicle_type({"gross_weight_kg": 3501}) == "hgv"
        # The label says 2.5 tonnes; the truck weighs 4990 kg laden. The label
        # is not what decides this.
        assert vs.ors_vehicle_type({"gross_weight_kg": 4990}) == "hgv"

    def test_unknown_weight_falls_back_to_the_stricter_profile(self):
        # Wrong towards `goods` puts a truck down a road tagged hgv=no. Wrong
        # towards `hgv` costs a detour. Only one of those is recoverable.
        assert vs.ors_vehicle_type({}) == "hgv"
        assert vs.ors_vehicle_type({"gross_weight_kg": None}) == "hgv"

    def test_the_label_is_ignored_entirely(self):
        heavy_label_light_truck = {"vehicle_type": "10 Tons", "gross_weight_kg": 3000}
        assert vs.ors_vehicle_type(heavy_label_light_truck) == "goods"


class TestBuildOrsOptions:
    def test_builds_vehicle_type_and_restrictions_together(self):
        options, source = vs.build_ors_options({"vehicle_type": "2.5 Tons", **REAL_ENVELOPE})
        assert source == "vehicle"
        assert options["vehicle_type"] == "hgv"          # 4990 kg
        assert options["profile_params"]["restrictions"]["height"] == 2.9

    def test_vehicle_type_is_always_present_when_restrictions_are(self):
        # ORS silently ignores the restrictions object without it.
        options, _ = vs.build_ors_options({"vehicle_type": "1.5 Tons"})
        assert "vehicle_type" in options
        assert options["profile_params"]["restrictions"]

    def test_a_1_5_ton_truck_on_type_defaults_is_goods(self):
        options, source = vs.build_ors_options({"vehicle_type": "1.5 Tons"})
        assert source == "type_default"
        assert options["vehicle_type"] == "goods"        # 3490 kg default

    def test_a_vehicle_with_nothing_known_gets_no_options_at_all(self):
        options, source = vs.build_ors_options({"vehicle_type": "Hovercraft"})
        assert options is None
        assert source == "none"

    def test_avoid_borders_is_never_set_here(self):
        # routing.py forces it on every request. Restating it would suggest it
        # is this layer's to decide, and therefore droppable.
        options, _ = vs.build_ors_options({"vehicle_type": "2.5 Tons"})
        assert "avoid_borders" not in options


class TestRelaxDimensions:
    def test_drops_the_restrictions_but_keeps_vehicle_type(self):
        options, _ = vs.build_ors_options({"vehicle_type": "10 Tons"})
        relaxed = vs.relax_dimensions(options)
        # Legal access bans are not dimensions: a truck barred from a road by
        # hgv=no is still barred when its height is the problem elsewhere.
        assert relaxed["vehicle_type"] == "hgv"
        assert "profile_params" not in relaxed

    def test_none_relaxes_to_none(self):
        assert vs.relax_dimensions(None) is None


class TestRestrictionsFingerprint:
    def test_the_same_options_hash_the_same(self):
        a, _ = vs.build_ors_options({"vehicle_type": "2.5 Tons"})
        b, _ = vs.build_ors_options({"vehicle_type": "2.5 Tons"})
        assert vs.restrictions_fingerprint(a) == vs.restrictions_fingerprint(b)

    def test_changing_a_dimension_changes_the_hash(self):
        base, _ = vs.build_ors_options({"vehicle_type": "2.5 Tons"})
        taller, _ = vs.build_ors_options({"vehicle_type": "2.5 Tons",
                                          "overall_height_mm": 3300})
        # This is what kills a cached route when a truck's specs are edited.
        assert vs.restrictions_fingerprint(base) != vs.restrictions_fingerprint(taller)

    def test_key_order_does_not_affect_the_hash(self):
        one = {"vehicle_type": "hgv", "profile_params": {"restrictions": {"height": 3.0, "weight": 8.5}}}
        two = {"profile_params": {"restrictions": {"weight": 8.5, "height": 3.0}}, "vehicle_type": "hgv"}
        assert vs.restrictions_fingerprint(one) == vs.restrictions_fingerprint(two)

    def test_no_options_has_a_stable_name(self):
        assert vs.restrictions_fingerprint(None) == "none"


class TestTypeDefaultsAreSelfConsistent:
    def test_every_default_is_inside_its_own_plausible_range(self):
        # A default that would warn if typed in by hand has no business being
        # the silent fallback.
        for vehicle_type, defaults in vs.TYPE_DEFAULTS.items():
            errors, warnings = vs.validate_envelope(defaults, None)
            assert errors == [], f"{vehicle_type}: {errors}"
            assert warnings == [], f"{vehicle_type}: {warnings}"

    def test_every_vehicle_type_in_the_database_schema_has_a_default(self):
        # The seven types actually in use. A missing one resolves to source
        # "none", which means no restrictions at all get sent for that truck.
        for vehicle_type in ["1.5 Tons", "2.5 Tons", "5 Tons", "8 Tons",
                             "9 Tons", "10 Tons", "Container"]:
            _, source = vs.resolve_envelope({"vehicle_type": vehicle_type})
            assert source == "type_default", vehicle_type
