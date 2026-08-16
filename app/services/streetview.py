"""
Mapillary street-level imagery lookup.

Answers one question for the dispatch board: "what does this place actually
look like?" — asked of a delivery stop whose address a driver cannot find, or
of an arbitrary point on the map. Returns the nearest street-level photo
Mapillary holds, with the date it was taken.

Imagery is crowdsourced and free (Mapillary is Meta-owned and has no paid
tier). Most Ho Chi Minh City and Hanoi coverage came from Be Group's
ride-hailing drivers, so arterial roads are dense and alleys, yards and
industrial estates are patchy. A miss is therefore a normal, expected result
and not an error — see find_nearest_image's contract below.

The token lives in app/config.MAPILLARY_TOKEN and never leaves the server:
callers get an image id and an embed URL, which is all the browser needs.
"""
import logging
import math

import requests

from app import config
from app.utils.geo import get_distance_meters

logger = logging.getLogger(__name__)

GRAPH_IMAGES_URL = "https://graph.mapillary.com/images"
DEFAULT_TIMEOUT_S = 12

# Fields requested from the Graph API. Kept minimal on purpose — `detections`
# and `sfm_cluster` on the same entity return hundreds of KB per image.
IMAGE_FIELDS = "id,captured_at,is_pano,geometry,compass_angle"

# Mapillary caps the radius search at 50 m and rejects anything larger, so this
# is their limit rather than a tuning choice.
RADIUS_CAP_M = 50

# Half-widths of the two fallback boxes, tried in order.
#
# Stop coordinates reach this system as hand-typed text in the manager's Google
# Sheet (see services/delivery/sheet_import_service.py), so a stop sitting 80 m
# off the road it belongs to is ordinary rather than exceptional, and the 50 m
# radius cap alone would call that "no coverage".
#
# The 500 m pass was added 2026-08-16 for a reason the operator identified:
# most of this fleet's stops are down lanes and yards that no Mapillary driver
# ever entered, so the nearest imagery is typically on the arterial road the
# lane comes off. That image is *useful* — it is how a driver actually
# approaches — and the earlier 150 m ceiling discarded exactly those results.
#
# 500 m each way is ~0.009 degrees square at this latitude, just inside the
# API's hard 0.01-degree-square bbox limit. That limit is why there is no third
# pass: a wider search needs several boxes or the s2/tile parameters, and the
# honest answer past half a kilometre is that the point is not covered.
FALLBACK_HALF_M = 100
WIDE_HALF_M = 500

# Ceiling on how far away a photo may be and still be returned. Generous on
# purpose — the caller is told the distance and can judge for itself. What it
# still excludes is the case where a click lands in open country and the
# nearest image is on a highway a kilometre away, which answers a question
# nobody asked.
MAX_USEFUL_DISTANCE_M = 600

# Enough candidates to find the genuinely closest one in the box without
# pulling the whole street.
FALLBACK_LIMIT = 50


class StreetViewUnavailable(Exception):
    """Mapillary could not be reached, or refused the request.

    Strictly separate from "no imagery here", which is a finding and is
    signalled by returning None. Collapsing the two would let an outage or an
    expired token read to the dispatcher as an uncovered address, and the
    dashboard would quietly stop working with no way to tell.
    """


def is_configured():
    return bool(config.MAPILLARY_TOKEN)


def _get(params, timeout):
    """One authenticated Graph API call. Raises StreetViewUnavailable."""
    # Header rather than ?access_token= — Mapillary's own docs prefer the header
    # for entity calls, and it keeps the credential out of any proxy or server
    # access log that records query strings.
    headers = {"Authorization": f"OAuth {config.MAPILLARY_TOKEN}"}
    try:
        response = requests.get(
            GRAPH_IMAGES_URL, params=params, headers=headers, timeout=timeout
        )
    except requests.RequestException as e:
        raise StreetViewUnavailable(f"Mapillary request failed: {e}") from e

    # Body before status: Mapillary reports a throttle as a 4xx carrying an
    # `error` object whose message is the only thing that distinguishes "you
    # are rate limited" from "your token is wrong", and both matter to whoever
    # reads the log.
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict) and payload.get("error"):
        err = payload["error"]
        message = err.get("message") if isinstance(err, dict) else str(err)
        raise StreetViewUnavailable(message or "Mapillary rejected the request")

    if not response.ok:
        raise StreetViewUnavailable(f"Mapillary returned HTTP {response.status_code}")

    if not isinstance(payload, dict):
        raise StreetViewUnavailable("Mapillary returned an unreadable response")

    data = payload.get("data")
    return data if isinstance(data, list) else []


def _coords(image):
    """(lat, lng) from an image entity, or None if the geometry is unusable."""
    geometry = image.get("geometry") or {}
    pair = geometry.get("coordinates")
    # GeoJSON is [lng, lat]. Reversing these is the classic silent bug here:
    # 10.77, 106.69 is Ho Chi Minh City and 106.69, 10.77 is nowhere, but both
    # are valid floats and neither raises.
    if not isinstance(pair, (list, tuple)) or len(pair) < 2:
        return None
    try:
        return float(pair[1]), float(pair[0])
    except (TypeError, ValueError):
        return None


def _shape(image, lat, lng, found_by):
    """Normalise a Graph API image entity into the dict the endpoint returns."""
    coords = _coords(image)
    distance = get_distance_meters(lat, lng, coords[0], coords[1]) if coords else None

    captured_at = image.get("captured_at")
    # Mapillary sends milliseconds since epoch. Passed through unchanged rather
    # than formatted here: the browser knows the dispatcher's locale and this
    # module does not.
    try:
        captured_at = int(captured_at) if captured_at is not None else None
    except (TypeError, ValueError):
        captured_at = None

    image_id = str(image.get("id")) if image.get("id") is not None else None

    return {
        "image_id": image_id,
        "captured_at": captured_at,
        "is_pano": bool(image.get("is_pano")),
        "compass_angle": image.get("compass_angle"),
        "lat": coords[0] if coords else None,
        "lng": coords[1] if coords else None,
        "distance_m": round(distance, 1) if distance is not None else None,
        "found_by": found_by,
        # style=photo gives the viewer alone. The `split` and `classic` styles
        # embed a second map, which would put a competing map inside a page
        # whose whole centre panel is already a map.
        "embed_url": (
            f"https://www.mapillary.com/embed?image_key={image_id}&style=photo"
            if image_id else None
        ),
        "page_url": (
            f"https://www.mapillary.com/app/?pKey={image_id}&focus=photo"
            if image_id else None
        ),
    }


def _bbox_around(lat, lng, half_m):
    """A square bbox in degrees: (west, south, east, north)."""
    dlat = half_m / 111000.0
    # Longitude degrees shorten toward the poles. At Ho Chi Minh City's
    # latitude the error from ignoring this is only ~2%, but the fleet's data
    # is not a promise about where it will operate next.
    cos_lat = math.cos(math.radians(lat))
    dlng = half_m / (111000.0 * cos_lat) if abs(cos_lat) > 1e-6 else 180.0
    return lng - dlng, lat - dlat, lng + dlng, lat + dlat


def find_nearest_image(lat, lng, timeout=DEFAULT_TIMEOUT_S):
    """Nearest usable street-level image to (lat, lng), or None if there is none.

    Two passes, because Mapillary's radius search stops at 50 m:

    1. Radius search. Mapillary picks the "best" image itself, weighing
       proximity, recency and a preference for 360° panoramas — a better answer
       than nearest-wins when several images qualify, so its choice is kept.
    2. Bounding box roughly 200 m across, nearest-wins. Catches the stop whose
       typed coordinate landed in the middle of a block.

    Returns None when both passes come up empty or the closest hit is further
    than MAX_USEFUL_DISTANCE_M. Raises StreetViewUnavailable if Mapillary could
    not be asked at all — the caller must keep those two apart.
    """
    if not is_configured():
        raise StreetViewUnavailable("Mapillary is not configured (no MAPILLARY_TOKEN)")

    radius_hits = _get({
        "fields": IMAGE_FIELDS,
        "lat": lat,
        "lng": lng,
        "radius": RADIUS_CAP_M,
        "limit": 1,
    }, timeout)

    if radius_hits:
        return _shape(radius_hits[0], lat, lng, "radius")

    # Narrow box first and only widen on a miss. The narrow one covers the
    # common case in one call, and a 500 m box in a dense district returns the
    # limit's worth of images from streets that are not the one being asked
    # about, which costs bandwidth to then throw away.
    for half_m, label in ((FALLBACK_HALF_M, "bbox"), (WIDE_HALF_M, "bbox_wide")):
        west, south, east, north = _bbox_around(lat, lng, half_m)
        box_hits = _get({
            "fields": IMAGE_FIELDS,
            "bbox": f"{west},{south},{east},{north}",
            "limit": FALLBACK_LIMIT,
        }, timeout)

        best = None
        best_distance = None
        for image in box_hits:
            coords = _coords(image)
            if not coords:
                continue
            distance = get_distance_meters(lat, lng, coords[0], coords[1])
            if best_distance is None or distance < best_distance:
                best, best_distance = image, distance

        if best is not None and best_distance <= MAX_USEFUL_DISTANCE_M:
            return _shape(best, lat, lng, label)

    logger.debug(
        "No street-level imagery within %sm of %s,%s", MAX_USEFUL_DISTANCE_M, lat, lng
    )
    return None
