"""
Vehicle envelope specs: validation, per-type fallbacks, and provenance.

The envelope is the vehicle itself — gross weight and overall height, width and
length — as opposed to `container_configs`, which is the cargo compartment and
exists for the bin-packing planner. Keeping the two apart is the whole point of
this module: cargo figures understate the envelope in every dimension, and
understating is the direction that routes a truck under a bridge it hits
(docs/VEHICLE_ROUTING_PLAN.md §3).

Units are mm and kg throughout, matching the existing cargo fields. Conversion
to the metres and tonnes ORS wants happens once, in `to_ors_restrictions()`,
rather than being scattered across form code where a 1000x slip would hide.
"""
import hashlib
import json
import logging

logger = logging.getLogger(__name__)

# ORS honours restrictions only for the access tags matching options.vehicle_type,
# so this choice decides which roads a truck is allowed down. The split is by
# **actual gross weight**, never by the vehicle_type label: "2.5 Tons" and
# "10 Tons" are payload-class names used for categorising the fleet, and the real
# gross weights are nothing like those numbers — a "2.5 Tons" truck is around
# 4990 kg laden.
#
# 3500 kg is the conventional line between a light commercial vehicle (OSM
# `goods`) and a heavy goods vehicle (OSM `hgv`).
GOODS_GVW_LIMIT_KG = 3500
ORS_VEHICLE_TYPE_GOODS = "goods"
ORS_VEHICLE_TYPE_HGV = "hgv"

ENVELOPE_FIELDS = (
    "gross_weight_kg",
    "overall_height_mm",
    "overall_width_mm",
    "overall_length_mm",
    "axle_load_kg",
)

# Plausibility bounds — a truck-shaped-object check, NOT a legal compliance
# check. The upper anchors come from QCVN 09:2024/BGTVT (trucks: 4.0 m tall,
# 2.5 m wide, 12.2 m long for general vehicles); the lower ones just exclude
# values that cannot describe a truck at all.
#
# Out-of-range WARNS rather than blocks, deliberately. A hard rejection on a
# legitimate outlier gets the field left empty, and empty falls back to a type
# default — a silent estimate is worse than a flagged odd number.
PLAUSIBLE_RANGES = {
    "gross_weight_kg": (1500, 40000),
    "overall_height_mm": (1800, 4000),
    "overall_width_mm": (1500, 2500),
    "overall_length_mm": (3500, 12200),
    "axle_load_kg": (500, 12000),
}

# Each envelope field must exceed its cargo counterpart, because the cargo box
# is carried *by* the vehicle. These catch the specific error this module
# exists to prevent: cargo numbers pasted into envelope fields. Every one of
# them passes a positive-number check, so nothing weaker would notice.
#
# (envelope_field, cargo_field, strict, human explanation)
CARGO_CONSISTENCY = (
    ("overall_height_mm", "cargo_height_mm", True,
     "the chassis and floor sit under the cargo box"),
    ("overall_length_mm", "cargo_length_mm", True,
     "the cab is not part of the cargo box"),
    ("overall_width_mm", "cargo_width_mm", False,
     "the body cannot be narrower than the cargo it holds"),
    ("gross_weight_kg", "payload_kg", True,
     "gross weight includes the vehicle's own kerb weight"),
)

# Fallbacks by vehicle_type, used ONLY where a vehicle's own column is NULL.
# These are estimates for common Vietnamese box-truck classes and are NOT a
# substitute for the registration certificate — anything routed from them is
# reported with restrictions_source "type_default" so the estimate is never
# mistaken for a measurement.
TYPE_DEFAULTS = {
    "1.5 tons": {"gross_weight_kg": 3490, "overall_height_mm": 2650,
                 "overall_width_mm": 1900, "overall_length_mm": 5300},
    "2.5 tons": {"gross_weight_kg": 4990, "overall_height_mm": 2900,
                 "overall_width_mm": 2000, "overall_length_mm": 6200},
    "5 tons": {"gross_weight_kg": 8500, "overall_height_mm": 3200,
               "overall_width_mm": 2200, "overall_length_mm": 7500},
    "8 tons": {"gross_weight_kg": 15000, "overall_height_mm": 3500,
               "overall_width_mm": 2350, "overall_length_mm": 9000},
    "9 tons": {"gross_weight_kg": 16000, "overall_height_mm": 3500,
               "overall_width_mm": 2350, "overall_length_mm": 9500},
    "10 tons": {"gross_weight_kg": 17500, "overall_height_mm": 3600,
                "overall_width_mm": 2400, "overall_length_mm": 10000},
    "container": {"gross_weight_kg": 24000, "overall_height_mm": 3800,
                  "overall_width_mm": 2450, "overall_length_mm": 11500},
}


def coerce_envelope_value(raw):
    """Form value -> int or None. Empty stays None; it must never become 0.

    A 0 would be sent to ORS as a genuine restriction ("this vehicle is 0 mm
    tall") rather than as "unknown", so blank and zero have to stay distinct
    all the way down.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = raw.strip()
        if raw == "":
            return None
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def validate_envelope(envelope, cargo=None):
    """(errors, warnings) for a set of envelope values.

    Errors block the save: they are physically impossible, so the number is
    wrong whatever its provenance. Warnings do not — see PLAUSIBLE_RANGES.
    """
    errors = []
    warnings = []

    for field in ENVELOPE_FIELDS:
        value = envelope.get(field)
        if value is None:
            continue
        if value <= 0:
            errors.append(f"{field} must be greater than zero")
            continue
        low, high = PLAUSIBLE_RANGES[field]
        if value < low or value > high:
            unit = "kg" if field.endswith("_kg") else "mm"
            warnings.append(
                f"{field} of {value}{unit} is outside the usual range "
                f"({low}-{high}{unit}) — please double-check it"
            )

    if cargo:
        for env_field, cargo_field, strict, why in CARGO_CONSISTENCY:
            env_value = envelope.get(env_field)
            cargo_value = cargo.get(cargo_field)
            if env_value is None or not cargo_value:
                continue
            too_small = env_value <= cargo_value if strict else env_value < cargo_value
            if too_small:
                errors.append(
                    f"{env_field} ({env_value}) must be "
                    f"{'greater than' if strict else 'at least'} "
                    f"{cargo_field} ({cargo_value}) — {why}. "
                    "Did you enter the cargo compartment figure here?"
                )

    return errors, warnings


def resolve_envelope(vehicle):
    """(envelope, source) for a vehicle row, filling gaps from its type.

    source is "vehicle" (every value from this vehicle's own record),
    "type_default" (every value from the type fallback), "mixed", or "none".
    It travels with the route so an estimate is never displayed as a fact.
    """
    defaults = TYPE_DEFAULTS.get((vehicle.get("vehicle_type") or "").strip().lower(), {})

    envelope = {}
    from_vehicle = 0
    from_default = 0

    for field in ENVELOPE_FIELDS:
        own = coerce_envelope_value(vehicle.get(field))
        if own is not None:
            envelope[field] = own
            from_vehicle += 1
        elif field in defaults:
            envelope[field] = defaults[field]
            from_default += 1

    if from_vehicle and from_default:
        source = "mixed"
    elif from_vehicle:
        source = "vehicle"
    elif from_default:
        source = "type_default"
    else:
        source = "none"

    return envelope, source


def to_ors_restrictions(envelope):
    """Envelope in mm/kg -> ORS profile_params.restrictions in m/tonnes.

    Unknown fields are omitted rather than sent as 0: ORS applies only the
    restrictions it is given, and a 0 would be a restriction that matches
    nothing. Partial data is fine — send what is known.
    """
    restrictions = {}

    if envelope.get("overall_height_mm"):
        restrictions["height"] = round(envelope["overall_height_mm"] / 1000.0, 2)
    if envelope.get("overall_width_mm"):
        restrictions["width"] = round(envelope["overall_width_mm"] / 1000.0, 2)
    if envelope.get("overall_length_mm"):
        restrictions["length"] = round(envelope["overall_length_mm"] / 1000.0, 2)
    if envelope.get("gross_weight_kg"):
        restrictions["weight"] = round(envelope["gross_weight_kg"] / 1000.0, 2)
    if envelope.get("axle_load_kg"):
        restrictions["axleload"] = round(envelope["axle_load_kg"] / 1000.0, 2)

    return restrictions


def ors_vehicle_type(envelope):
    """"goods" or "hgv", from gross weight alone.

    Unknown gross weight resolves to "hgv" — the stricter of the two. Guessing
    wrong towards `goods` would let a truck through a road tagged `hgv=no`,
    which is the failure direction that puts a vehicle somewhere it is not
    allowed to be; guessing wrong towards `hgv` only costs a detour.
    """
    gvw = envelope.get("gross_weight_kg")
    if gvw and gvw <= GOODS_GVW_LIMIT_KG:
        return ORS_VEHICLE_TYPE_GOODS
    return ORS_VEHICLE_TYPE_HGV


def build_ors_options(vehicle):
    """(options, source) for an ORS directions request, from a vehicle row.

    `options` is None when nothing is known about the vehicle — there is no
    point declaring a vehicle_type with no restrictions attached to it, and a
    caller needs to be able to tell "unrestricted" from "restricted".

    Note this never sets avoid_borders: app.services.routing forces that on
    every request regardless, and re-stating it here would invite someone to
    later think it is optional.
    """
    envelope, source = resolve_envelope(vehicle or {})
    restrictions = to_ors_restrictions(envelope)
    if not restrictions:
        return None, source

    return {
        # Mandatory. Without it the restrictions object below is inert and ORS
        # silently routes as though nothing had been asked for.
        "vehicle_type": ors_vehicle_type(envelope),
        "profile_params": {"restrictions": restrictions},
    }, source


def relax_dimensions(options):
    """`options` with the dimension restrictions dropped, vehicle_type kept.

    The second rung of the degraded-route ladder: when no compliant route
    exists, the dispatcher still needs a line on the map. vehicle_type stays
    because legal access bans (`hgv=no`) are not dimensions and are not part of
    what gets relaxed — only the physical limits are. avoid_borders is not
    touchable from here at all; routing.py reapplies it after every caller.
    """
    if not options:
        return None
    relaxed = {k: v for k, v in options.items() if k != "profile_params"}
    return relaxed or None


def restrictions_fingerprint(options):
    """Short stable hash of an options dict, for cache keys.

    Without this in the key, editing a truck's specs would keep serving routes
    computed under the old ones until the process restarted. Sorted keys so the
    hash depends on the values rather than on dict ordering.
    """
    if not options:
        return "none"
    encoded = json.dumps(options, sort_keys=True, separators=(",", ":"))
    return hashlib.md5(encoded.encode("utf-8")).hexdigest()[:12]
