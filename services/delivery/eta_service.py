import logging
import math
import threading
from typing import Optional

# Shared ORS transport. Same package direction as execution_service ->
# app.db and tracking_service -> app.services.ttas_client. The request shape,
# the always-on routing options (avoid_borders) and the error classification
# belong in exactly one place; this module owns the ETA arithmetic, not the
# HTTP call.
from app.services.routing import (
    OrsNoRouteError,
    OrsUnavailableError,
    request_directions,
)
from app.services.vehicle_specs import relax_dimensions, restrictions_fingerprint

logger = logging.getLogger(__name__)

# Route/ETA cache — avoids re-hitting ORS every poll for an assignment whose
# remaining stops and GPS position haven't meaningfully changed. Scoped to
# this module (not app/state.py, which is documented as being for the
# fleet/fuel/oil/trips blueprints + TTAS session, a different concern).
_route_cache = {}  # assignment_id -> {"key": stops_key, "gps": (lat, lng), "result": [...]}
_route_cache_lock = threading.Lock()
ROUTE_CACHE_GPS_THRESHOLD_M = 50  # below this, treat GPS position as "unchanged"


def get_distance_meters(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (math.sin(delta_phi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def calculate_eta(ors_api_key: str, ors_base_url: str,
                  from_lat: float, from_lng: float,
                  to_lat: float, to_lng: float,
                  options: Optional[dict] = None) -> dict:
    """Road distance/duration for one leg, with a straight-line fallback.

    ``route_status`` separates the reasons a leg can end up without a real
    road route:

      "ok"              a road route was found
      "not_configured"  no ORS API key
      "no_route"        ORS answered: no route exists, even unrestricted
      "unavailable"     ORS could not be reached, or failed for another reason

    ``restriction_status`` says what the route is worth:

      "compliant"     routed with this vehicle's restrictions applied
      "violated"      no compliant route existed; this one ignores the
                      vehicle's dimensions and may not be legal or physically
                      passable for it
      "unrestricted"  no envelope data for this vehicle, so nothing was checked
      "unknown"       no route was obtained at all

    "unrestricted" and "violated" are deliberately distinct: "we did not check"
    and "we checked and it failed" are different claims and must not be
    presented as one.
    """
    straight_km = round(get_distance_meters(from_lat, from_lng, to_lat, to_lng) / 1000, 2)

    def straight_line(source: str, route_status: str) -> dict:
        return {
            "distance_km": straight_km,
            "duration_sec": None,
            "eta": None,
            "source": source,
            "route_status": route_status,
            "restriction_status": "unknown",
            "geometry": None,
        }

    def road_route(result: dict, restriction_status: str) -> dict:
        distance_m = result["distance_m"]
        duration_sec = result["duration_s"]
        # ORS/GeoJSON coordinates are [lng, lat]; Leaflet wants [lat, lng].
        geometry = [[c[1], c[0]] for c in result["coordinates"]] or None
        return {
            "distance_km": round(distance_m / 1000, 2) if distance_m is not None else straight_km,
            "duration_sec": duration_sec,
            "eta": duration_sec,
            "source": "ors",
            "route_status": "ok",
            "restriction_status": restriction_status,
            "geometry": geometry,
        }

    if not ors_api_key:
        return straight_line("haversine", "not_configured")

    coordinates = [[from_lng, from_lat], [to_lng, to_lat]]

    try:
        result = request_directions(ors_api_key, ors_base_url, coordinates, options=options)
        return road_route(result, "compliant" if options else "unrestricted")
    except OrsUnavailableError as e:
        # A transport fault is not a routing finding, and must not be retried
        # as though the restrictions were the problem.
        logger.warning("ORS ETA calculation failed: %s", e)
        return straight_line("haversine_fallback", "unavailable")
    except OrsNoRouteError as e:
        first_failure = e

    # Second rung: no compliant route exists. Retry once without the dimension
    # restrictions so the dispatcher still gets a line to the destination, and
    # mark it loudly rather than passing it off as a normal route. Note
    # avoid_borders survives this — routing.py reapplies it after every caller,
    # so the border rule is not part of what degrades.
    relaxed = relax_dimensions(options)
    if options:
        try:
            result = request_directions(ors_api_key, ors_base_url, coordinates, options=relaxed)
            logger.warning(
                "No compliant route from (%s, %s) to (%s, %s) for restrictions %s — "
                "falling back to an unrestricted route: %s",
                from_lat, from_lng, to_lat, to_lng,
                (options or {}).get("profile_params"), first_failure,
            )
            return road_route(result, "violated")
        except OrsUnavailableError as e:
            logger.warning("ORS ETA relaxed retry failed: %s", e)
            return straight_line("haversine_fallback", "unavailable")
        except OrsNoRouteError as e:
            first_failure = e

    # Nothing reaches this stop, restrictions or not: a border, a bad
    # coordinate, or genuinely no road.
    logger.warning("No route at all from (%s, %s) to (%s, %s): %s",
                   from_lat, from_lng, to_lat, to_lng, first_failure)
    return straight_line("haversine_no_route", "no_route")


def _compute_etas_for_stops(ors_api_key: str, ors_base_url: str,
                             current_lat: float, current_lng: float,
                             stops: list[dict],
                             options: Optional[dict] = None) -> list[dict]:
    cumulative_duration = 0.0
    cumulative_distance = 0.0
    results = []
    prev_lat, prev_lng = current_lat, current_lng

    for stop in stops:
        stop_lat = stop.get("lat")
        stop_lng = stop.get("lng")
        if stop_lat is None or stop_lng is None:
            results.append({**stop, "stop_id": stop.get("id"), "distance_km": None,
                            "duration_sec": None, "cumulative_sec": None, "cumulative_km": None,
                            "eta_seconds": None, "geometry": None,
                            "route_status": "no_coordinates",
                            "restriction_status": "unknown"})
            continue

        leg = calculate_eta(ors_api_key, ors_base_url,
                            prev_lat, prev_lng, stop_lat, stop_lng,
                            options=options)
        if leg.get("duration_sec"):
            cumulative_duration += leg["duration_sec"]
        if leg.get("distance_km"):
            cumulative_distance += leg["distance_km"]

        results.append({
            **stop,
            "stop_id": stop.get("id"),
            "distance_km": leg["distance_km"],
            "duration_sec": leg["duration_sec"],
            "cumulative_sec": cumulative_duration,
            "cumulative_km": round(cumulative_distance, 2),
            "eta_seconds": cumulative_duration,
            "geometry": leg.get("geometry"),
            # Carried through to /api/eta so the dashboard can distinguish a
            # real road leg from a straight-line placeholder. Nothing renders
            # it yet — that is phase C4 of docs/VEHICLE_ROUTING_PLAN.md.
            "route_status": leg.get("route_status"),
            "restriction_status": leg.get("restriction_status"),
        })

        if stop_lat is not None and stop_lng is not None:
            prev_lat, prev_lng = stop_lat, stop_lng

    return results


def _stops_cache_key(stops: list[dict], options: Optional[dict] = None):
    """Cache identity for a set of remaining stops under a set of restrictions.

    The restriction fingerprint is part of the key, not an afterthought: an
    assignment's vehicle is fixed, so without it, editing that truck's
    dimensions would keep serving routes computed under the old ones until the
    process restarted. Changing the specs now changes the key, and the stale
    route dies on the next poll.
    """
    return (
        restrictions_fingerprint(options),
        tuple((s.get("id"), s.get("lat"), s.get("lng")) for s in stops),
    )


def calculate_etas_for_stops(ors_api_key: str, ors_base_url: str,
                              current_lat: float, current_lng: float,
                              stops: list[dict],
                              assignment_id: Optional[int] = None,
                              options: Optional[dict] = None) -> list[dict]:
    """Same computation as _compute_etas_for_stops, with an optional
    in-memory cache keyed by assignment_id. A cached result is reused only
    when the remaining stop set/order/destinations AND the vehicle's routing
    restrictions are identical, AND the vehicle hasn't moved more than
    ROUTE_CACHE_GPS_THRESHOLD_M — i.e. it's invalidated by assignment change,
    stop order change, stop completion/skip (both alter the remaining-stop
    set), a change to the vehicle's specs, or significant GPS movement.
    assignment_id=None (the default) bypasses the cache entirely.
    """
    if assignment_id is None:
        return _compute_etas_for_stops(ors_api_key, ors_base_url,
                                       current_lat, current_lng, stops, options)

    stops_key = _stops_cache_key(stops, options)

    with _route_cache_lock:
        cached = _route_cache.get(assignment_id)

    if cached is not None and cached["key"] == stops_key:
        moved_m = get_distance_meters(cached["gps"][0], cached["gps"][1], current_lat, current_lng)
        if moved_m < ROUTE_CACHE_GPS_THRESHOLD_M:
            return cached["result"]

    result = _compute_etas_for_stops(ors_api_key, ors_base_url,
                                     current_lat, current_lng, stops, options)

    with _route_cache_lock:
        _route_cache[assignment_id] = {"key": stops_key, "gps": (current_lat, current_lng), "result": result}

    return result


def calculate_travelled_distance_km(stops: list[dict], current_lat: float, current_lng: float) -> float:
    """Approximate straight-line distance already covered on this assignment:
    sums stop-to-stop gaps for stops already passed (completed/skipped, in
    planned_sequence order), plus the gap from the last passed stop to the
    vehicle's current position. Intentionally straight-line rather than
    road-based — avoids extra ORS calls for a secondary, best-effort figure.
    """
    ordered = sorted(stops, key=lambda s: s.get("planned_sequence") or 0)
    passed = [s for s in ordered if s.get("execution_status") in ("completed", "skipped")]
    if not passed:
        return 0.0

    total_m = 0.0
    prev_lat, prev_lng = None, None
    for s in passed:
        lat, lng = s.get("lat"), s.get("lng")
        if lat is None or lng is None:
            continue
        if prev_lat is not None:
            total_m += get_distance_meters(prev_lat, prev_lng, lat, lng)
        prev_lat, prev_lng = lat, lng

    if prev_lat is not None:
        total_m += get_distance_meters(prev_lat, prev_lng, current_lat, current_lng)

    return round(total_m / 1000, 2)
