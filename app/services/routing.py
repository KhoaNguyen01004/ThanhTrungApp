"""
OpenRouteService (ORS) routing helpers.

Extracted from app.py. `get_route_coords` is used by app/routes/trips.py's
route refresh logic; `request_directions` below is the shared transport, also
used by services/delivery/eta_service.py so the request shape, the routing
options and the error classification exist in exactly one place.
"""
import logging

import requests

from app import config
from app.utils.geo import get_distance_meters

logger = logging.getLogger(__name__)

DEFAULT_PROFILE = "driving-hgv"
DEFAULT_TIMEOUT_S = 30

# Sent on *every* directions request, whatever the vehicle.
#
# avoid_borders="all" is an operator decision rather than a tuning knob: this
# fleet does not leave Vietnam, and a route crossing into Cambodia or Laos is
# wrong no matter how much shorter it is. Unlike the per-vehicle dimension
# restrictions planned on top of this (docs/VEHICLE_ROUTING_PLAN.md phase C),
# it is a graph-level constraint in ORS and does not depend on how well the
# roads happen to be tagged in OSM.
BASE_OPTIONS = {"avoid_borders": "all"}

# 2009 "Route could not be found between locations", 2010 "Point was not
# found". Both mean ORS understood the request and no route exists under the
# options given. That is a *finding* — once vehicle restrictions land it is the
# whole point of the feature — so it is kept strictly separate from ORS being
# unreachable, which is a fault. Collapsing the two is what would let a
# straight-line estimate stand in for "this truck cannot legally get there".
ORS_CODE_NO_ROUTE = 2009
ORS_CODE_POINT_NOT_FOUND = 2010
NO_ROUTE_CODES = (ORS_CODE_NO_ROUTE, ORS_CODE_POINT_NOT_FOUND)


class OrsNoRouteError(Exception):
    """ORS answered; no route exists under the options requested."""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


class OrsUnavailableError(Exception):
    """ORS could not be reached, or failed for a reason unrelated to the route."""


def get_routing_profile(vehicle_type):
    # Every branch returns the same profile today. Kept as the seam where the
    # vehicle_type -> ORS options.vehicle_type mapping will live, because
    # restrictions do nothing at all unless that field is set
    # (docs/VEHICLE_ROUTING_PLAN.md C2).
    vehicle_type = (vehicle_type or "").lower()
    if "dau" in vehicle_type or "heavy" in vehicle_type or "truck" in vehicle_type:
        return "driving-hgv"
    if "tai" in vehicle_type or "van" in vehicle_type:
        return "driving-hgv"
    return "driving-hgv"


def _extract_error(payload):
    """(code, message) from an ORS error body, tolerating both shapes it uses."""
    if not isinstance(payload, dict):
        return None, ""
    err = payload.get("error")
    if isinstance(err, dict):
        return err.get("code"), err.get("message") or ""
    if isinstance(err, str):
        return None, err
    return None, ""


def request_directions(api_key, base_url, coordinates, profile=DEFAULT_PROFILE,
                       options=None, timeout=DEFAULT_TIMEOUT_S):
    """POST a directions request; return {coordinates, distance_m, duration_s}.

    POST rather than GET because `options` is a request-*body* parameter — the
    GET form is documented as not accepting advanced options at all, so
    avoid_borders and the vehicle restrictions planned on top of it are simply
    unreachable over it.

    The /geojson result type returns a FeatureCollection whose feature
    properties carry the same `segments` the GET form did, so callers parse the
    shape they always parsed.

    Raises OrsNoRouteError or OrsUnavailableError. Never substitutes a fallback
    of its own — what to show when there is no route is the caller's decision.
    """
    if not api_key or not base_url:
        raise OrsUnavailableError("ORS is not configured (missing API key or base URL)")

    # Caller options first, BASE_OPTIONS last: the border rule is absolute and
    # must not be droppable by a caller. Phase C's degraded retry relaxes the
    # dimension restrictions only, and enforcing that structurally here is
    # better than relying on every future call site to remember it.
    merged_options = dict(options or {})
    merged_options.update(BASE_OPTIONS)

    url = f"{base_url}/{profile}/geojson"
    try:
        response = requests.post(
            url,
            json={"coordinates": coordinates, "options": merged_options},
            headers={
                "Authorization": api_key,
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/geo+json",
            },
            timeout=timeout,
        )
    except requests.RequestException as e:
        raise OrsUnavailableError(f"ORS request failed: {e}") from e

    # The body is read *before* the status is judged. ORS reports "no route"
    # as HTTP 404 with a 2009 in the body, so calling raise_for_status() first
    # would flatten a routing finding into an indistinguishable HTTP error.
    try:
        payload = response.json()
    except ValueError:
        payload = None

    code, message = _extract_error(payload)
    if code in NO_ROUTE_CODES:
        raise OrsNoRouteError(message or "No route found between locations", code=code)

    if not response.ok:
        detail = message or (response.text or "")[:200]
        raise OrsUnavailableError(f"ORS returned HTTP {response.status_code}: {detail}")

    features = (payload or {}).get("features") or []
    if not features:
        # A 200 carrying no feature is neither a transport failure nor a route.
        raise OrsNoRouteError("ORS returned no route")

    feature = features[0] or {}
    segments = (feature.get("properties") or {}).get("segments") or []
    if not segments:
        raise OrsNoRouteError("ORS returned a route with no segments")

    # segments[0] only, matching what both call sites have always read: every
    # request made here has exactly two coordinates, so there is exactly one
    # segment. A multi-waypoint request would need these summed.
    return {
        "coordinates": (feature.get("geometry") or {}).get("coordinates") or [],
        "distance_m": segments[0].get("distance"),
        "duration_s": segments[0].get("duration"),
    }


def get_route_coords(start_lng, start_lat, end_lng, end_lat, profile=DEFAULT_PROFILE):
    """Road route between two points, falling back to a straight line.

    The returned dict gained a "status" key — "ok", "no_route", "unavailable"
    or "not_configured" — so a caller can tell a real route from a placeholder.
    The three original keys are unchanged, so existing callers need no edit.
    """
    straight_line = {
        "coordinates": [[start_lng, start_lat], [end_lng, end_lat]],
        "distance": get_distance_meters(start_lat, start_lng, end_lat, end_lng) / 1000,
        "duration": None,
    }

    if not config.ORS_API_KEY:
        logger.warning("ORS_API_KEY not set, using straight line")
        return {**straight_line, "status": "not_configured"}

    try:
        result = request_directions(
            config.ORS_API_KEY,
            config.ORS_BASE_URL,
            [[start_lng, start_lat], [end_lng, end_lat]],
            profile=profile,
        )
    except OrsNoRouteError as e:
        # With avoid_borders="all" in force this now also covers a destination
        # only reachable by leaving the country — a legitimate answer, not an
        # error to be retried.
        logger.warning("No route from (%s, %s) to (%s, %s): %s",
                       start_lat, start_lng, end_lat, end_lng, e)
        return {**straight_line, "status": "no_route"}
    except OrsUnavailableError as e:
        logger.warning("Error fetching route: %s", e)
        return {**straight_line, "status": "unavailable"}

    distance_m = result["distance_m"]
    return {
        "coordinates": result["coordinates"] or straight_line["coordinates"],
        "distance": (distance_m / 1000) if distance_m is not None else straight_line["distance"],
        "duration": result["duration_s"],
        "status": "ok",
    }
