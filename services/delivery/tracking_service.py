"""GPS telemetry normalization for the delivery dashboard.

Input contract
--------------
``normalize_gps_position()`` takes a **raw TTAS DevList item** — the dicts
returned by ``app.services.ttas_client.fetch_vehicle_data()``, whose keys are
TTAS's own (``biensoxe``, ``speed``, ``ad3``, ``trktime``, ``driver``,
``latitude``, ``longitude``).

Before 2026-07-31 this module read ``speed_status`` / ``vehicle_status`` /
``engine_status`` / ``last_update`` / ``driver_name`` off that raw dict. Those
are the *output* key names of ``normalize_vehicle()``, not TTAS's input names,
so every one of them silently resolved to its default and no ``device_name``
was emitted at all — which meant the dashboard could never match a GPS
position to a vehicle (audit C-02). Raw-key parsing is therefore delegated to
``normalize_vehicle()`` rather than reimplemented here: it already owns the
six-key license-plate fallback chain, the Vietnamese speed-phrase → status
derivation, and ``safe_float``/``clean_text`` coercion. Duplicating that would
create a second source of truth for TTAS's field names.
"""
import logging
import re
from typing import Optional

from services.plate_utils import normalize_plate

logger = logging.getLogger(__name__)


def normalize_gps_position(raw_vehicle: dict) -> dict:
    """Flat dict of normalized telemetry for one vehicle.

    New fields can be added here without breaking existing consumers, since
    callers read named keys off this dict rather than assuming a fixed set.

    ``device_name`` is the license plate as TTAS reports it; ``plate_key`` is
    that plate reduced to its 5-digit serial via ``normalize_plate``, and is
    the field callers should join on — it is stable across the ``50E-18463`` /
    ``50E18463`` / ``50E 18463`` / ``18463`` formatting variants that TTAS and
    the ``vehicles`` table disagree about.
    """
    # Deferred import: app.services.ttas_client pulls in app.config, which
    # raises at import time when .env is absent. Keeping it out of module
    # scope lets this module (and its pure-function tests) be imported
    # without a configured environment. Deliberately not wrapped in
    # try/except — a genuine import failure must surface, not degrade.
    from app.services.ttas_client import normalize_vehicle

    vehicle = normalize_vehicle(raw_vehicle)
    vehicle_status = vehicle.get("vehicle_status", "unknown")

    device_name = vehicle.get("device_name", "")
    speed_status = vehicle.get("speed_status", "")

    # safe_float() coerces missing/garbage coordinates to 0.0 rather than
    # None, so an exact 0,0 reading is TTAS saying "no fix" — not a vehicle
    # in the Gulf of Guinea. Surface that as None so the frontend's existing
    # `if (!gps || gps.lat == null)` guard skips the marker.
    lat = vehicle.get("latitude")
    lng = vehicle.get("longitude")
    if not lat and not lng:
        lat = lng = None

    return {
        "device_name": device_name,
        "plate_key": normalize_plate(device_name),
        "lat": lat,
        "lng": lng,
        "speed": speed_status,
        "speed_kmh": _parse_speed_kmh(speed_status),
        "vehicle_status": vehicle_status,
        # TTAS saying the tracker is unreachable ("MTH:6h48'"), as opposed to
        # the dashboard inferring it from the age of the last fix. The No GPS
        # filter keys off this: such a vehicle still *has* a position — the
        # last one before the signal dropped — so a "no position at all"
        # test alone would leave it out of the one list a dispatcher checks
        # to find the trucks they cannot see.
        "signal_lost": vehicle_status == "lost_signal",
        "engine_status": vehicle.get("engine_status", ""),
        # Raw TTAS text for display; the ISO twin for anything computing an
        # age. None means "position is real, its age is unknown" — a third
        # state the dashboard must show rather than guess at.
        "last_update": vehicle.get("last_update", ""),
        "last_update_iso": vehicle.get("last_update_iso"),
        "driver_name": vehicle.get("driver_name", "Unknown"),
    }


# A number that carries the unit — "42km/h", "37.5 km/h", "0 km / h". This is
# the only unambiguous reading in the phrase, so it is tried first.
_KMH_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*km\s*/?\s*h", re.IGNORECASE)

# Durations, which are what a *stopped* phrase counts: "3h30'", "25 phút",
# "1 giờ". Stripped before any unitless fallback so a park time can never be
# mistaken for a speed.
_DURATION_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:h(?!\w)|giờ|phút|ph(?!\w)|')", re.IGNORECASE)

_NUMBER_RE = re.compile(r"(\d+(?:[.,]\d+)?)")


def _parse_speed_kmh(speed_status: str) -> Optional[float]:
    """Numeric km/h from TTAS's speed text, which is a Vietnamese status
    phrase ("Chạy 42km/h", "Dừng 3h30'") rather than a number.

    Reading the *first* number in the phrase — what this did until
    2026-08-03, and what `app/routes/trips.py` still does — is wrong for
    every stopped vehicle: a parked truck's phrase counts how long it has
    been parked, so "Dừng 3h30'" was reported to the dispatcher as 3 km/h,
    and the figure grew the longer the truck sat still. Operator-reported.

    The number is therefore taken only when it carries the km/h unit, and a
    "Dừng" phrase is read as a genuine **0.0** — TTAS is stating the vehicle
    is stopped, which is knowledge, not absence of it. `None` stays reserved
    for a phrase this cannot interpret at all, since the dashboard renders
    that as "no reading" rather than as a speed.

    Supplementary operational signal only — never used for ETA or routing.
    """
    if not speed_status:
        return None

    text = speed_status.strip()

    match = _KMH_RE.search(text)
    if match:
        return _to_float(match.group(1))

    # "Dừng đỗ", "Dừng 3h30'", "Dừng 7h44'" — stopped, and TTAS says so.
    if text.startswith("Dừng"):
        return 0.0

    # A moving vehicle whose reading lost its unit. Durations are removed
    # first so the fallback cannot pick a time out of the phrase; if nothing
    # numeric survives, the reading is unknown rather than zero.
    if text.startswith("Chạy"):
        match = _NUMBER_RE.search(_DURATION_RE.sub(" ", text))
        if match:
            return _to_float(match.group(1))

    return None


def _to_float(raw: str) -> Optional[float]:
    """TTAS is a Vietnamese-locale system; a decimal comma is plausible even
    though every sample so far uses a point."""
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None
